"""Offline repacking from a verified upstream cache, and the guarded resumable downloader."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("autojs6_speech_test_support", Path(__file__).with_name("support.py"))
support = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
if not hasattr(support, "distribution"):
    _spec.loader.exec_module(support)
distribution, preparation = support.distribution, support.preparation
DistributionError = distribution.DistributionError
prepare_sources = support.load("prepare_sources")


class FakeResponse(io.BytesIO):
    def __init__(self, data, status=200, url="https://objects.githubusercontent.com/asset"):
        super().__init__(data)
        self.status, self._url = status, url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def open(self, request, timeout):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class PreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sources, self.cache = self.root / "sources", self.root / "cache"

    def test_repacking_is_deterministic_and_records_exact_installed_files(self):
        folder = support.tts_fixture(self.sources, self.cache)
        [(source, first)] = support.measure(self.sources, self.cache, self.root / "first")
        recorded = support.read_source(folder)
        self.assertEqual(recorded["archive"], {"format": "tar", "size": first.stat().st_size,
                                               "sha256": hashlib.sha256(first.read_bytes()).hexdigest()})
        self.assertEqual([item["path"] for item in recorded["files"]], sorted(support.tts_members()))
        self.assertNotIn("test_wavs/0.wav", json.dumps(recorded["files"]))
        self.assertEqual(first.name, distribution.archive_file_name(source["modelId"], 1, recorded["archive"]["sha256"]))
        loaded = distribution.load_sources(self.sources)
        [(_source, second)] = preparation.prepare(loaded, self.cache, self.root / "second", offline=True, log=lambda _m: None)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        again = preparation.prepare(loaded, self.cache, self.root / "first", offline=True, log=lambda _m: None)
        self.assertEqual(first, again[0][1])
        self.assertEqual([], [path.name for path in (self.root / "first").iterdir() if path.name.startswith(".work-")])

    def test_upstream_only_sources_are_measured_but_never_archived(self):
        folder = support.upstream_only_fixture(self.sources, self.cache)
        [(source, path)] = support.measure(self.sources, self.cache, self.root / "assets")
        self.assertIsNone(path)
        recorded = support.read_source(folder)
        self.assertFalse(recorded["mirror"])
        self.assertIsNone(recorded["archive"])
        self.assertEqual(["README.md", "model.int8.onnx", "tokens.txt"], [item["path"] for item in recorded["files"]])
        self.assertEqual(hashlib.sha256(b"sense-voice" * 40).hexdigest(), recorded["files"][1]["sha256"])
        self.assertEqual([], list((self.root / "assets").iterdir()))
        loaded = distribution.load_sources(self.sources)
        messages = []
        [(_source, again)] = preparation.prepare(loaded, self.cache, self.root / "assets", offline=True, log=messages.append)
        self.assertIsNone(again)
        self.assertIn("no mirror archive", messages[0])
        recorded["files"][1]["sha256"] = "0" * 64
        (folder / "source.json").write_bytes(distribution.canonical_json_bytes(recorded))
        with self.assertRaisesRegex(DistributionError, "differ from source.json"):
            preparation.prepare(distribution.load_sources(self.sources), self.cache, self.root / "assets", offline=True, log=lambda _m: None)
        recorded["files"][1]["sha256"] = source["files"][1]["sha256"]
        (folder / "source.json").write_bytes(distribution.canonical_json_bytes(recorded))
        catalog, assets = distribution.build_catalog(self.sources, support.REPOSITORY, 1, support.TIME1)
        self.assertEqual([], assets)
        catalog_path = self.root / "catalog-v1.json"
        catalog_path.write_bytes(distribution.canonical_json_bytes(catalog))
        release = self.root / "release"
        self.assertEqual(0, prepare_sources.main(["--source-root", str(self.sources), "--cache-dir", str(self.cache), "--offline",
                                                  "--output-dir", str(release), "--catalog", str(catalog_path)]))
        self.assertFalse(release.exists())
        self.assertEqual(0, prepare_sources.main(["--source-root", str(self.sources), "--cache-dir", str(self.cache), "--offline",
                                                  "--output-dir", str(release)]))
        self.assertEqual([], [path.name for path in release.iterdir()] if release.exists() else [])

    def test_raw_upstream_files_are_installed_unchanged(self):
        folder = support.asr_fixture(self.sources, self.cache)
        support.measure(self.sources, self.cache, self.root / "assets")
        files = {item["path"]: item for item in support.read_source(folder)["files"]}
        self.assertEqual(hashlib.sha256(b"joiner-bytes").hexdigest(), files["joiner.int8.onnx"]["sha256"])

    def test_changed_reproduction_is_refused_without_update(self):
        folder = support.tts_fixture(self.sources, self.cache)
        support.measure(self.sources, self.cache, self.root / "assets")
        value = support.read_source(folder)
        value["files"][0]["sha256"] = "0" * 64
        (folder / "source.json").write_bytes(distribution.canonical_json_bytes(value))
        before = (folder / "source.json").read_bytes()
        with self.assertRaisesRegex(DistributionError, "differ from source.json"):
            preparation.prepare(distribution.load_sources(self.sources), self.cache, self.root / "again", offline=True, log=lambda _m: None)
        self.assertEqual(before, (folder / "source.json").read_bytes())

    def test_cache_must_match_pins_and_offline_mode_never_downloads(self):
        folder = support.tts_fixture(self.sources, self.cache)
        value = support.read_source(folder)
        cached = self.cache / "tts-models" / "tts.vits.unit-test-v1.tar.bz2"
        original = cached.read_bytes()
        cached.write_bytes(original + b"tampered")
        with self.assertRaisesRegex(DistributionError, "differs from its pin"):
            preparation.repack(value, self.cache, self.root / "assets", offline=True)
        cached.unlink()
        with self.assertRaisesRegex(DistributionError, "not cached"):
            preparation.repack(value, self.cache, self.root / "assets", offline=True)
        calls = []

        def fetch(url, target, size, sha256):
            calls.append(url)
            target.write_bytes(original)
            return target

        path, _files, archive = preparation.repack(value, self.cache, self.root / "assets", fetch=fetch)
        self.assertEqual([value["upstream"][0]["url"]], calls)
        self.assertEqual(archive["size"], path.stat().st_size)

    def test_selected_members_must_be_unique_regular_files(self):
        members = support.tts_members()
        link_part = support.write_upstream(self.cache, "tts-models", "link.tar.bz2", "link", members, link="model.onnx.link")
        link_part["members"]["link/model.onnx.link"] = "model.onnx.link"
        value = support.source_value("tts.vits.link", [link_part], {"model": "model.onnx", "tokens": "tokens.txt"})
        with self.assertRaisesRegex(DistributionError, "regular files"):
            preparation.repack(value, self.cache, self.root / "assets", offline=True)
        duplicate = support.write_upstream(self.cache, "tts-models", "dup.tar.bz2", "dup", members, extra={"tokens.txt": b"again"})
        value = support.source_value("tts.vits.dup", [duplicate], {"model": "model.onnx", "tokens": "tokens.txt"})
        with self.assertRaisesRegex(DistributionError, "twice"):
            preparation.repack(value, self.cache, self.root / "assets", offline=True)
        missing = support.write_upstream(self.cache, "tts-models", "miss.tar.bz2", "miss", members)
        missing["members"]["miss/absent.bin"] = "absent.bin"
        value = support.source_value("tts.vits.miss", [missing], {"model": "model.onnx", "tokens": "tokens.txt"})
        with self.assertRaisesRegex(DistributionError, "lacks"):
            preparation.repack(value, self.cache, self.root / "assets", offline=True)

    def test_download_resumes_verifies_and_guards_redirects(self):
        content = b"0123456789" * 100
        digest = hashlib.sha256(content).hexdigest()
        url = support.BASE + "/tts-models/x.tar.bz2"
        target = self.root / "dl" / "x.tar.bz2"
        partial = target.with_name(target.name + ".part")
        partial.parent.mkdir(parents=True)
        partial.write_bytes(content[:300])
        opener = FakeOpener([FakeResponse(content[300:], status=206)])
        preparation.download(url, target, len(content), digest, opener=opener, sleep=lambda _s: None)
        self.assertEqual(content, target.read_bytes())
        self.assertEqual("bytes=300-", opener.requests[0].get_header("Range"))
        self.assertFalse(partial.exists())
        target.unlink()
        opener = FakeOpener([OSError("reset"), FakeResponse(content)])
        preparation.download(url, target, len(content), digest, opener=opener, sleep=lambda _s: None)
        self.assertEqual(content, target.read_bytes())
        target.unlink()
        with self.assertRaisesRegex(DistributionError, "SHA-256"):
            preparation.download(url, target, len(content), "0" * 64, opener=FakeOpener([FakeResponse(content)]), sleep=lambda _s: None)
        with self.assertRaisesRegex(DistributionError, "exceeds"):
            preparation.download(url, target, 10, digest, opener=FakeOpener([FakeResponse(content)]), sleep=lambda _s: None)
        with self.assertRaisesRegex(DistributionError, "allowed GitHub"):
            preparation.download(url, target, len(content), digest, sleep=lambda _s: None,
                                 opener=FakeOpener([FakeResponse(content, url="https://example.com/x")]))
        self.assertFalse(target.exists())
        for bad in ("http://github.com/x", "https://github.com.evil.example/x", "https://user@github.com/x", "https://github.com:8443/x"):
            with self.subTest(bad=bad), self.assertRaises(DistributionError):
                preparation.check_download_url(bad)
        with self.assertRaises(DistributionError):
            preparation.download("https://github.com/other/repo/releases/download/t/x", target, 1, digest)

    def test_cli_selects_models_and_catalog_releases(self):
        support.tts_fixture(self.sources, self.cache)
        support.asr_fixture(self.sources, self.cache)
        support.measure(self.sources, self.cache, self.root / "measured")
        output = self.root / "selected"
        code = prepare_sources.main(["--source-root", str(self.sources), "--cache-dir", str(self.cache), "--output-dir", str(output),
                                     "--offline", "--model", "asr.online.unit-test/1"])
        self.assertEqual(0, code)
        self.assertEqual(1, len([path for path in output.iterdir() if path.suffix == ".tar"]))
        self.assertEqual(2, prepare_sources.main(["--source-root", str(self.sources), "--cache-dir", str(self.cache), "--offline",
                                                  "--output-dir", str(output), "--model", "asr.unknown/1"]))
        catalog, _assets = distribution.build_catalog(self.sources, support.REPOSITORY, 1, support.TIME1)
        catalog_path = self.root / "catalog-v1.json"
        catalog_path.write_bytes(distribution.canonical_json_bytes(catalog))
        release = self.root / "release"
        self.assertEqual(0, prepare_sources.main(["--source-root", str(self.sources), "--cache-dir", str(self.cache), "--offline",
                                                  "--output-dir", str(release), "--catalog", str(catalog_path)]))
        self.assertEqual(sorted(distribution.expected_release_assets(catalog)), sorted(path.name for path in release.iterdir()))


if __name__ == "__main__":
    unittest.main()
