"""Catalog building from sources, source-tree rules, pending output and the verify_catalog CLI."""

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("autojs6_speech_test_support", Path(__file__).with_name("support.py"))
support = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
if not hasattr(support, "distribution"):
    _spec.loader.exec_module(support)
distribution = support.distribution
DistributionError = distribution.DistributionError
build_catalog = support.load("build_catalog")
crypto = support.load("crypto")
verify_catalog = support.load("verify_catalog")


class CatalogTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources, self.cache = self.root / "sources", self.root / "cache"
        self.tts = support.tts_fixture(self.sources, self.cache)
        support.asr_fixture(self.sources, self.cache)
        support.upstream_only_fixture(self.sources, self.cache)
        support.measure(self.sources, self.cache, self.root / "assets")

    def build(self, name, version=1, previous=None, generated=support.TIME1):
        output = self.root / name
        arguments = ["--source-root", str(self.sources), "--output", str(output), "--catalog-version", str(version),
                     "--generated-at", generated]
        if previous:
            arguments += ["--previous-catalog", str(previous)]
        return build_catalog.main(arguments), output

    def test_pending_output_is_reproducible_and_never_overwritten(self):
        code, first = self.build("pending")
        self.assertEqual(0, code)
        self.assertEqual({"catalog-v1.json", "release-assets.txt", "preparation.json", distribution.OUTPUT_MARKER},
                         {path.name for path in first.iterdir()})
        _code, second = self.build("again")
        for name in ("catalog-v1.json", "release-assets.txt", "preparation.json"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
        names = (first / "release-assets.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(names))
        self.assertTrue(all(name.startswith("autojs6-speech-") and name.endswith(".tar") for name in names))
        self.assertFalse(any(support.UPSTREAM_ONLY_ID in name for name in names))
        catalog = distribution.read_json(first / "catalog-v1.json")
        self.assertEqual(3, len(catalog["models"]))
        self.assertEqual([(support.UPSTREAM_ONLY_ID, 1)], distribution.upstream_only_versions(catalog))
        preparation = distribution.read_json(first / "preparation.json")
        self.assertEqual((2, 1), (preparation["releaseAssetCount"], preparation["upstreamOnlyVersions"]))
        before = (first / "catalog-v1.json").read_bytes()
        self.assertEqual(2, self.build("pending")[0])
        self.assertEqual(before, (first / "catalog-v1.json").read_bytes())

    def test_next_catalog_keeps_published_urls_and_only_lists_new_archives(self):
        _code, v1 = self.build("v1")
        support.tts_fixture(self.sources, self.cache, code=2, members=dict(support.tts_members(), **{"model.onnx": b"retrained"}))
        support.measure(self.sources, self.cache, self.root / "assets")
        code, v2 = self.build("v2", 2, v1 / "catalog-v1.json", support.TIME2)
        self.assertEqual(0, code)
        catalog = distribution.read_json(v2 / "catalog-v1.json")
        tts = next(model for model in catalog["models"] if model["kind"] == "tts")
        self.assertEqual([1, 2], [version["versionCode"] for version in tts["versions"]])
        self.assertIn("/speech-models-v1/", tts["versions"][0]["mirror"]["url"])
        self.assertIn("/speech-models-v2/", tts["versions"][1]["mirror"]["url"])
        self.assertEqual(2, tts["recommendedVersionCode"])
        self.assertEqual([tts["versions"][1]["mirror"]["fileName"]], (v2 / "release-assets.txt").read_text(encoding="utf-8").splitlines())
        carried = next(model for model in catalog["models"] if model["modelId"] == support.UPSTREAM_ONLY_ID)["versions"][0]
        self.assertIsNone(carried["mirror"])
        self.assertIn("/tree/speech-models-v1/", carried["sourceUrl"])
        self.assertEqual(2, self.build("skip", 3, v1 / "catalog-v1.json", support.TIME2)[0])
        self.assertEqual(2, self.build("no-previous", 2)[0])

    def test_published_versions_cannot_change_or_lose_sources(self):
        _code, v1 = self.build("v1")
        previous = distribution.read_json(v1 / "catalog-v1.json")
        value = support.read_source(self.tts)
        value["license"]["commercialUse"] = False
        (self.tts / "source.json").write_bytes(distribution.canonical_json_bytes(value))
        with self.assertRaisesRegex(DistributionError, "immutable"):
            distribution.build_catalog(self.sources, support.REPOSITORY, 2, support.TIME2, previous_catalog=previous)
        value["license"]["commercialUse"] = True
        archive, value["mirror"], value["archive"] = value["archive"], False, None
        (self.tts / "source.json").write_bytes(distribution.canonical_json_bytes(value))
        with self.assertRaisesRegex(DistributionError, "immutable"):
            distribution.build_catalog(self.sources, support.REPOSITORY, 2, support.TIME2, previous_catalog=previous)
        value["mirror"], value["archive"] = True, archive
        value["revoked"] = True
        (self.tts / "source.json").write_bytes(distribution.canonical_json_bytes(value))
        catalog, assets = distribution.build_catalog(self.sources, support.REPOSITORY, 2, support.TIME2, previous_catalog=previous)
        self.assertEqual([], assets)
        tts = next(model for model in catalog["models"] if model["kind"] == "tts")
        self.assertIsNone(tts["recommendedVersionCode"])
        shutil.rmtree(self.sources / "asr.online.unit-test")
        with self.assertRaisesRegex(DistributionError, "lost their sources"):
            distribution.build_catalog(self.sources, support.REPOSITORY, 2, support.TIME2, previous_catalog=previous)

    def test_source_tree_accepts_only_reviewed_text_files(self):
        for name, content in (("model.onnx", b"binary"), ("notes.txt", b"text"), ("LICENSE.bin", b"x")):
            path = self.tts / name
            path.write_bytes(content)
            with self.subTest(name=name), self.assertRaisesRegex(DistributionError, "must contain only"):
                distribution.load_sources(self.sources)
            path.unlink()
        (self.tts / "LICENSE-extra").write_bytes(b"\0binary")
        with self.assertRaisesRegex(DistributionError, "text"):
            distribution.load_sources(self.sources)
        (self.tts / "LICENSE-extra").unlink()
        (self.tts / "MODEL_CARD.md").unlink()
        with self.assertRaisesRegex(DistributionError, "must contain only"):
            distribution.load_sources(self.sources)
        (self.tts / "MODEL_CARD.md").write_text("# card\n", encoding="utf-8")
        renamed = self.sources / "tts.vits.renamed"
        (self.sources / "tts.vits.unit-test").rename(renamed)
        with self.assertRaisesRegex(DistributionError, "identity"):
            distribution.load_sources(self.sources)
        renamed.rename(self.sources / "tts.vits.unit-test")
        (self.sources / "README.md").write_text("stray", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "Unexpected entry"):
            distribution.load_sources(self.sources)

    def test_verify_catalog_checks_canonical_bytes_sources_and_signature_arguments(self):
        _code, pending = self.build("pending")
        catalog = pending / "catalog-v1.json"
        arguments = [str(catalog), "--expected-repository", support.REPOSITORY, "--source-root", str(self.sources)]
        self.assertEqual(0, verify_catalog.main(arguments))
        catalog.write_bytes(catalog.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(2, verify_catalog.main(arguments))
        catalog.write_bytes(catalog.read_bytes().replace(b"\r\n", b"\n"))
        value = support.read_source(self.tts)
        value["summary"]["en"] = "Edited after review"
        (self.tts / "source.json").write_bytes(distribution.canonical_json_bytes(value))
        self.assertEqual(2, verify_catalog.main(arguments))
        self.assertEqual(0, verify_catalog.main(arguments[:3]))
        with self.assertRaises(SystemExit):
            verify_catalog.main([str(catalog), "--signature", str(catalog)])


@support.windows_mkdtemp_dacl
class PendingAccessTest(unittest.TestCase):
    def test_pending_output_archives_and_signature_inherit_the_parent_access_rights(self):
        # mkdtemp() staging used to leave only SYSTEM, Administrators and OWNER RIGHTS on all of these.
        parent = support.plain_directory(self)
        sources, cache = parent / "sources", parent / "cache"
        support.tts_fixture(sources, cache)
        support.measure(sources, cache, parent / "assets")
        pending = parent / "pending"
        self.assertEqual(0, build_catalog.main(["--source-root", str(sources), "--output", str(pending),
                                                "--catalog-version", "1", "--generated-at", support.TIME1]))
        openssl = crypto.find_openssl()
        private, pem, der = parent / "keys/private.pem", parent / "keys/public.pem", parent / "keys/public.der"
        key_id = crypto.generate_key_pair(private, pem, der, openssl)
        crypto.sign_catalog(pending / distribution.CATALOG_FILE, private, pending / distribution.SIGNATURE_FILE, key_id, openssl)
        support.assert_inherited_access(self, parent / "assets")
        support.assert_inherited_access(self, pending)


if __name__ == "__main__":
    unittest.main()
