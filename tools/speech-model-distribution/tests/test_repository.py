"""Checked-in speech model data: sources, pending v3 catalogs (schema 3 and 2), signed v2 catalog, v1 / v2 history, license audits, schemas and CI wiring."""

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
PENDING = FAMILY / "catalogs/pending/v3"
PENDING_V2 = FAMILY / "catalogs/pending/v2"
HISTORY_V1 = FAMILY / "catalogs/history/v1"
HISTORY_V2 = FAMILY / "catalogs/history/v2"
NOTICE_FOR = {True: "speech_model_license_commercial", False: "speech_model_license_non_commercial",
              "unknown": "speech_model_license_unknown"}
# Catalog v3 adds a notice for "unknown" when the publisher names no training data (decision D131, Q80).
UNKNOWN_DATA = "speech_model_license_unknown_data"
PENGCHENG = "asr.zipformer-streaming.ar-en-id-ja-ru-th-vi-zh.2025-02-10.int8"
NEMO_ES = "asr.nemo-transducer.es.2026-05-03.int8"
MIRO_V2 = "tts.vits.piper.ar-jo-sa-miro-v2-high.int8"
ZH_2025 = "asr.zipformer-streaming.zh.2025-06-30.int8"
UPSTREAM_ONLY = ["asr.zipformer-streaming.ko.2024-06-16.int8", ZH_2025, MIRO_V2]
SENSE_VOICE = "asr.sense-voice.zh-en-ja-ko-yue.2024-07-17.int8"
PUNCT_EN = "punct.cnn-bilstm.en.2024-08-06.int8"
SPEAKER = "speaker.eres2net.3dspeaker.en-voxceleb"
SEGMENT = "segment.pyannote.3-0"
WHISPER = ["langid.whisper.base.int8", "langid.whisper.tiny.int8"]
TAGGER = "tagger.ced.mini.int8"
# The versions that need catalog schema 3 (plugin roadmap P8.3, P8.4): catalog-v2.json of release 3 leaves them out.
SCHEMA_3 = [SPEAKER, SEGMENT, *WHISPER, TAGGER]


def schema(name):
    return distribution.read_json(FAMILY / "schemas" / name)


class CheckedInDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = distribution.load_sources(FAMILY / "sources")
        cls.catalog = distribution.read_json(PENDING / distribution.CATALOG_FILE)
        cls.pending_v2 = distribution.read_json(PENDING / "catalog-v2.json")
        cls.v1 = distribution.read_json(HISTORY_V1 / "catalog-v1.json")
        cls.v2 = distribution.read_json(HISTORY_V2 / "catalog-v2.json")

    def test_sources_are_measured_text_only_and_license_complete(self):
        self.assertEqual(30, len(self.sources))
        for folder, source in self.sources:
            names = {path.name for path in folder.iterdir()}
            paths = {item["path"] for item in source["files"]}
            with self.subTest(model=source["modelId"]):
                self.assertTrue({"source.json", "MODEL_CARD.md"} <= names)
                self.assertEqual(any(path.startswith("espeak-ng-data/") for path in paths), "LICENSE-espeak-ng-data" in names)
                self.assertNotIn("test_wavs", " ".join(paths))
                self.assertEqual("1.13.8", source["runtime"]["minSherpaOnnx"])
                expected = UNKNOWN_DATA if source["modelId"] in (PENGCHENG, *WHISPER) else NOTICE_FOR[source["license"]["commercialUse"]]
                self.assertEqual(expected, source["license"]["noticeKey"])
                self.assertEqual(source["mirror"], source["archive"] is not None)
                self.assertEqual(distribution.canonical_json_bytes(source), (folder / "source.json").read_bytes())
        self.assertEqual(UPSTREAM_ONLY, [source["modelId"] for _folder, source in self.sources if not source["mirror"]])
        by_id = {source["modelId"]: source for _folder, source in self.sources}
        self.assertNotIn("asr.sense-voice.zh-en-ja-ko-yue.2025-09-09.int8", by_id)
        self.assertIs(True, by_id[SENSE_VOICE]["license"]["commercialUse"])
        self.assertEqual("LicenseRef-FunASR-Model-License-1.1", by_id[SENSE_VOICE]["license"]["spdx"])
        self.assertEqual(["LICENSE", "README.md", "model.int8.onnx", "tokens.txt"], [item["path"] for item in by_id[SENSE_VOICE]["files"]])
        self.assertIn("FunASR Model Open Source License Agreement",
                      (FAMILY / "sources" / SENSE_VOICE / "1/LICENSE").read_text(encoding="utf-8"))
        # Schema 2 additions: punct versions carry no sampleRate, and an archive packed from "." keeps its "./" members.
        punct = sorted(source["modelType"] for _folder, source in self.sources if source["kind"] == "punct")
        self.assertEqual(["cnn-bilstm", "ct-transformer"], punct)
        self.assertFalse(any("sampleRate" in source for _folder, source in self.sources if source["kind"] == "punct"))
        self.assertTrue(all(member.startswith(distribution.MEMBER_PREFIX) for member in by_id[PUNCT_EN]["upstream"][0]["members"]))
        # Catalog v3 (P8.2): the NeMo recognizer uses the offline-transducer type added to schema 2.
        self.assertEqual("offline-transducer", by_id[NEMO_ES]["modelType"])
        self.assertEqual("nemo_transducer", by_id[NEMO_ES]["runtime"]["config"]["modelType"])
        self.assertTrue(all(member.startswith(distribution.MEMBER_PREFIX) for member in by_id[NEMO_ES]["upstream"][0]["members"]))
        # Schema 3 (P8.3): the speaker kind, one raw ONNX file of the upstream speaker-recongition-models release.
        self.assertEqual([SPEAKER], [source["modelId"] for _folder, source in self.sources if source["kind"] == "speaker"])
        self.assertEqual(("speaker-embedding", 16000, {"model": "model.onnx"}, ["model.onnx"], "file"),
                         (by_id[SPEAKER]["modelType"], by_id[SPEAKER]["sampleRate"], by_id[SPEAKER]["runtime"]["config"],
                          [item["path"] for item in by_id[SPEAKER]["files"]], by_id[SPEAKER]["upstream"][0]["format"]))

    def test_pending_catalog_is_canonical_and_reproduced_from_sources(self):
        data = (PENDING / distribution.CATALOG_FILE).read_bytes()
        self.assertEqual(distribution.canonical_json_bytes(self.catalog), data)
        distribution.validate_catalog(self.catalog, previous_catalog=self.v2, expected_repository=distribution.DEFAULT_REPOSITORY)
        self.assertEqual((3, 3, "speech-models-v3"),
                         (self.catalog["schemaVersion"], self.catalog["catalogVersion"], self.catalog["releaseTag"]))
        rebuilt, assets = distribution.build_catalog(FAMILY / "sources", self.catalog["repository"], 3, self.catalog["generatedAt"],
                                                     previous_catalog=self.v2)
        self.assertEqual(data, distribution.canonical_json_bytes(rebuilt))
        self.assertEqual(assets, (PENDING / "release-assets.txt").read_text(encoding="utf-8").splitlines())
        self.assertEqual(10, len(assets))
        self.assertEqual(30, len(self.catalog["models"]))
        self.assertEqual([(model_id, 1) for model_id in UPSTREAM_ONLY], distribution.upstream_only_versions(self.catalog))
        # Archives of catalogs v1 and v2 stay on their releases; v3 uploads only the archives it introduces.
        old = {model["modelId"]: model for model in self.v2["models"]}
        self.assertFalse(any(model_id in name for name in assets for model_id in set(old) | set(UPSTREAM_ONLY)))
        self.assertEqual(old, {model["modelId"]: model for model in self.catalog["models"] if model["modelId"] in old})
        preparation = distribution.read_json(PENDING / "preparation.json")
        self.assertEqual(len(assets), preparation["releaseAssetCount"])
        self.assertEqual(3, preparation["upstreamOnlyVersions"])
        self.assertEqual(sum(version["mirror"]["size"] for model in self.catalog["models"] for version in model["versions"]
                             if version["mirror"] is not None and version["mirror"]["fileName"] in assets),
                         preparation["releaseAssetBytes"])
        self.assertTrue(preparation["unsigned"])

    def test_pending_catalog_v2_is_the_same_release_without_newer_kinds(self):
        # Decision D127: release 3 also publishes catalog-v2.json for plugins 1.2.0 and older, without the kinds of schema 3.
        data = (PENDING / "catalog-v2.json").read_bytes()
        self.assertEqual(distribution.canonical_json_bytes(self.pending_v2), data)
        distribution.validate_catalog(self.pending_v2, previous_catalog=self.v2, expected_repository=distribution.DEFAULT_REPOSITORY)
        self.assertEqual((2, 3, "speech-models-v3"),
                         (self.pending_v2["schemaVersion"], self.pending_v2["catalogVersion"], self.pending_v2["releaseTag"]))
        rebuilt, assets = distribution.build_catalog(FAMILY / "sources", self.pending_v2["repository"], 3, self.pending_v2["generatedAt"],
                                                     previous_catalog=self.v2, schema=2)
        self.assertEqual(data, distribution.canonical_json_bytes(rebuilt))
        self.assertEqual([model for model in self.catalog["models"] if model["modelId"] not in SCHEMA_3], self.pending_v2["models"])
        self.assertEqual(SCHEMA_3, sorted((model["modelId"] for model in self.catalog["models"] if model["kind"] in ("langid", "segment", "speaker", "tagger")),
                                          key=SCHEMA_3.index))
        released = (PENDING / "release-assets.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual([name for name in released if not any(f"-{model_id}-v1-" in name for model_id in SCHEMA_3)], assets)

    def test_catalog_v1_is_frozen_with_a_signed_history_copy(self):
        catalogs = FAMILY / "catalogs"
        for name in ("catalog-v1.json", "catalog-v1.sig.json"):
            self.assertEqual((catalogs / name).read_bytes(), (HISTORY_V1 / name).read_bytes())
        self.assertEqual((1, 1, 10), (self.v1["schemaVersion"], self.v1["catalogVersion"], len(self.v1["models"])))
        distribution.validate_catalog(self.v1, expected_repository=distribution.DEFAULT_REPOSITORY)

    def test_promoted_catalog_v2_is_the_reviewed_candidate_with_a_valid_signature(self):
        catalogs = FAMILY / "catalogs"
        for name in ("catalog-v2.json", "catalog-v2.sig.json"):
            self.assertEqual((PENDING_V2 / name).read_bytes(), (catalogs / name).read_bytes())
            self.assertEqual((HISTORY_V2 / name).read_bytes(), (catalogs / name).read_bytes())
        self.assertEqual((2, 2, 19), (self.v2["schemaVersion"], self.v2["catalogVersion"], len(self.v2["models"])))
        crypto = support.load("crypto")
        crypto.verify_catalog_material(
            catalogs / "catalog-v2.json", catalogs / "catalog-v2.sig.json",
            FAMILY / "keys/catalog-signing-public.pem", "p256-bf5f0f579c7fbef1",
            minimum_catalog_version=2, expected_repository=distribution.DEFAULT_REPOSITORY)

    def test_license_audits_match_every_catalog_model(self):
        first = self.check_audit("license-audit-v1.json", self.v1)
        self.assertEqual(2, len(first["decisions"]))
        audit = self.check_audit("license-audit-v2.json", self.v2)
        self.assertEqual(first["decisions"], audit["decisions"][:2])
        self.assertEqual(5, len(audit["decisions"]))
        carried = {entry["modelId"] for entry in first["models"]}
        self.assertEqual(first["models"], [entry for entry in audit["models"] if entry["modelId"] in carried])
        third = self.check_audit("license-audit-v3.json", self.catalog, set(NOTICE_FOR.values()) | {UNKNOWN_DATA})
        self.assertEqual(audit["decisions"], third["decisions"][:5])
        self.assertEqual(10, len(third["decisions"]))
        self.assertEqual(audit["models"], [entry for entry in third["models"] if entry["modelId"] in {item["modelId"] for item in audit["models"]}])
        pengcheng = next(entry for entry in third["models"] if entry["modelId"] == PENGCHENG)
        self.assertEqual(["undisclosed"], [item["commercialRestriction"] for item in pengcheng["trainingData"]])
        by_id = {entry["modelId"]: entry for entry in third["models"]}
        # MSDWild is for research only, so the segmentation model is false by the policy; Whisper names no training data.
        self.assertEqual((False, ["MSDWild"]), (by_id[SEGMENT]["commercialUse"],
                                                [item["name"] for item in by_id[SEGMENT]["trainingData"] if item["commercialRestriction"] is True]))
        self.assertEqual([("unknown", UNKNOWN_DATA)] * 2, [(by_id[model_id]["commercialUse"], by_id[model_id]["noticeKey"]) for model_id in WHISPER])
        self.assertEqual(["class_labels_indices.csv"], [item["name"] for item in by_id[TAGGER]["bundledComponents"]])
        for entry in audit["models"]:
            if entry["modelId"].startswith("tts.vits.piper."):
                with self.subTest(model=entry["modelId"]):
                    self.assertIs(False, entry["commercialUse"])
                    self.assertTrue(any(item["name"].startswith("Lessac Blizzard 2013") for item in entry["trainingData"]))

    def check_audit(self, name, catalog_value, notice_keys=frozenset(NOTICE_FOR.values())):
        audit = distribution.read_json(FAMILY / "audits" / name)
        self.assertEqual(distribution.canonical_json_bytes(audit), (FAMILY / "audits" / name).read_bytes())
        self.assertEqual(catalog_value["catalogVersion"], audit["catalogVersion"])
        upstream_only = {model_id for model_id, _code in distribution.upstream_only_versions(catalog_value)}
        by_id = {entry["modelId"]: entry for entry in audit["models"]}
        catalog = {model["modelId"]: model["versions"][0] for model in catalog_value["models"]}
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
        self.assertEqual(set(notice_keys), set(audit["policy"]["noticeKeys"]))
        self.assertIs(False, by_id["tts.matcha.icefall.zh-baker"]["commercialUse"])
        self.assertIs(True, by_id[SENSE_VOICE]["commercialUse"])
        self.assertEqual({"upstream-only"}, {by_id[model_id]["distribution"] for model_id in upstream_only})
        self.assertEqual([], by_id[ZH_2025]["openQuestions"])
        self.assertEqual({"mirror"}, {entry["distribution"] for key, entry in by_id.items() if key not in upstream_only})
        self.assertEqual({"mirror", "upstream-only"}, set(audit["policy"]["distribution"]))
        return audit

    def test_schemas_follow_the_validator(self):
        catalog = schema("catalog-v3.schema.json")
        version = catalog["$defs"]["version"]
        model = catalog["properties"]["models"]["items"]
        self.assertEqual(distribution.CATALOG_SCHEMA_VERSION, catalog["properties"]["schemaVersion"]["const"])
        self.assertEqual(list(distribution.KINDS), catalog["$defs"]["kind"]["enum"])
        self.assertEqual(list(distribution.CATALOG_FIELDS), catalog["required"])
        self.assertEqual(list(distribution.MODEL_FIELDS), model["required"])
        self.assertEqual(list(distribution.VERSION_REQUIRED), version["required"])
        self.assertEqual(set(distribution.VERSION_REQUIRED + distribution.VERSION_OPTIONAL), set(version["properties"]))
        mirror = version["properties"]["mirror"]["oneOf"]
        self.assertEqual({"type": "null"}, mirror[0])
        self.assertEqual(list(distribution.MIRROR_FIELDS), mirror[1]["required"])
        source = schema("model-source-v1.schema.json")
        self.assertEqual(list(distribution.SOURCE_REQUIRED), source["required"])
        self.assertEqual(set(distribution.SOURCE_REQUIRED + distribution.SOURCE_OPTIONAL), set(source["properties"]))
        self.assertEqual("boolean", source["properties"]["mirror"]["type"])
        self.assertIn({"if": {"properties": {"mirror": {"const": False}}, "required": ["mirror"]},
                       "then": {"properties": {"archive": {"type": "null"}}}}, source["allOf"])
        for document in (catalog, source):
            self.assertEqual(list(distribution.MODEL_TYPES), document["$defs"]["modelType"]["enum"])
            rules = {rule["if"]["properties"]["modelType"]["const"]: rule["then"]["properties"]["runtime"]["properties"]["config"]
                     for rule in document["$defs"]["configByModelType"]["allOf"]}
            for model_type, specification in distribution.MODEL_TYPES.items():
                self.assertEqual(list(specification["required"]), rules[model_type]["required"])
                self.assertEqual(set(specification["required"] + specification["optional"]), set(rules[model_type]["properties"]))
            self.assertEqual([name for name, specification in distribution.MODEL_TYPES.items() if specification["kind"] == "punct"],
                             document["$defs"]["sampleRateByKind"]["if"]["properties"]["modelType"]["enum"])
            members = document["$defs"]["upstreamPart"]["oneOf"][0]["properties"]["members"]
            self.assertEqual({"$ref": "#/$defs/upstreamMember"}, members["propertyNames"])
            self.assertEqual("^(?:\\./)?" + document["$defs"]["path"]["pattern"][1:], document["$defs"]["upstreamMember"]["pattern"])
        # catalog-v2.schema.json is frozen with schema 2: everything of catalog-v3.schema.json except the speaker kind and type.
        older = lambda names: [name for name in names if distribution.SCHEMA_INTRODUCED.get(name, 1) <= 2]
        frozen = schema("catalog-v2.schema.json")
        self.assertEqual(2, frozen["properties"]["schemaVersion"]["const"])
        self.assertEqual(older(distribution.KINDS), frozen["$defs"]["kind"]["enum"])
        self.assertEqual(older(distribution.MODEL_TYPES), frozen["$defs"]["modelType"]["enum"])
        self.assertEqual(older(distribution.MODEL_TYPES),
                         [rule["if"]["properties"]["modelType"]["const"] for rule in frozen["$defs"]["configByModelType"]["allOf"]])
        # catalog-v1.schema.json is frozen with schema 1: no punct kind or types, sampleRate always required.
        frozen = schema("catalog-v1.schema.json")
        first = lambda names: [name for name in names if distribution.SCHEMA_INTRODUCED.get(name, 1) == 1]
        self.assertEqual(1, frozen["properties"]["schemaVersion"]["const"])
        self.assertEqual(first(distribution.KINDS), frozen["$defs"]["kind"]["enum"])
        self.assertEqual(first(distribution.MODEL_TYPES), frozen["$defs"]["modelType"]["enum"])
        self.assertEqual(list(distribution.VERSION_REQUIRED),
                         [field for field in frozen["$defs"]["version"]["required"] if field != "sampleRate"])
        self.assertEqual({"$ref": "#/$defs/path"}, frozen["$defs"]["upstreamPart"]["oneOf"][0]["properties"]["members"]["propertyNames"])
        signature = schema("signature-v1.schema.json")
        codegen = distribution.read_json(ROOT / "codegen-models/schemas/signature-v1.schema.json")
        strip = lambda value: {key: item for key, item in value.items() if key not in ("$id", "title")}
        self.assertEqual(strip(codegen), strip(signature))
        signature_v2 = strip(schema("signature-v2.schema.json"))
        self.assertEqual({"const": "catalog-v2.json"}, signature_v2["properties"].pop("catalog"))
        signature_v3 = strip(schema("signature-v3.schema.json"))
        self.assertEqual({"const": "catalog-v3.json"}, signature_v3["properties"].pop("catalog"))
        signature["properties"].pop("catalog")
        self.assertEqual(strip(signature), signature_v2)
        self.assertEqual(signature_v2, signature_v3)
        for name in ("catalog-v1.schema.json", "catalog-v2.schema.json", "catalog-v3.schema.json", "model-source-v1.schema.json",
                     "signature-v1.schema.json", "signature-v2.schema.json", "signature-v3.schema.json"):
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
