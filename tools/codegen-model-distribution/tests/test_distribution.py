"""Synthetic local fixtures only: no production gates, keys, or releases."""

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile
import zlib

if __package__:
    from . import windows_access
else:
    import windows_access


TOOL_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TOOL_DIR.parents[1]
MODULE_NAME = "autojs6_codegen_distribution"
if MODULE_NAME in sys.modules:
    if Path(sys.modules[MODULE_NAME].__file__).resolve() != (TOOL_DIR / "distribution.py").resolve():
        raise RuntimeError("Unexpected distribution module identity")
    distribution = sys.modules[MODULE_NAME]
else:
    spec = importlib.util.spec_from_file_location(MODULE_NAME, TOOL_DIR / "distribution.py")
    distribution = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = distribution
    spec.loader.exec_module(distribution)

DistributionError = distribution.DistributionError
TIME1 = "2026-01-01T00:00:00Z"
TIME2 = "2026-01-02T00:00:00Z"
FORK = "test-owner/isolated-codegen-tests"


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(distribution.canonical_json_bytes(value))


def package_entries(model_id="autojs6.codegen.unit", code=1, delta=0.0, license_name="MPL-2.0"):
    binary = struct.pack("<4sHHIddBHfff", b"AJCG", 1, 1, 1, 0, 1, 1, 0, 0.5, -0.5 + delta, 0.5)
    binary += struct.pack("<I", zlib.crc32(binary) & 0xFFFFFFFF)
    schema = {"format": 1, "featureSchemaVersion": 1, "names": ["numeric"],
              "namesHash": hashlib.sha256(b"numeric").hexdigest()[:16]}
    metrics = {"test": {"groups": 1, "top1Survival": 1, "ruleTop1Survival": 0.5, "regret": 0},
               "realTest": {"groups": 0, "top1Survival": None, "ruleTop1Survival": None, "regret": None}}
    manifest = {"format": 1, "modelId": model_id, "displayName": {"en": "Synthetic unit fixture"},
                "versionCode": code, "versionName": str(code), "kind": "ranker", "algorithm": "catboost-oblivious",
                "featureSchemaVersion": 1, "featureNamesHash": schema["namesHash"],
                "model": {"file": "model.bin", "size": len(binary), "sha256": distribution.sha256_bytes(binary), "features": 1, "trees": 1, "depth": 1},
                "dataset": {"datasetId": "synthetic-unit-data", "groups": 2, "createdAt": TIME1}, "metrics": metrics,
                "training": {"catboostVersion": "synthetic", "pythonVersion": "synthetic", "hostCommit": "a" * 40, "trainedAt": TIME1},
                "minHostVersionCode": 1, "license": license_name, "publisher": "Unit tests only"}
    return {"manifest.json": distribution.canonical_json_bytes(manifest), "model.bin": binary,
            "features.json": distribution.canonical_json_bytes(schema), "MODEL_CARD.md": b"Synthetic test fixture only.\n",
            "LICENSE": b"Synthetic unit-test bytes, not a production license grant.\n"}


def write_package(path, entries, *, compress=zipfile.ZIP_STORED, extra=None):
    with zipfile.ZipFile(path, "w", compression=compress) as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compress
            archive.writestr(info, content)
        if extra:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(*extra)


def central_records(data):
    """Independent mutation helper for ordinary test ZIPs, not a validator."""
    end = data.rfind(b"PK\x05\x06")
    count, offset = struct.unpack_from("<H", data, end + 10)[0], struct.unpack_from("<I", data, end + 16)[0]
    positions = []
    for _ in range(count):
        positions.append(offset)
        name, extra, comment = struct.unpack_from("<HHH", data, offset + 28)
        offset += 46 + name + extra + comment
    return end, positions


def tiny_entries():
    path = REPOSITORY_ROOT / "codegen-models/sources/autojs6.codegen.tiny-test/1/tiny-test-v1.ajcgm"
    with zipfile.ZipFile(path) as archive:
        return path.read_bytes(), {name: archive.read(name) for name in archive.namelist()}


def source(root, model_id="autojs6.codegen.unit", code=1, *, gate=True, delta=0.0, license_name="MPL-2.0"):
    folder = Path(root) / model_id / str(code)
    folder.mkdir(parents=True, exist_ok=True)
    entries = package_entries(model_id, code, delta, license_name)
    package = folder / "source.ajcgm"
    write_package(package, entries)
    (folder / "MODEL_CARD.md").write_bytes(entries["MODEL_CARD.md"])
    write_json(folder / "dataset-manifest.json", {"format": 1, "datasetId": "synthetic-unit-data", "generatedAt": TIME1,
                                                 "sourceManifestSha256": "b" * 64,
                                                 "splits": {"train": {"groups": 2, "groupsWithoutCandidates": 0}}})
    write_json(folder / "source.json", {"format": 1, "summary": {"en": "Synthetic offline unit test"}, "releasedAt": TIME1})
    if gate:
        # This synthetic evidence exists only in TemporaryDirectory for validating
        # the consumer. No gate is made for any actual trained model/source.
        write_json(folder / "gate.json", {"format": 1, "passed": True, "packageSha256": distribution.sha256_bytes(package.read_bytes())})
    return folder


class DistributionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()

    def prepare(self, name="pending", version=1, **kwargs):
        return distribution.prepare_catalog(self.sources, self.root / name, distribution.DEFAULT_REPOSITORY,
                                             version, TIME1 if version == 1 else TIME2, **kwargs)

    def test_preparation_is_byte_reproducible_and_unsigned(self):
        source(self.sources)
        catalog = self.prepare("one")
        self.prepare("two")
        for path in (self.root / "one").rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (self.root / "two" / path.relative_to(self.root / "one")).read_bytes())
        self.assertFalse((self.root / "one/catalog-v1.sig.json").exists())
        self.assertEqual(1, catalog["models"][0]["recommendedVersionCode"])
        self.assertTrue(distribution.read_json(self.root / "one/preparation.json")["unsigned"])

    def test_empty_bootstrap_is_explicit_and_does_not_scan_sources(self):
        source(self.sources, distribution.TINY_TEST_MODEL_ID, gate=False)
        with self.assertRaisesRegex(DistributionError, "empty initial catalog"):
            self.prepare()
        catalog = self.prepare("empty", empty_bootstrap=True)
        self.assertEqual([], catalog["models"])
        self.assertEqual(b"", (self.root / "empty/release-assets.txt").read_bytes())
        self.assertFalse((self.root / "pending").exists())

    def test_test_source_exclusion_is_recorded_without_weakening_gates(self):
        source(self.sources, distribution.TINY_TEST_MODEL_ID, gate=False)
        source(self.sources)
        catalog = self.prepare()
        self.assertEqual(["autojs6.codegen.unit"], [model["modelId"] for model in catalog["models"]])
        summary = distribution.read_json(self.root / "pending/preparation.json")
        self.assertEqual(distribution.TINY_TEST_MODEL_ID, summary["excludedTestSources"][0]["modelId"])

    def test_tiny_only_runs_in_explicit_noncanonical_test_mode(self):
        source(self.sources, distribution.TINY_TEST_MODEL_ID, gate=False)
        for repository in (distribution.DEFAULT_REPOSITORY, distribution.DEFAULT_REPOSITORY.lower()):
            with self.assertRaisesRegex(DistributionError, "canonical"):
                distribution.prepare_catalog(self.sources, self.root / "bad", repository, 1, TIME1, allow_test_models=True)
        catalog = distribution.prepare_catalog(self.sources, self.root / "fork", FORK, 1, TIME1, allow_test_models=True)
        distribution.validate_catalog(catalog, allow_test_models=True)
        with self.assertRaisesRegex(DistributionError, "tiny-test"):
            distribution.validate_catalog(catalog)

    def test_production_gate_is_required_and_bound_to_exact_bytes(self):
        folder = source(self.sources, gate=False)
        for kwargs in ({}, {"allow_test_models": True}):
            repository = FORK if kwargs else distribution.DEFAULT_REPOSITORY
            with self.assertRaisesRegex(DistributionError, "gate.json"):
                distribution.prepare_catalog(self.sources, self.root / "bad", repository, 1, TIME1, **kwargs)
        for gate in ({"format": 1, "passed": False, "packageSha256": "a" * 64},
                     {"format": 1, "passed": True, "packageSha256": "a" * 64},
                     {"format": 1, "passed": 1, "packageSha256": "a" * 64}):
            write_json(folder / "gate.json", gate)
            with self.assertRaisesRegex(DistributionError, "passed gate.json"):
                self.prepare()
        self.assertFalse((self.root / "pending").exists())

    def test_local_evaluation_license_is_never_catalogued(self):
        source(self.sources, license_name="LicenseRef-LocalEvaluation")
        with self.assertRaisesRegex(DistributionError, "Local-evaluation"):
            self.prepare()

    def test_historical_urls_are_retained_and_only_new_assets_are_staged(self):
        source(self.sources)
        previous = self.prepare("v1")
        source(self.sources, code=2)
        current = self.prepare("v2", 2, previous_catalog=previous)
        versions = current["models"][0]["versions"]
        self.assertEqual(previous["models"][0]["versions"][0], versions[0])
        self.assertIn("/codegen-models-v1/", versions[0]["artifact"]["url"])
        self.assertIn("/codegen-models-v2/", versions[1]["artifact"]["url"])
        self.assertEqual([versions[1]["artifact"]["fileName"]], [path.name for path in (self.root / "v2/assets").iterdir()])

    def test_rollback_and_same_catalog_version_equivocation_are_rejected(self):
        source(self.sources)
        previous = self.prepare("v1")
        with self.assertRaises(DistributionError):
            distribution.validate_catalog(previous, minimum_catalog_version=2)
        altered = deepcopy(previous)
        altered["generatedAt"] = TIME2
        with self.assertRaisesRegex(DistributionError, "Same catalogVersion"):
            distribution.validate_catalog(altered, previous_catalog=previous)
        newer = deepcopy(previous)
        newer.update(catalogVersion=2, releaseTag="codegen-models-v2", generatedAt=TIME2)
        with self.assertRaisesRegex(DistributionError, "rollback"):
            distribution.validate_catalog(previous, previous_catalog=newer)

    def test_preparation_cannot_omit_history_or_reuse_current_catalog_as_previous(self):
        source(self.sources)
        previous = self.prepare("v1")
        with self.assertRaisesRegex(DistributionError, "require --previous-catalog"):
            self.prepare("v2", 2)
        for version in (1, 3):
            with self.assertRaisesRegex(DistributionError, "exactly one"):
                self.prepare("wrong", version, previous_catalog=previous)

    def test_historical_payload_cannot_change_even_after_gate_refresh(self):
        source(self.sources)
        previous = self.prepare("v1")
        source(self.sources, delta=0.25)
        with self.assertRaisesRegex(DistributionError, "immutable historical package"):
            self.prepare("v2", 2, previous_catalog=previous)
        missing = deepcopy(previous)
        missing.update(catalogVersion=2, releaseTag="codegen-models-v2", generatedAt=TIME2, models=[])
        with self.assertRaisesRegex(DistributionError, "changed or disappeared"):
            distribution.validate_catalog(missing, previous_catalog=previous)

    def test_revocation_and_deprecation_are_only_monotonic(self):
        folder = source(self.sources)
        previous = self.prepare("v1")
        metadata = distribution.read_json(folder / "source.json")
        metadata.update(deprecated=True, revoked=True)
        write_json(folder / "source.json", metadata)
        revoked = self.prepare("v2", 2, previous_catalog=previous)
        self.assertIsNone(revoked["models"][0]["recommendedVersionCode"])
        self.assertEqual([], list((self.root / "v2/assets").iterdir()))
        for flag in ("deprecated", "revoked"):
            altered = deepcopy(revoked)
            altered.update(catalogVersion=3, releaseTag="codegen-models-v3")
            altered["models"][0]["versions"][0][flag] = False
            with self.assertRaisesRegex(DistributionError, "cannot be reversed"):
                distribution.validate_catalog(altered, previous_catalog=revoked)

    def test_duplicate_versions_invalid_urls_and_size_boundaries(self):
        source(self.sources)
        catalog = self.prepare()
        invalid = deepcopy(catalog)
        invalid["models"][0]["versions"].append(deepcopy(invalid["models"][0]["versions"][0]))
        with self.assertRaisesRegex(DistributionError, "Duplicate"):
            distribution.validate_catalog(invalid)
        for field, value in (("size", distribution.MAX_PACKAGE_BYTES), ("size", True),
                             ("fileName", "../wrong.ajcgm"), ("sha256", "uppercase"),
                             ("url", "https://evil.example/package.ajcgm")):
            invalid = deepcopy(catalog)
            invalid["models"][0]["versions"][0]["artifact"][field] = value
            with self.assertRaises(DistributionError):
                distribution.validate_catalog(invalid)
        invalid = deepcopy(catalog)
        artifact = invalid["models"][0]["versions"][0]["artifact"]
        artifact["url"] = artifact["url"].replace("codegen-models-v1", "codegen-models-v2")
        artifact["urls"] = [artifact["url"]]
        with self.assertRaisesRegex(DistributionError, "earlier release"):
            distribution.validate_catalog(invalid)

    def test_current_header_can_change_without_mutating_old_version(self):
        source(self.sources)
        previous = self.prepare()
        changed = deepcopy(previous)
        changed.update(catalogVersion=2, releaseTag="codegen-models-v2", generatedAt=TIME2)
        changed["models"][0]["displayName"]["en"] = "Renamed model family"
        changed["models"][0]["summary"]["en"] = "Updated family description"
        distribution.validate_catalog(changed, previous_catalog=previous)

    def test_public_dataset_summary_and_model_card_must_match_package(self):
        folder = source(self.sources)
        (folder / "MODEL_CARD.md").write_text("Unrelated card", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "MODEL_CARD"):
            self.prepare()
        source(self.sources)
        data = distribution.read_json(folder / "dataset-manifest.json")
        data["splits"]["train"]["groups"] = 3
        write_json(folder / "dataset-manifest.json", data)
        with self.assertRaisesRegex(DistributionError, "dataset manifest summary"):
            self.prepare()

    def test_existing_output_is_preserved_and_json_is_strict(self):
        source(self.sources)
        self.prepare()
        before = (self.root / "pending/catalog-v1.json").read_bytes()
        with self.assertRaisesRegex(DistributionError, "already exists"):
            self.prepare()
        self.assertEqual(before, (self.root / "pending/catalog-v1.json").read_bytes())
        path = self.root / "bad.json"
        for content in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e400}', b'\xef\xbb\xbf{}', b'[]'):
            path.write_bytes(content)
            with self.assertRaises(DistributionError):
                distribution.read_json(path)

    @windows_access.windows_mkdtemp_dacl
    def test_pending_output_inherits_the_parent_access_rights(self):
        # mkdtemp() staging used to leave only SYSTEM, Administrators and OWNER RIGHTS on the output.
        source(self.sources)
        output = windows_access.plain_directory(self) / "pending"
        distribution.prepare_catalog(self.sources, output, distribution.DEFAULT_REPOSITORY, 1, TIME1)
        self.assertTrue((output / "assets").is_dir())
        windows_access.assert_inherited_access(self, output)


class PackageValidationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "model.ajcgm"

    def test_valid_package_and_missing_duplicate_traversal_entries(self):
        entries = package_entries()
        write_package(self.path, entries)
        self.assertEqual(1, distribution.validate_package(self.path)["model"]["trees"])
        for extra in (("manifest.json", entries["manifest.json"]), ("../escape", b"x")):
            write_package(self.path, entries, extra=extra)
            with self.assertRaisesRegex(DistributionError, "five allowed"):
                distribution.validate_package(self.path)
        entries.pop("LICENSE")
        write_package(self.path, entries)
        with self.assertRaises(DistributionError):
            distribution.validate_package(self.path)

    def test_package_crc_schema_and_manifest_sha_are_checked(self):
        for name in ("model.bin", "features.json", "manifest.json"):
            entries = package_entries()
            if name == "model.bin":
                entries[name] = entries[name][:-1] + bytes([entries[name][-1] ^ 1])
            else:
                value = json.loads(entries[name])
                if name == "features.json":
                    value["names"] = ["different"]
                else:
                    value["model"]["sha256"] = "0" * 64
                entries[name] = distribution.canonical_json_bytes(value)
            write_package(self.path, entries)
            with self.assertRaises(DistributionError):
                distribution.validate_package(self.path)

    def test_compression_bomb_and_strict_package_size_limit(self):
        entries = package_entries()
        entries["LICENSE"] = b"x" * 100000
        write_package(self.path, entries, compress=zipfile.ZIP_DEFLATED)
        with self.assertRaisesRegex(DistributionError, "compression ratio"):
            distribution.validate_package(self.path)
        with self.path.open("wb") as target:
            target.truncate(distribution.MAX_PACKAGE_BYTES)
        with self.assertRaisesRegex(DistributionError, "strictly smaller"):
            distribution.validate_package(self.path)

    def test_package_catalog_metadata_comparison(self):
        write_package(self.path, package_entries())
        manifest = distribution.validate_package(self.path)
        version = {field: manifest[field] for field in ("versionCode", "versionName", "featureSchemaVersion", "featureNamesHash", "minHostVersionCode", "metrics")}
        version.update(datasetId=manifest["dataset"]["datasetId"], license={"spdx": manifest["license"]})
        model = {"modelId": manifest["modelId"], "displayName": {"en": "Current renamed family"}}
        distribution.compare_release_version(manifest, model, version)
        version["featureNamesHash"] = "0" * 16
        with self.assertRaisesRegex(DistributionError, "mismatch"):
            distribution.compare_release_version(manifest, model, version)

    def test_actual_tiny_rejects_prefix_suffix_and_nonregular_central_attributes(self):
        original, _ = tiny_entries()
        self.path.write_bytes(original)
        self.assertEqual(distribution.TINY_TEST_MODEL_ID, distribution.validate_package(self.path)["modelId"])
        for invalid in (b"prefix" + original, original + b"trailing garbage"):
            self.path.write_bytes(invalid)
            with self.assertRaises(DistributionError):
                distribution.validate_package(self.path)
        _, records = central_records(original)
        for attributes in (0o120777 << 16, 0o040755 << 16, 0o010644 << 16, 0x10):
            invalid = bytearray(original)
            struct.pack_into("<I", invalid, records[0] + 38, attributes)
            self.path.write_bytes(invalid)
            with self.assertRaisesRegex(DistributionError, "non-regular"):
                distribution.validate_package(self.path)
        # A prefix remains forbidden even if all ZIP offsets are repaired.
        invalid = bytearray(b"prefix" + original)
        end, records = central_records(original)
        directory = struct.unpack_from("<I", original, end + 16)[0]
        struct.pack_into("<I", invalid, end + 6 + 16, directory + 6)
        for record in records:
            old = struct.unpack_from("<I", original, record + 42)[0]
            struct.pack_into("<I", invalid, record + 6 + 42, old + 6)
        self.path.write_bytes(invalid)
        with self.assertRaisesRegex(DistributionError, "prefix"):
            distribution.validate_package(self.path)

    def test_actual_tiny_rejects_directory_gaps_and_local_header_mismatches(self):
        original, _ = tiny_entries()
        end, records = central_records(original)
        directory = struct.unpack_from("<I", original, end + 16)[0]
        variants = []
        for offset, fmt, value in ((records[0] + 6, "<H", 45), (4, "<H", 45),
                                   (records[0] + 34, "<H", 1), (14, "<I", 1),
                                   (records[0] + 8, "<H", 1), (6, "<H", 1),
                                   (records[1] + 42, "<I", 0), (end + 12, "<I", 1)):
            invalid = bytearray(original)
            struct.pack_into(fmt, invalid, offset, value)
            variants.append(invalid)
        invalid = bytearray(original)
        invalid[30] ^= 1  # local filename differs from its central record
        variants.append(invalid)
        invalid = bytearray(original[:directory] + b"gap" + original[directory:])
        struct.pack_into("<I", invalid, end + 3 + 16, directory + 3)
        variants.append(invalid)
        for invalid in variants:
            self.path.write_bytes(invalid)
            with self.assertRaises(DistributionError):
                distribution.validate_package(self.path)

    def test_actual_tiny_supports_deflate_descriptors_and_rejects_extra_or_bad_descriptor(self):
        _, entries = tiny_entries()

        class NonSeekable(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation("test output is not seekable")

        output = NonSeekable()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        data = output.getvalue()
        self.path.write_bytes(data)
        distribution.validate_package(self.path)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            first = archive.infolist()[0]
        name_size, extra_size = struct.unpack_from("<HH", data, first.header_offset + 26)
        descriptor = first.header_offset + 30 + name_size + extra_size + first.compress_size
        self.assertEqual(b"PK\x07\x08", data[descriptor:descriptor + 4])
        invalid = bytearray(data)
        invalid[descriptor + 4] ^= 1
        self.path.write_bytes(invalid)
        with self.assertRaisesRegex(DistributionError, "descriptor"):
            distribution.validate_package(self.path)
        for extra in (b"\x01\x00\x00\x00", b"\x02", b"\x02\x00\x02\x00x"):
            with zipfile.ZipFile(self.path, "w") as archive:
                for index, (name, content) in enumerate(entries.items()):
                    info = zipfile.ZipInfo(name)
                    if index == 0:
                        info.extra = extra
                    archive.writestr(info, content)
            with self.assertRaisesRegex(DistributionError, "extra field"):
                distribution.validate_package(self.path)

    def test_actual_tiny_rejects_unused_bytes_inside_a_deflate_entry(self):
        _, entries = tiny_entries()
        write_package(self.path, entries, compress=zipfile.ZIP_DEFLATED)
        original = self.path.read_bytes()
        end, records = central_records(original)
        directory = struct.unpack_from("<I", original, end + 16)[0]
        with zipfile.ZipFile(self.path) as archive:
            first = archive.infolist()[0]
        name_size, extra_size = struct.unpack_from("<HH", original, first.header_offset + 26)
        insertion = first.header_offset + 30 + name_size + extra_size + first.compress_size
        invalid = bytearray(original[:insertion] + b"junk" + original[insertion:])
        struct.pack_into("<I", invalid, end + 4 + 16, directory + 4)
        struct.pack_into("<I", invalid, first.header_offset + 18, first.compress_size + 4)
        for index, record in enumerate(records):
            local = struct.unpack_from("<I", original, record + 42)[0]
            if local >= insertion:
                struct.pack_into("<I", invalid, record + 4 + 42, local + 4)
            if index == 0:
                struct.pack_into("<I", invalid, record + 4 + 20, first.compress_size + 4)
        self.path.write_bytes(invalid)
        with self.assertRaisesRegex(DistributionError, "deflate stream"):
            distribution.validate_package(self.path)

    def test_actual_tiny_rejects_noncalendar_or_overprecise_timestamps(self):
        _, original_entries = tiny_entries()
        invalid_times = ("2026-W40-6T00:00:00Z", "2026-10-03T00:00:00.1234567890Z", "2026-02-30T00:00:00Z",
                         "2026-10-03T00:00:00+18:01", "2026-10-03T24:00:00Z", "2026-10-03T00:00:00+01:00:30")
        for value in invalid_times:
            entries = dict(original_entries)
            manifest = json.loads(entries["manifest.json"])
            manifest["training"]["trainedAt"] = value
            entries["manifest.json"] = distribution.canonical_json_bytes(manifest)
            write_package(self.path, entries)
            with self.assertRaisesRegex(DistributionError, "timestamp"):
                distribution.validate_package(self.path)
        for value in ("2026-10-03T00:00:00.123456789Z", "2026-10-03T00:00:00+18:00", "2026-10-03T00:00:00-18:00"):
            entries = dict(original_entries)
            manifest = json.loads(entries["manifest.json"])
            manifest["training"]["trainedAt"] = value
            entries["manifest.json"] = distribution.canonical_json_bytes(manifest)
            write_package(self.path, entries)
            distribution.validate_package(self.path)

    def test_catalog_timestamp_comparison_preserves_nanosecond_order(self):
        catalog = {"schemaVersion": 1, "catalogVersion": 1, "releaseTag": "codegen-models-v1", "models": [],
                   "repository": distribution.DEFAULT_REPOSITORY, "generatedAt": "2026-10-03T00:00:00.123456789Z"}
        later = deepcopy(catalog)
        later.update(catalogVersion=2, releaseTag="codegen-models-v2", generatedAt="2026-10-03T01:00:00.123456790+01:00")
        distribution.validate_catalog(later, previous_catalog=catalog)
        later["generatedAt"] = "2026-10-03T00:00:00.123456788Z"
        with self.assertRaisesRegex(DistributionError, "backwards"):
            distribution.validate_catalog(later, previous_catalog=catalog)


class SchemaTest(unittest.TestCase):
    def test_three_schemas_parse_and_declare_required_wire_fields(self):
        root = REPOSITORY_ROOT / "codegen-models/schemas"
        for name in ("catalog-v1", "signature-v1", "model-manifest-v1"):
            schema = distribution.read_json(root / (name + ".schema.json"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(set(schema["properties"]), set(schema["required"]))
        catalog = distribution.read_json(root / "catalog-v1.schema.json")
        self.assertIn("repository", catalog["required"])
        self.assertEqual(["integer", "null"], catalog["properties"]["models"]["items"]["properties"]["recommendedVersionCode"]["type"])
        for name in ("catalog-v1.schema.json", "model-manifest-v1.schema.json"):
            pattern = distribution.read_json(root / name)["$defs"]["timestamp"]["pattern"]
            self.assertIsNotNone(re.fullmatch(pattern, "2026-10-03T00:00:00.123456789+18:00"))
            for invalid in ("2026-W40-6T00:00:00Z", "2026-10-03T00:00:00.1234567890Z", "2026-10-03T00:00:00+18:01"):
                self.assertIsNone(re.fullmatch(pattern, invalid))


if __name__ == "__main__":
    unittest.main()
