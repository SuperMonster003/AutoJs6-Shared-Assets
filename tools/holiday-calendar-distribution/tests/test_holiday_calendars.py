"""Tests for the holiday-calendars tools. Standard library only; OpenSSL and holidays are optional."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

import build_catalog  # noqa: E402
import calendar_format as fmt  # noqa: E402
import check_docs  # noqa: E402
import verify_calendars  # noqa: E402
import verify_release  # noqa: E402

FAMILY = ROOT / "holiday-calendars"
DATA = FAMILY / "data"
PENDING = FAMILY / "catalogs" / "pending" / "v1"
KNOWN = FAMILY / "sources" / "known-dates.json"


def load(code: str) -> dict:
    return fmt.parse_json((DATA / f"{code}.json").read_bytes())


def quiet(function, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return function(*args)


class CommittedDataTest(unittest.TestCase):
    def test_pending_catalog_verifies(self):
        status = quiet(verify_calendars.main, [str(PENDING / fmt.CATALOG_NAME), "--data-dir", str(DATA), "--first-release",
                                               "--release-assets", str(PENDING / "release-assets.txt"),
                                               "--known-dates", str(KNOWN)])
        self.assertEqual(status, 0)

    def test_data_files_are_canonical(self):
        for path in sorted(DATA.glob("*.json")):
            data = path.read_bytes()
            document = fmt.parse_json(data)
            if path.name == "generation.json":
                self.assertEqual(fmt.canonical_json_bytes(document), data)
            else:
                self.assertEqual(fmt.calendar_bytes(document), data, path.name)

    def test_pending_catalog_is_reproducible(self):
        with tempfile.TemporaryDirectory() as value:
            out = Path(value)
            status = quiet(build_catalog.main, ["--data-dir", str(DATA), "--output-dir", str(out), "--catalog-version", "1",
                                                "--generated-at", fmt.parse_json((PENDING / fmt.CATALOG_NAME).read_bytes())["generatedAt"]])
            self.assertEqual(status, 0)
            for name in (fmt.CATALOG_NAME, "release-assets.txt", "preparation.json"):
                self.assertEqual((out / name).read_bytes(), (PENDING / name).read_bytes(), name)

    def test_overlays_and_weekends(self):
        cn = load("CN")
        self.assertTrue(cn["hasMakeupWorkdays"])
        self.assertEqual(cn["estimatedFrom"], 2027)
        self.assertFalse(fmt.is_day_off(cn, dt.date(2026, 2, 14)))  # Saturday makeup workday
        self.assertTrue(fmt.is_day_off(cn, dt.date(2026, 2, 15)))   # Sunday inside the break
        us = load("US")
        self.assertIn("10-12", fmt.resolve_year(us, 2026)[0])
        self.assertNotIn("10-12", fmt.resolve_year(us, 2026, "CA")[0])
        my = load("MY")
        self.assertEqual(fmt.resolve_year(my, 2024, "01")[2], [5, 6])
        self.assertEqual(fmt.resolve_year(my, 2026, "01")[2], [6, 7])
        ae = load("AE")
        self.assertEqual(fmt.resolve_year(ae, 2021)[2], [5, 6])
        self.assertEqual(fmt.resolve_year(ae, 2022)[2], [6, 7])


class CalendarValidationTest(unittest.TestCase):
    def setUp(self):
        self.cn = load("CN")
        self.us = load("US")

    def assertInvalid(self, document, text):
        with self.assertRaises(fmt.FormatError) as caught:
            fmt.validate_calendar(document)
        self.assertIn(text, str(caught.exception))

    def test_workday_must_fall_on_weekend(self):
        document = copy.deepcopy(self.cn)
        document["calendar"]["2026"]["workdays"] = ["01-05"]
        self.assertInvalid(document, "not a weekend day")

    def test_flag_must_match_data(self):
        document = copy.deepcopy(self.us)
        document["hasMakeupWorkdays"] = True
        self.assertInvalid(document, "hasMakeupWorkdays")

    def test_unused_names_rejected(self):
        document = copy.deepcopy(self.us)
        document["names"].append({document["defaultLanguage"]: "Unused"})
        self.assertInvalid(document, "unused")

    def test_removed_must_exist_nationally(self):
        document = copy.deepcopy(self.us)
        document["subdivisions"]["CA"]["calendar"]["2026"]["removed"] = ["01-02"]
        self.assertInvalid(document, "not a national holiday")

    def test_years_must_be_complete(self):
        document = copy.deepcopy(self.us)
        del document["calendar"]["2030"]
        self.assertInvalid(document, "exactly the years")

    def test_strict_json(self):
        with self.assertRaises(fmt.FormatError):
            fmt.parse_json(b'{"a": 1, "a": 2}')
        with self.assertRaises(fmt.FormatError):
            fmt.parse_json(b'{"a": NaN}')


class CatalogHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.data = self.dir / "data"
        shutil.copytree(DATA, self.data)
        self.first = fmt.parse_json((PENDING / fmt.CATALOG_NAME).read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def test_second_release_uploads_only_changed_regions(self):
        document = fmt.parse_json((self.data / "JP.json").read_bytes())
        document["name"] = "Japan (changed)"
        (self.data / "JP.json").write_bytes(fmt.calendar_bytes(document))
        catalog, sources = build_catalog.build(self.data, 2, "2027-11-10T00:00:00Z", self.first)
        self.assertEqual(list(sources), [fmt.asset_name("JP", hashlib.sha256((self.data / "JP.json").read_bytes()).hexdigest())])
        self.assertEqual(fmt.new_assets(catalog), list(sources))
        unchanged = next(region for region in catalog["regions"] if region["code"] == "CN")
        self.assertEqual(unchanged["file"]["releaseTag"], "holiday-calendars-v1")

    def test_unchanged_data_is_refused(self):
        with self.assertRaises(fmt.FormatError):
            build_catalog.build(self.data, 2, "2027-11-10T00:00:00Z", self.first)

    def test_history_rules(self):
        second = copy.deepcopy(self.first)
        second["catalogVersion"], second["releaseTag"] = 3, "holiday-calendars-v3"
        with self.assertRaises(fmt.FormatError):
            fmt.check_catalog_history(second, self.first)
        second = copy.deepcopy(self.first)
        second["catalogVersion"], second["releaseTag"] = 2, "holiday-calendars-v2"
        second["regions"][0]["file"]["size"] += 1
        with self.assertRaises(fmt.FormatError):
            fmt.check_catalog_history(second, self.first)

    def test_release_verification(self):
        stage = self.dir / "stage"
        status = quiet(build_catalog.main, ["--data-dir", str(DATA), "--output-dir", str(self.dir / "out"), "--catalog-version", "1",
                                            "--generated-at", self.first["generatedAt"], "--stage-assets", str(stage)])
        self.assertEqual(status, 0)
        catalog = PENDING / fmt.CATALOG_NAME
        assets = PENDING / "release-assets.txt"
        self.assertEqual(verify_release.verify_release(catalog, stage, assets), len(self.first["regions"]))
        victim = next(stage.iterdir())
        victim.write_bytes(victim.read_bytes() + b" ")
        with self.assertRaises(fmt.FormatError):
            verify_release.verify_release(catalog, stage, assets)


class SignatureTest(unittest.TestCase):
    def setUp(self):
        import crypto
        self.crypto = crypto
        try:
            crypto.find_openssl()
        except crypto.DistributionError:
            self.skipTest("OpenSSL is not available")
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_sign_and_verify(self):
        crypto = self.crypto
        key_id = crypto.generate_key_pair(self.dir / "private.pem", self.dir / "public.pem", self.dir / "public.der")
        catalog = self.dir / fmt.CATALOG_NAME
        shutil.copyfile(PENDING / fmt.CATALOG_NAME, catalog)
        signature = self.dir / fmt.SIGNATURE_NAME
        crypto.sign_catalog(catalog, self.dir / "private.pem", signature, key_id, expected_repository=fmt.DEFAULT_REPOSITORY)
        envelope = json.loads(signature.read_text(encoding="utf-8"))
        self.assertEqual(envelope["catalog"], fmt.CATALOG_NAME)
        crypto.verify_catalog_material(catalog, signature, self.dir / "public.pem", key_id,
                                       expected_repository=fmt.DEFAULT_REPOSITORY)
        arguments = ["--verify-signature", str(catalog), "--signature", str(signature), "--public-key",
                     str(self.dir / "public.pem"), "--expected-key-id", key_id]
        self.assertEqual(quiet(verify_release.main, arguments), 0)
        self.assertEqual(quiet(verify_release.main, arguments[:-1] + ["p256-0000000000000000"]), 2)
        catalog.write_bytes(catalog.read_bytes().replace(b'"catalogVersion": 1', b'"catalogVersion": 1 '))
        with self.assertRaises(crypto.DistributionError):
            crypto.verify_catalog_material(catalog, signature, self.dir / "public.pem", key_id,
                                           expected_repository=fmt.DEFAULT_REPOSITORY)

    def test_other_family_keys_are_refused(self):
        for family in ("speech-models", "codegen-models", "ace-fonts"):
            key = ROOT / family / "keys" / "catalog-signing-public.pem"
            if key.is_file():
                with self.assertRaises(self.crypto.DistributionError):
                    self.crypto.public_key_der(key)

    def test_family_key_matches_readme(self):
        self.assertGreaterEqual(check_docs.check(ROOT), 2)


class GeneratorTest(unittest.TestCase):
    def test_generator_reproduces_committed_region(self):
        try:
            import importlib.metadata
            import holidays
            version = importlib.metadata.version("holidays")
        except ImportError:
            self.skipTest("holidays is not installed")
        import generate_calendars
        config = generate_calendars.load_config(FAMILY / "sources" / "generator.json")
        if version != config["source"]["version"]:
            self.skipTest(f"holidays {version} is not the pinned version")
        for code in ("CN", "MY"):
            document = generate_calendars.build_region(code, getattr(holidays, code), config, {"languageMismatches": 0})
            self.assertEqual(fmt.calendar_bytes(document), (DATA / f"{code}.json").read_bytes(), code)


if __name__ == "__main__":
    unittest.main()
