from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

if __package__:
    from . import windows_access
    from .test_crypto import catalog_value, crypto, load_tool
else:
    import windows_access
    from test_crypto import catalog_value, crypto, load_tool

bootstrap = load_tool("prepare_bootstrap")


class BootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openssl = crypto.find_openssl()
        cls.keys = tempfile.TemporaryDirectory(prefix="codegen-bootstrap-test-keys-")
        directory = Path(cls.keys.name)
        cls.private, cls.pem, cls.der = directory / "private.pem", directory / "public.pem", directory / "public.der"
        cls.key_id = crypto.generate_key_pair(cls.private, cls.pem, cls.der, cls.openssl)

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codegen-bootstrap-test-")
        self.root = Path(self.temporary.name)
        self.catalog, self.signature = self.root / "catalog-v1.json", self.root / "catalog-v1.sig.json"
        self.output = self.root / "staged"
        self.catalog.write_bytes(crypto.canonical_json_bytes(catalog_value()).replace(b"\n", b"\r\n"))
        self.sign()

    def tearDown(self):
        self.temporary.cleanup()

    def sign(self):
        crypto.sign_catalog(self.catalog, self.private, self.signature, self.key_id, self.openssl)

    def prepare(self, **options):
        return bootstrap.prepare_bootstrap(self.catalog, self.signature, self.pem, self.key_id, self.output, openssl_value=self.openssl, **options)

    def host(self):
        host = self.root / "fake-host-checkout"
        (host / "app").mkdir(parents=True)
        (host / "app/build.gradle.kts").write_text("// test fixture only\n")
        (host / "version.properties").write_text("VERSION_BUILD=1\n")
        return host

    def test_staging_preserves_exact_signed_bytes_and_converts_public_spki(self):
        result = self.prepare()
        self.assertFalse(result["installed"])
        self.assertEqual({bootstrap.PUBLIC_KEY_RESOURCE, bootstrap.CATALOG_RESOURCE}, {path.name for path in self.output.iterdir()})
        self.assertEqual(self.der.read_bytes(), (self.output / bootstrap.PUBLIC_KEY_RESOURCE).read_bytes())
        envelope = json.loads((self.output / bootstrap.CATALOG_RESOURCE).read_text())
        self.assertEqual({"format", "catalogBase64", "signature"}, set(envelope))
        self.assertEqual(1, envelope["format"])
        self.assertEqual(self.catalog.read_bytes(), base64.b64decode(envelope["catalogBase64"], validate=True))
        self.assertEqual(json.loads(self.signature.read_text()), envelope["signature"])

    def test_failed_verification_leaves_previous_resources_untouched(self):
        self.prepare()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.catalog.write_bytes(self.catalog.read_bytes() + b"\n")
        with self.assertRaises(crypto.DistributionError):
            self.prepare()
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_pair_replacement_rolls_back_first_file_when_second_fails(self):
        self.output.mkdir()
        before = {bootstrap.PUBLIC_KEY_RESOURCE: b"old-key", bootstrap.CATALOG_RESOURCE: b"old-catalog"}
        for name, data in before.items():
            (self.output / name).write_bytes(data)
        replace = bootstrap.os.replace
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("test second-rename failure")
            return replace(source, target)
        with mock.patch.object(bootstrap.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.prepare()
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_host_installation_is_explicit_and_uses_only_two_verified_files(self):
        host = self.host()
        result = self.prepare(host_root=host)
        self.assertTrue(result["installed"])
        raw = host / "app/src/main/res/raw"
        self.assertEqual({bootstrap.PUBLIC_KEY_RESOURCE, bootstrap.CATALOG_RESOURCE}, {path.name for path in raw.iterdir()})
        for path in raw.iterdir():
            self.assertEqual((self.output / path.name).read_bytes(), path.read_bytes())

    def test_fork_and_test_mode_can_never_install_into_host(self):
        host = self.host()
        self.catalog.write_bytes(crypto.canonical_json_bytes(catalog_value("example/model-test")))
        self.sign()
        self.prepare(allow_test_models=True)
        for options in ({"host_root": host}, {"host_root": host, "allow_test_models": True}):
            with self.assertRaises(crypto.DistributionError):
                self.prepare(**options)
        self.assertFalse((host / "app/src/main/res/raw").exists())

    def test_staging_path_cannot_bypass_host_installation_policy(self):
        host = self.host()
        output = host / "app/src/main/res/raw"
        self.catalog.write_bytes(crypto.canonical_json_bytes(catalog_value("example/model-test")))
        self.sign()
        with self.assertRaisesRegex(crypto.DistributionError, "stage outside"):
            bootstrap.prepare_bootstrap(self.catalog, self.signature, self.pem, self.key_id, output,
                openssl_value=self.openssl, allow_test_models=True)
        self.assertFalse(output.exists())

    def test_wrong_pin_unsigned_catalog_and_invalid_host_do_not_create_outputs(self):
        with self.assertRaises(crypto.DistributionError):
            bootstrap.prepare_bootstrap(self.catalog, self.signature, self.pem, "p256-" + "0" * 16, self.output, openssl_value=self.openssl)
        self.assertFalse(self.output.exists())
        with self.assertRaises(crypto.DistributionError):
            self.prepare(host_root=self.root / "not-a-host")
        self.assertFalse(self.output.exists())
        self.signature.unlink()
        with self.assertRaises(crypto.DistributionError):
            self.prepare()
        self.assertFalse(self.output.exists())

    @windows_access.windows_mkdtemp_dacl
    def test_signature_and_staged_pair_inherit_the_parent_access_rights(self):
        # The pair is written in a mkdtemp() transaction, which used to pass its restricted DACL on.
        parent = windows_access.plain_directory(self)
        pending = parent / "pending"
        pending.mkdir()
        self.catalog = pending / "catalog-v1.json"
        self.catalog.write_bytes((self.root / "catalog-v1.json").read_bytes())
        self.signature = pending / "catalog-v1.sig.json"
        self.sign()
        self.output = parent / "staged"
        self.prepare()
        self.assertEqual({bootstrap.PUBLIC_KEY_RESOURCE, bootstrap.CATALOG_RESOURCE}, {path.name for path in self.output.iterdir()})
        windows_access.assert_inherited_access(self, pending)
        windows_access.assert_inherited_access(self, self.output)


if __name__ == "__main__":
    unittest.main()
