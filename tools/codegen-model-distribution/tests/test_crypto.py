from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


TOOL_DIR = Path(__file__).resolve().parents[1]


def load_tool(name):
    key = "autojs6_codegen_" + name
    path = (TOOL_DIR / (name + ".py")).resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("incorrect codegen module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


crypto = load_tool("crypto")


def catalog_value(repository="SuperMonster003/AutoJs6-Shared-Assets"):
    return {"schemaVersion": 1, "catalogVersion": 1, "releaseTag": "codegen-models-v1",
            "generatedAt": "2026-10-03T00:00:00Z", "repository": repository, "models": []}


class CatalogCryptoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = crypto.find_openssl()
        cls.keys = tempfile.TemporaryDirectory(prefix="codegen offline test keys ")
        root = Path(cls.keys.name)
        cls.private, cls.pem, cls.der = root / "private.pem", root / "public.pem", root / "public.der"
        cls.key_id = crypto.generate_key_pair(cls.private, cls.pem, cls.der, cls.openssl)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codegen-crypto-test-")
        self.root = Path(self.temporary.name)
        self.catalog = self.root / "catalog-v1.json"
        self.signature = self.root / "catalog-v1.sig.json"
        self.catalog.write_bytes(crypto.canonical_json_bytes(catalog_value()))

    def tearDown(self):
        self.temporary.cleanup()

    def sign(self):
        return crypto.sign_catalog(self.catalog, self.private, self.signature, self.key_id, self.openssl)

    def verify(self, public=None, key_id=None):
        return crypto.verify_catalog_signature(self.catalog, self.signature, public or self.pem, key_id or self.key_id, openssl_value=self.openssl)

    def test_round_trip_pem_der_fingerprint_and_exact_bytes(self):
        original = crypto.canonical_json_bytes(catalog_value()).replace(b"\n", b"\r\n")
        self.catalog.write_bytes(original)
        signature = self.sign()
        self.assertEqual(signature, self.verify())
        self.assertEqual(signature, self.verify(self.der))
        self.assertEqual(self.key_id, "p256-" + hashlib.sha256(self.der.read_bytes()).hexdigest()[:16])
        material = crypto.verify_catalog_material(self.catalog, self.signature, self.pem, self.key_id, openssl_value=self.openssl)
        self.assertEqual(original, material.catalog_bytes)
        self.assertEqual(self.der.read_bytes(), material.public_der)

    def test_whitespace_and_content_tampering_fail_without_recanonicalizing(self):
        self.sign()
        self.catalog.write_bytes(self.catalog.read_bytes().replace(b"\n", b"\r\n"))
        with self.assertRaises(crypto.DistributionError):
            self.verify()
        self.catalog.write_bytes(crypto.canonical_json_bytes(catalog_value()))
        self.catalog.write_bytes(self.catalog.read_bytes().replace(b"2026-10-03", b"2026-10-04"))
        with self.assertRaises(crypto.DistributionError):
            self.verify()

    def test_wrong_public_key_and_alias_key_ids_are_rejected(self):
        self.sign()
        private, pem, der = self.root / "other.pem", self.root / "other-public.pem", self.root / "other-public.der"
        other_id = crypto.generate_key_pair(private, pem, der, self.openssl)
        with self.assertRaises(crypto.DistributionError):
            self.verify(pem)
        envelope = json.loads(self.signature.read_text())
        envelope["keyId"] = other_id
        self.signature.write_bytes(crypto.canonical_json_bytes(envelope))
        with self.assertRaises(crypto.DistributionError):
            self.verify(pem, other_id)
        for alias in ("custom-key", "p256-" + "0" * 16, None):
            with self.assertRaises(crypto.DistributionError):
                crypto.verify_catalog_signature(self.catalog, self.signature, self.pem, alias, openssl_value=self.openssl)

    def test_ace_public_key_is_never_a_codegen_trust_anchor(self):
        with self.assertRaisesRegex(crypto.DistributionError, "Ace"):
            crypto.public_key_der(crypto.ACE_PUBLIC_KEY, self.openssl)

    def test_changed_algorithm_catalog_fields_base64_and_der_are_rejected(self):
        envelope = self.sign()
        variants = []
        for key, value in (("algorithm", "ECDSA_P256_SHA512"), ("catalog", "other.json"), ("signature", "?"), ("signature", ""), ("signature", base64.b64encode(b"junk").decode())):
            variants.append(dict(envelope, **{key: value}))
        variants.append(dict(envelope, extra=1))
        variants.append({key: value for key, value in envelope.items() if key != "algorithm"})
        raw = base64.b64decode(envelope["signature"])
        variants.append(dict(envelope, signature=base64.b64encode(raw + b"\0").decode()))
        for variant in variants:
            self.signature.write_bytes(crypto.canonical_json_bytes(variant))
            with self.subTest(variant=variant), self.assertRaises(crypto.DistributionError):
                self.verify()

    def test_signature_using_a_different_digest_does_not_verify(self):
        envelope = self.sign()
        wrong = self.root / "wrong-digest.der"
        crypto._run([self.openssl, "dgst", "-sha512", "-sign", str(self.private), "-out", str(wrong), str(self.catalog)], sensitive=True)
        envelope["signature"] = base64.b64encode(wrong.read_bytes()).decode()
        self.signature.write_bytes(crypto.canonical_json_bytes(envelope))
        with self.assertRaises(crypto.DistributionError):
            self.verify()

    def test_bom_duplicate_fields_and_catalog_rollback_are_rejected(self):
        envelope = self.sign()
        original = self.catalog.read_bytes()
        for data in (b"\xef\xbb\xbf" + original, original.replace(b'"catalogVersion": 1', b'"catalogVersion": 1, "catalogVersion": 1')):
            self.catalog.write_bytes(data)
            with self.assertRaises(crypto.DistributionError):
                self.sign()
        self.catalog.write_bytes(original)
        signature_data = crypto.canonical_json_bytes(envelope)
        for data in (b"\xef\xbb\xbf" + signature_data, signature_data.replace(b'"algorithm":', b'"algorithm": "ECDSA_P256_SHA256", "algorithm":')):
            self.signature.write_bytes(data)
            with self.assertRaises(crypto.DistributionError):
                self.verify()
        self.signature.write_bytes(signature_data)
        with self.assertRaises(crypto.DistributionError):
            crypto.verify_catalog_signature(self.catalog, self.signature, self.pem, self.key_id, 2, self.openssl)

    def test_generation_refuses_existing_keys_and_git_worktree_paths(self):
        before = self.private.read_bytes()
        with self.assertRaisesRegex(crypto.DistributionError, "overwrite"):
            crypto.generate_key_pair(self.private, self.root / "new.pem", self.root / "new.der", self.openssl)
        self.assertEqual(before, self.private.read_bytes())
        for marker_is_file in (False, True):
            worktree = self.root / ("linked" if marker_is_file else "regular")
            worktree.mkdir()
            if marker_is_file:
                (worktree / ".git").write_text("gitdir: /not-a-real-test-gitdir")
            else:
                (worktree / ".git").mkdir()
            private = worktree / "nested/key.private.pem"
            with self.assertRaisesRegex(crypto.DistributionError, "outside every Git"):
                crypto.generate_key_pair(private, self.root / "new.pem", self.root / "new.der", self.openssl)
            self.assertFalse(private.exists())
            with self.assertRaisesRegex(crypto.DistributionError, "outside every Git"):
                crypto.sign_catalog(self.catalog, private, self.signature, self.key_id, self.openssl)

    def test_exclusive_output_failure_removes_partial_generated_key_material(self):
        private, pem, der = self.root / "partial.pem", self.root / "partial-public.pem", self.root / "partial-public.der"
        with mock.patch.object(crypto.os, "fsync", side_effect=OSError("test disk failure")):
            with self.assertRaises(OSError):
                crypto.generate_key_pair(private, pem, der, self.openssl)
        self.assertFalse(private.exists())
        self.assertFalse(pem.exists())
        self.assertFalse(der.exists())

    def test_signature_failure_preserves_existing_output(self):
        self.signature.write_bytes(b"previous signature")
        with self.assertRaises(crypto.DistributionError):
            crypto.sign_catalog(self.catalog, self.private, self.signature, "p256-" + "0" * 16, self.openssl)
        self.assertEqual(b"previous signature", self.signature.read_bytes())

    def test_expected_repository_and_catalog_filename_are_pinned(self):
        self.sign()
        with self.assertRaises(crypto.DistributionError):
            crypto.verify_catalog_signature(self.catalog, self.signature, self.pem, self.key_id, openssl_value=self.openssl, expected_repository="example/other")
        other = self.root / "renamed.json"
        other.write_bytes(self.catalog.read_bytes())
        with self.assertRaises(crypto.DistributionError):
            crypto.verify_catalog_signature(other, self.signature, self.pem, self.key_id, openssl_value=self.openssl)

    def test_font_module_name_cannot_redirect_codegen_validation(self):
        fake = type("FakeModule", (), {"validate_catalog": lambda *args: self.fail("font validator used")})()
        with mock.patch.dict(sys.modules, {"distribution": fake, "crypto": fake}):
            self.sign()
            self.verify()


if __name__ == "__main__":
    unittest.main()
