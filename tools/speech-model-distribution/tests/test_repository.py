"""Checked-in speech model data: sources, pending v1 catalog, license audit, schemas and CI wiring."""

import importlib.util
import json
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
check_docs = support.load("check_docs")
ROOT = support.REPOSITORY_ROOT
FAMILY = ROOT / "speech-models"
PENDING = FAMILY / "catalogs/pending/v1"
NOTICE_FOR = {True: "speech_model_license_commercial", False: "speech_model_license_non_commercial",
              "unknown": "speech_model_license_unknown"}


def schema(name):
    return distribution.read_json(FAMILY / "schemas" / name)


class CheckedInDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = distribution.load_sources(FAMILY / "sources")
        cls.catalog = distribution.read_json(PENDING / "catalog-v1.json")

    def test_sources_are_measured_text_only_and_license_complete(self):
        self.assertEqual(10, len(self.sources))
        for folder, source in self.sources:
            names = {path.name for path in folder.iterdir()}
            paths = {item["path"] for item in source["files"]}
            with self.subTest(model=source["modelId"]):
                self.assertTrue({"source.json", "MODEL_CARD.md"} <= names)
                self.assertEqual(any(path.startswith("espeak-ng-data/") for path in paths), "LICENSE-espeak-ng-data" in names)
                self.assertNotIn("test_wavs", " ".join(paths))
                self.assertEqual("1.13.8", source["runtime"]["minSherpaOnnx"])
                self.assertEqual(NOTICE_FOR[source["license"]["commercialUse"]], source["license"]["noticeKey"])
                self.assertEqual(distribution.canonical_json_bytes(source), (folder / "source.json").read_bytes())

    def test_pending_catalog_is_canonical_and_reproduced_from_sources(self):
        data = (PENDING / "catalog-v1.json").read_bytes()
        self.assertEqual(distribution.canonical_json_bytes(self.catalog), data)
        distribution.validate_catalog(self.catalog, expected_repository=distribution.DEFAULT_REPOSITORY)
        rebuilt, assets = distribution.build_catalog(FAMILY / "sources", self.catalog["repository"], 1, self.catalog["generatedAt"])
        self.assertEqual(data, distribution.canonical_json_bytes(rebuilt))
        self.assertEqual(assets, (PENDING / "release-assets.txt").read_text(encoding="utf-8").splitlines())
        preparation = distribution.read_json(PENDING / "preparation.json")
        self.assertEqual(len(assets), preparation["releaseAssetCount"])
        self.assertEqual(sum(version["mirror"]["size"] for model in self.catalog["models"] for version in model["versions"]),
                         preparation["releaseAssetBytes"])
        self.assertTrue(preparation["unsigned"])

    def test_license_audit_matches_every_catalog_model(self):
        audit = distribution.read_json(FAMILY / "audits/license-audit-v1.json")
        self.assertEqual(distribution.canonical_json_bytes(audit), (FAMILY / "audits/license-audit-v1.json").read_bytes())
        by_id = {entry["modelId"]: entry for entry in audit["models"]}
        catalog = {model["modelId"]: model["versions"][0] for model in self.catalog["models"]}
        self.assertEqual(set(catalog), set(by_id))
        for model_id, version in catalog.items():
            entry = by_id[model_id]
            with self.subTest(model=model_id):
                self.assertEqual((version["versionCode"], version["license"]["spdx"], version["license"]["commercialUse"],
                                  version["license"]["noticeKey"]),
                                 (entry["versionCode"], entry["spdx"], entry["commercialUse"], entry["noticeKey"]))
                links = entry["weights"]["evidence"] + [url for item in entry["trainingData"] for url in item["evidence"]]
                self.assertTrue(links and all(url.startswith("https://") for url in links))
                if version["license"]["commercialUse"] is False:
                    restricted = any(item["commercialRestriction"] is True for item in entry["trainingData"])
                    self.assertTrue(restricted, "false requires a named restricted dataset")
        self.assertEqual(set(NOTICE_FOR.values()), set(audit["policy"]["noticeKeys"]))
        self.assertIs(False, by_id["tts.matcha.icefall.zh-baker"]["commercialUse"])

    def test_schemas_follow_the_validator(self):
        catalog = schema("catalog-v1.schema.json")
        version = catalog["$defs"]["version"]
        model = catalog["properties"]["models"]["items"]
        self.assertEqual(list(distribution.CATALOG_FIELDS), catalog["required"])
        self.assertEqual(list(distribution.MODEL_FIELDS), model["required"])
        self.assertEqual(list(distribution.VERSION_REQUIRED), version["required"])
        self.assertEqual(set(distribution.VERSION_REQUIRED + distribution.VERSION_OPTIONAL), set(version["properties"]))
        source = schema("model-source-v1.schema.json")
        self.assertEqual(list(distribution.SOURCE_REQUIRED), source["required"])
        self.assertEqual(set(distribution.SOURCE_REQUIRED + distribution.SOURCE_OPTIONAL), set(source["properties"]))
        for document in (catalog, source):
            self.assertEqual(list(distribution.MODEL_TYPES), document["$defs"]["modelType"]["enum"])
            rules = {rule["if"]["properties"]["modelType"]["const"]: rule["then"]["properties"]["runtime"]["properties"]["config"]
                     for rule in document["$defs"]["configByModelType"]["allOf"]}
            for model_type, specification in distribution.MODEL_TYPES.items():
                self.assertEqual(list(specification["required"]), rules[model_type]["required"])
                self.assertEqual(set(specification["required"] + specification["optional"]), set(rules[model_type]["properties"]))
        signature = schema("signature-v1.schema.json")
        codegen = distribution.read_json(ROOT / "codegen-models/schemas/signature-v1.schema.json")
        strip = lambda value: {key: item for key, item in value.items() if key not in ("$id", "title")}
        self.assertEqual(strip(codegen), strip(signature))
        for name in ("catalog-v1.schema.json", "model-source-v1.schema.json", "signature-v1.schema.json"):
            self.assertEqual(distribution.canonical_json_bytes(schema(name)), (FAMILY / "schemas" / name).read_bytes())

    def test_documents_ci_and_ignore_rules(self):
        self.assertGreaterEqual(check_docs.check(ROOT), 12)
        markdown = (ROOT / ".github/workflows/markdown.yml").read_text(encoding="utf-8")
        self.assertIn("python tools/speech-model-distribution/check_docs.py", markdown)
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("build/", ignored)
        self.assertIn("*.private.pem", ignored)


class DocumentCheckTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / ".python", self.root / ".python", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(FAMILY, self.root / "speech-models")
        (self.root / "tools/speech-model-distribution").mkdir(parents=True)
        shutil.copyfile(support.TOOL_DIR / "README.md", self.root / "tools/speech-model-distribution/README.md")
        self.readme = self.root / "speech-models/README.md"

    def test_valid_copy_passes_and_defects_are_reported(self):
        self.assertGreaterEqual(check_docs.check(self.root), 12)
        original = self.readme.read_text(encoding="utf-8")
        defects = (original.replace("Signing key", "Signing key" + chr(0xFF0C)),
                   original.replace("(schemas/catalog-v1.schema.json)", "(schemas/missing.json)"),
                   original.replace("p256-bf5f0f579c7fbef1", "p256-0000000000000000"),
                   original.replace("SPKI DER SHA-256: `bf5f", "SPKI DER SHA-256: `0f5f"))
        for text in defects:
            self.readme.write_text(text, encoding="utf-8")
            with self.assertRaises(check_docs.DocumentError):
                check_docs.check(self.root)
        self.readme.write_text(original, encoding="utf-8")
        card = next((self.root / "speech-models/sources").glob("*/1/MODEL_CARD.md"))
        card.write_text(card.read_text(encoding="utf-8") + "\n" + chr(0x3002) + "\n", encoding="utf-8")
        with self.assertRaises(check_docs.DocumentError):
            check_docs.check(self.root)


if __name__ == "__main__":
    unittest.main()
