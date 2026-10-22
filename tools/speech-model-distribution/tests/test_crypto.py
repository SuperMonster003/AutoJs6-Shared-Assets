"""Detached catalog signatures with real OpenSSL and disposable keys created in temporary directories."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("autojs6_speech_test_support", Path(__file__).with_name("support.py"))
support = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
if not hasattr(support, "distribution"):
    _spec.loader.exec_module(support)
distribution = support.distribution
crypto = support.load("crypto")
verify_catalog = support.load("verify_catalog")
sign_catalog = support.load("sign_catalog")
DistributionError = distribution.DistributionError
SPEECH_KEY = support.REPOSITORY_ROOT / "speech-models/keys/catalog-signing-public.pem"


class CatalogCryptoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = crypto.find_openssl()
        cls.fixtures = tempfile.TemporaryDirectory(prefix="speech crypto fixtures ")
        root = Path(cls.fixtures.name)
        cls.sources = root / "sources"
        support.tts_fixture(cls.sources, root / "cache")
        support.measure(cls.sources, root / "cache", root / "assets")
        cls.catalog_value, _ = distribution.build_catalog(cls.sources, support.REPOSITORY, 1, support.TIME1)
        cls.private, cls.pem, cls.der = root / "keys/private.pem", root / "keys/public.pem", root / "keys/public.der"
        cls.key_id = crypto.generate_key_pair(cls.private, cls.pem, cls.der, cls.openssl)

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="speech-crypto-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = self.root / distribution.CATALOG_FILE
        self.signature = self.root / distribution.SIGNATURE_FILE
        self.catalog.write_bytes(distribution.canonical_json_bytes(self.catalog_value))

    def sign(self):
        return crypto.sign_catalog(self.catalog, self.private, self.signature, self.key_id, self.openssl)

    def verify(self, public=None, key_id=None, **kwargs):
        return crypto.verify_catalog_material(self.catalog, self.signature, public or self.pem, key_id or self.key_id,
                                              openssl_value=self.openssl, **kwargs).signature

    def test_round_trip_with_pem_and_der_keys_and_key_id_derivation(self):
        envelope = self.sign()
        self.assertEqual(envelope, self.verify())
        self.assertEqual(envelope, self.verify(self.der))
        self.assertEqual(self.key_id, "p256-" + hashlib.sha256(self.der.read_bytes()).hexdigest()[:16])
        self.assertEqual(hashlib.sha256(self.der.read_bytes()).hexdigest(), crypto.pem_spki_sha256(self.pem))
        self.assertEqual(distribution.canonical_json_bytes(envelope), self.signature.read_bytes())

    def test_any_byte_change_breaks_the_signature(self):
        self.sign()
        original = self.catalog.read_bytes()
        for data in (original.replace(b"\n", b"\r\n"), original.replace(b"Unit fixture", b"Unit fixturf"), original + b" "):
            self.catalog.write_bytes(data)
            with self.subTest(data=data[-20:]), self.assertRaises(DistributionError):
                self.verify()

    def test_wrong_keys_alias_ids_and_malformed_envelopes_are_rejected(self):
        envelope = self.sign()
        other = self.root / "other"
        other_id = crypto.generate_key_pair(other / "private.pem", other / "public.pem", other / "public.der", self.openssl)
        with self.assertRaises(DistributionError):
            self.verify(other / "public.pem", other_id)
        for alias in ("custom-key", "p256-" + "0" * 16):
            with self.subTest(alias=alias), self.assertRaises(DistributionError):
                self.verify(key_id=alias)
        raw = base64.b64decode(envelope["signature"])
        variants = [dict(envelope, algorithm="ECDSA_P256_SHA512"), dict(envelope, catalog="other.json"), dict(envelope, signature="?"),
                    dict(envelope, extra=1), {key: value for key, value in envelope.items() if key != "keyId"},
                    dict(envelope, signature=base64.b64encode(raw + b"\0").decode())]
        for variant in variants:
            self.signature.write_bytes(distribution.canonical_json_bytes(variant))
            with self.subTest(variant=sorted(variant)), self.assertRaises(DistributionError):
                self.verify()

    def test_ace_and_codegen_keys_are_never_speech_trust_anchors(self):
        for key in crypto.OTHER_FAMILY_KEYS:
            with self.subTest(key=key.parent.parent.name), self.assertRaisesRegex(DistributionError, "own key"):
                crypto.public_key_der(key, self.openssl)

    def test_checked_in_speech_key_is_p256_with_the_recorded_key_id(self):
        der = crypto.public_key_der(SPEECH_KEY, self.openssl)
        self.assertEqual("p256-bf5f0f579c7fbef1", crypto.key_id_for_der(der))
        self.assertEqual("bf5f0f579c7fbef188e81a02257fc3336189020273b2c69c69092cc402214f68", hashlib.sha256(der).hexdigest())
        self.assertEqual(hashlib.sha256(der).hexdigest(), crypto.pem_spki_sha256(SPEECH_KEY))

    def test_private_keys_inside_git_worktrees_are_refused(self):
        for marker_is_file in (False, True):
            worktree = self.root / ("linked" if marker_is_file else "regular")
            worktree.mkdir()
            if marker_is_file:
                (worktree / ".git").write_text("gitdir: /not-a-real-test-gitdir", encoding="utf-8")
            else:
                (worktree / ".git").mkdir()
            private = worktree / "nested/key.private.pem"
            with self.assertRaisesRegex(DistributionError, "outside every Git"):
                crypto.sign_catalog(self.catalog, private, self.signature, self.key_id, self.openssl)
            with self.assertRaisesRegex(DistributionError, "outside every Git"):
                crypto.generate_key_pair(private, self.root / f"{marker_is_file}.pem", self.root / f"{marker_is_file}.der", self.openssl)

    def test_failed_signing_preserves_existing_output_and_pins_names_and_repository(self):
        self.signature.write_bytes(b"previous signature")
        with self.assertRaises(DistributionError):
            crypto.sign_catalog(self.catalog, self.private, self.signature, "p256-" + "0" * 16, self.openssl)
        self.assertEqual(b"previous signature", self.signature.read_bytes())
        self.sign()
        with self.assertRaises(DistributionError):
            self.verify(expected_repository="other/repository")
        renamed = self.root / "renamed.json"
        renamed.write_bytes(self.catalog.read_bytes())
        with self.assertRaises(DistributionError):
            crypto.verify_catalog_material(renamed, self.signature, self.pem, self.key_id, openssl_value=self.openssl)
        with self.assertRaises(DistributionError):
            crypto.verify_catalog_material(self.catalog, self.signature, self.pem, self.key_id, 2, self.openssl)

    def test_envelope_and_file_names_follow_the_catalog_schema(self):
        self.assertEqual("catalog-v2.json", self.sign()["catalog"])
        signed = self.signature.read_bytes()
        v1_value, _ = distribution.build_catalog(self.sources, support.REPOSITORY, 1, support.TIME1, schema=1)
        v1, v1_signature = self.root / "catalog-v1.json", self.root / "catalog-v1.sig.json"
        v1.write_bytes(distribution.canonical_json_bytes(v1_value))
        envelope = crypto.sign_catalog(v1, self.private, v1_signature, self.key_id, self.openssl)
        self.assertEqual("catalog-v1.json", envelope["catalog"])
        crypto.verify_catalog_material(v1, v1_signature, self.pem, self.key_id, openssl_value=self.openssl)
        # A schema 2 catalog never passes as catalog-v1.json, and an envelope never names another schema's file.
        v1.write_bytes(self.catalog.read_bytes())
        with self.assertRaisesRegex(DistributionError, "catalog-v2.json"):
            crypto.sign_catalog(v1, self.private, v1_signature, self.key_id, self.openssl)
        with self.assertRaisesRegex(DistributionError, "catalog-v2.json"):
            crypto.verify_catalog_material(v1, self.signature, self.pem, self.key_id, openssl_value=self.openssl)
        self.signature.write_bytes(distribution.canonical_json_bytes(dict(json.loads(signed), catalog="catalog-v1.json")))
        with self.assertRaisesRegex(DistributionError, "envelope"):
            self.verify()
        self.catalog.write_bytes(distribution.canonical_json_bytes(dict(self.catalog_value, schemaVersion=3)))
        with self.assertRaisesRegex(DistributionError, "schemaVersion"):
            self.sign()

    def test_command_line_sign_and_verify_round_trip(self):
        self.assertEqual(0, sign_catalog.main([str(self.catalog), "--private-key", str(self.private), "--output", str(self.signature),
                                               "--key-id", self.key_id, "--expected-repository", support.REPOSITORY,
                                               "--openssl", self.openssl]))
        arguments = [str(self.catalog), "--signature", str(self.signature), "--public-key", str(self.pem),
                     "--expected-key-id", self.key_id, "--expected-repository", support.REPOSITORY,
                     "--source-root", str(self.sources), "--openssl", self.openssl]
        self.assertEqual(0, verify_catalog.main(arguments))
        envelope = json.loads(self.signature.read_text(encoding="utf-8"))
        envelope["keyId"] = "p256-" + "1" * 16
        self.signature.write_bytes(distribution.canonical_json_bytes(envelope))
        self.assertEqual(2, verify_catalog.main(arguments))


if __name__ == "__main__":
    unittest.main()
