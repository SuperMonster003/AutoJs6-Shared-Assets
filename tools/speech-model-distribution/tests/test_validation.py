"""Source and catalog validation, including catalog history invariants."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("autojs6_speech_test_support", Path(__file__).with_name("support.py"))
support = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
if not hasattr(support, "distribution"):
    _spec.loader.exec_module(support)
distribution = support.distribution
DistributionError = distribution.DistributionError


class ValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.sources, cache = root / "sources", root / "cache"
        support.tts_fixture(cls.sources, cache)
        support.asr_fixture(cls.sources, cache)
        support.measure(cls.sources, cache, root / "assets")
        cls.catalog, cls.new_assets = distribution.build_catalog(cls.sources, support.REPOSITORY, 1, support.TIME1)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def source(self, model_id="tts.vits.unit-test"):
        return support.read_source(self.sources / model_id / "1")

    def tts_version(self, catalog):
        return next(model for model in catalog["models"] if model["kind"] == "tts")["versions"][0]

    def assert_source_invalid(self, change, pattern=None):
        value = self.source()
        change(value)
        with self.assertRaisesRegex(DistributionError, pattern or ""):
            distribution.validate_source(value)

    def assert_catalog_invalid(self, change, pattern=None, **kwargs):
        catalog = deepcopy(self.catalog)
        change(catalog)
        with self.assertRaisesRegex(DistributionError, pattern or ""):
            distribution.validate_catalog(catalog, **kwargs)

    def test_measured_sources_and_catalog_are_valid(self):
        for model_id in ("tts.vits.unit-test", "asr.online.unit-test"):
            distribution.validate_source(self.source(model_id))
        distribution.validate_catalog(self.catalog, expected_repository=support.REPOSITORY)
        self.assertEqual(2, len(self.new_assets))
        version = self.tts_version(self.catalog)
        self.assertEqual(version["mirror"]["size"], distribution.archive_size(item["size"] for item in version["files"]))
        self.assertTrue(version["sourceUrl"].endswith("/tree/speech-models-v1/speech-models/sources/tts.vits.unit-test/1"))

    def test_source_identity_kind_and_type_rules(self):
        self.assert_source_invalid(lambda value: value.update(modelId="asr.vits.unit-test"), "kind")
        self.assert_source_invalid(lambda value: value.update(modelType="sense-voice"), "modelType")
        self.assert_source_invalid(lambda value: value.update(format=2), "format")
        self.assert_source_invalid(lambda value: value.pop("speakers"), "speakers")
        self.assert_source_invalid(lambda value: value.update(extra=True), "unknown")
        self.assert_source_invalid(lambda value: value["displayName"].pop("zh-CN"), "zh-CN")
        self.assert_source_invalid(lambda value: value.update(languages=["zh", "zh"]), "languages")
        self.assert_source_invalid(lambda value: value.update(sampleRate=16000.0), "sampleRate")
        asr = support.read_source(self.sources / "asr.online.unit-test" / "1")
        asr["speakers"] = 1
        with self.assertRaisesRegex(DistributionError, "speakers"):
            distribution.validate_source(asr)

    def test_license_values_are_restricted(self):
        for change in ({"commercialUse": "yes"}, {"commercialUse": 1}, {"commercialUse": None}, {"spdx": "Apache 2.0"},
                       {"spdx": "MIT and GPL"}, {"noticeKey": "license_mit"}):
            with self.subTest(change=change):
                self.assert_source_invalid(lambda value, change=change: value["license"].update(change), "license")
        for allowed in (True, False, "unknown"):
            value = self.source()
            value["license"]["commercialUse"] = allowed
            distribution.validate_source(value)

    def test_runtime_config_must_reference_installed_files(self):
        self.assert_source_invalid(lambda value: value["runtime"]["config"].update(model="missing.onnx"), "installed file")
        self.assert_source_invalid(lambda value: value["runtime"]["config"].update(dataDir="model.onnx"), "directory")
        self.assert_source_invalid(lambda value: value["runtime"]["config"].update(lexicon="lexicon.txt"), "lexicon")
        self.assert_source_invalid(lambda value: value["runtime"]["config"].update(lexicon=["lexicon.txt", "lexicon.txt"]), "lexicon")
        self.assert_source_invalid(lambda value: value["runtime"]["config"].update(encoder="model.onnx"), "unknown")
        self.assert_source_invalid(lambda value: value["runtime"]["config"].pop("tokens"), "missing")
        self.assert_source_invalid(lambda value: value["runtime"].update(minSherpaOnnx="1.13"), "semantic")
        asr = support.read_source(self.sources / "asr.online.unit-test" / "1")
        asr["runtime"]["config"]["modelType"] = "lstm"
        with self.assertRaisesRegex(DistributionError, "modelType"):
            distribution.validate_source(asr)

    def test_upstream_must_be_pinned_sherpa_onnx_assets_covering_files_exactly(self):
        bad_urls = ("https://example.com/k2-fsa/sherpa-onnx/releases/download/tts-models/x.tar.bz2",
                    "http://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/x.tar.bz2",
                    "https://github.com/other/sherpa-onnx/releases/download/tts-models/x.tar.bz2",
                    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/x.tar.bz2?x=1",
                    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/x.zip")
        for url in bad_urls:
            with self.subTest(url=url):
                self.assert_source_invalid(lambda value, url=url: value["upstream"][0].update(url=url))
        self.assert_source_invalid(lambda value: value["upstream"][0]["members"].popitem(), "exactly")
        self.assert_source_invalid(lambda value: value["upstream"][0]["members"].update({"x/../../etc": "z"}), "segment")
        self.assert_source_invalid(lambda value: value["upstream"].append(deepcopy(value["upstream"][0])), "Duplicate")
        self.assert_source_invalid(lambda value: value["upstream"][0].update(sha256="A" * 64), "sha256")
        asr = support.read_source(self.sources / "asr.online.unit-test" / "1")
        asr["upstream"][1]["sha256"] = "0" * 64
        with self.assertRaisesRegex(DistributionError, "raw upstream"):
            distribution.validate_source(asr)

    def test_files_and_archive_records_are_consistent(self):
        self.assert_source_invalid(lambda value: value["files"].reverse(), "ascending")
        self.assert_source_invalid(lambda value: value["archive"].update(size=value["archive"]["size"] + 512), "canonical size")
        self.assert_source_invalid(lambda value: value["archive"].update(format="zip"), "tar")
        self.assert_source_invalid(lambda value: value.update(archive=None), "both")
        unmeasured = self.source()
        unmeasured.update(archive=None, files=None)
        distribution.validate_source(unmeasured, require_measured=False)

    def test_file_lists_reject_case_collisions_and_file_directory_conflicts(self):
        entry = {"size": 1, "sha256": "0" * 64}
        for paths in (["A.txt", "a.txt"], ["dir", "dir/file"], ["Dir", "dir/file"]):
            with self.subTest(paths=paths), self.assertRaises(DistributionError):
                distribution.validate_files([dict(entry, path=path) for path in sorted(paths)])

    def test_catalog_structure_urls_and_recommendation_rules(self):
        def tts(change):
            return lambda catalog: change(self.tts_version(catalog))

        self.assert_catalog_invalid(lambda catalog: catalog.update(releaseTag="speech-models-v2"), "releaseTag")
        self.assert_catalog_invalid(lambda catalog: catalog["models"].reverse(), "ascending")
        self.assert_catalog_invalid(tts(lambda version: version["mirror"].update(fileName="other.tar")), "content addressed")
        self.assert_catalog_invalid(tts(lambda version: version["mirror"].update(url=version["mirror"]["url"].replace("v1/", "v2/"))), "later release")
        self.assert_catalog_invalid(tts(lambda version: version["mirror"].update(url=version["mirror"]["url"].replace("SuperMonster003", "other"))), "mirror.url")
        self.assert_catalog_invalid(tts(lambda version: version.update(sourceUrl=version["sourceUrl"].replace("/1", "/2"))), "sourceUrl")
        self.assert_catalog_invalid(tts(lambda version: version.update(releasedAt="2027-01-01T00:00:00Z")), "releasedAt")
        self.assert_catalog_invalid(tts(lambda version: version["files"][0].update(size=version["files"][0]["size"] + 512)), "mirror.size")
        self.assert_catalog_invalid(lambda catalog: catalog["models"][0].update(recommendedVersionCode=None), "recommendedVersionCode")
        self.assert_catalog_invalid(lambda catalog: catalog["models"][0].update(kind="tts"), "kind")
        self.assert_catalog_invalid(lambda catalog: None, "repository", expected_repository="other/repository")
        catalog = deepcopy(self.catalog)
        for model in catalog["models"]:
            model["versions"][0]["revoked"] = True
            model["recommendedVersionCode"] = None
        distribution.validate_catalog(catalog)

    def test_history_is_monotonic_and_published_versions_are_immutable(self):
        current = deepcopy(self.catalog)
        current.update(catalogVersion=2, releaseTag="speech-models-v2", generatedAt=support.TIME2)
        distribution.validate_catalog(current, previous_catalog=self.catalog)
        with self.assertRaisesRegex(DistributionError, "rollback"):
            distribution.validate_catalog(self.catalog, previous_catalog=current)
        changed = deepcopy(self.catalog)
        changed["models"][0]["summary"]["en"] = "Changed"
        with self.assertRaisesRegex(DistributionError, "Same catalogVersion"):
            distribution.validate_catalog(changed, previous_catalog=self.catalog)
        mutated = deepcopy(current)
        self.tts_version(mutated)["license"]["commercialUse"] = False
        with self.assertRaisesRegex(DistributionError, "Historical"):
            distribution.validate_catalog(mutated, previous_catalog=self.catalog)
        dropped = deepcopy(current)
        dropped["models"] = dropped["models"][:1]
        with self.assertRaisesRegex(DistributionError, "Historical"):
            distribution.validate_catalog(dropped, previous_catalog=self.catalog)
        backwards = deepcopy(current)
        backwards.update(catalogVersion=3, releaseTag="speech-models-v3", generatedAt=support.TIME1)
        with self.assertRaisesRegex(DistributionError, "backwards"):
            distribution.validate_catalog(backwards, previous_catalog=current)
        revoked = deepcopy(current)
        self.tts_version(revoked)["revoked"] = True
        next(model for model in revoked["models"] if model["kind"] == "tts")["recommendedVersionCode"] = None
        distribution.validate_catalog(revoked, previous_catalog=self.catalog)
        restored = deepcopy(revoked)
        restored.update(catalogVersion=3, releaseTag="speech-models-v3")
        self.tts_version(restored).pop("revoked")
        next(model for model in restored["models"] if model["kind"] == "tts")["recommendedVersionCode"] = 1
        with self.assertRaisesRegex(DistributionError, "revoked"):
            distribution.validate_catalog(restored, previous_catalog=revoked)

    def test_json_parsing_is_strict(self):
        for data in (b'{"a": 1, "a": 2}', b'{"a": NaN}', b"\xef\xbb\xbf{}", b"[]", b"{"):
            with self.subTest(data=data), self.assertRaises(DistributionError):
                distribution.parse_json(data)
        self.assertEqual(b'{\n  "a": 1,\n  "b": "x"\n}\n', distribution.canonical_json_bytes({"b": "x", "a": 1}))


if __name__ == "__main__":
    unittest.main()
