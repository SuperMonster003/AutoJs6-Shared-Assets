"""Release archive verification, read-only remote preflight and the publication workflow contract."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("autojs6_speech_test_support", Path(__file__).with_name("support.py"))
support = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
if not hasattr(support, "distribution"):
    _spec.loader.exec_module(support)
distribution = support.distribution
release = support.load("verify_release")
DistributionError = distribution.DistributionError
REPOSITORY = support.REPOSITORY


def response(status, payload=None, returncode=None, stderr=""):
    code = (0 if status == 200 else 1) if returncode is None else returncode
    return subprocess.CompletedProcess([], code, f"HTTP/2.0 {status} Result\nContent-Type: application/json\n\n" + json.dumps(payload or {}), stderr)


class ReleaseVerificationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        sources, cache = self.root / "sources", self.root / "cache"
        support.tts_fixture(sources, cache)
        support.asr_fixture(sources, cache)
        support.upstream_only_fixture(sources, cache)
        self.assets = self.root / "assets"
        support.measure(sources, cache, self.assets)
        self.catalog, self.names = distribution.build_catalog(sources, REPOSITORY, 1, support.TIME1)
        self.catalog_path = self.root / distribution.CATALOG_FILE
        self.catalog_path.write_bytes(distribution.canonical_json_bytes(self.catalog))

    def verify(self, **kwargs):
        return release.verify_release(self.catalog_path, self.assets, expected_repository=REPOSITORY, **kwargs)

    def test_valid_archives_and_asset_list_pass(self):
        listing = self.root / "release-assets.txt"
        listing.write_text("".join(name + "\n" for name in self.names), encoding="utf-8")
        result = self.verify(asset_list=listing)
        self.assertEqual(2, result["archives"])
        for entries in (self.names[0] + "\n", "\n".join(self.names + self.names[:1]), "../outside.tar\n"):
            listing.write_text(entries, encoding="utf-8")
            with self.subTest(entries=entries), self.assertRaisesRegex(DistributionError, "release-assets.txt"):
                self.verify(asset_list=listing)

    def test_upstream_only_versions_are_never_release_assets(self):
        self.assertEqual([(support.UPSTREAM_ONLY_ID, 1)], distribution.upstream_only_versions(self.catalog))
        self.assertEqual(2, self.verify()["archives"])
        self.assertEqual(2, self.verify(all_artifacts=True)["archives"])
        self.assertEqual(2, len(list(self.assets.iterdir())))
        listing = self.root / "release-assets.txt"
        listing.write_text("".join(name + "\n" for name in self.names + [f"autojs6-speech-{support.UPSTREAM_ONLY_ID}-v1-00000000.tar"]),
                           encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "release-assets.txt"):
            self.verify(asset_list=listing)
        (self.assets / f"autojs6-speech-{support.UPSTREAM_ONLY_ID}-v1-00000000.tar").write_bytes(b"\0" * 1024)
        with self.assertRaisesRegex(DistributionError, "Unexpected"):
            self.verify()

    def test_missing_unexpected_nested_resized_and_altered_archives_fail(self):
        target = self.assets / self.names[0]
        original = target.read_bytes()
        target.unlink()
        with self.assertRaisesRegex(DistributionError, "Missing"):
            self.verify()
        target.write_bytes(original + b"\0" * 512)
        with self.assertRaisesRegex(DistributionError, "size differs"):
            self.verify()
        changed = bytearray(original)
        changed[600] ^= 1
        target.write_bytes(bytes(changed))
        with self.assertRaisesRegex(DistributionError, "SHA-256"):
            self.verify()
        target.write_bytes(original)
        (self.assets / "extra.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "Unexpected"):
            self.verify()
        (self.assets / "extra.txt").unlink()
        (self.assets / "nested").mkdir()
        with self.assertRaisesRegex(DistributionError, "ordinary files"):
            self.verify()

    def test_archive_content_must_match_files_even_when_catalog_digest_matches(self):
        version = next(model for model in self.catalog["models"] if model["kind"] == "tts")["versions"][0]
        version["files"][0]["sha256"] = "0" * 64
        self.catalog_path.write_bytes(distribution.canonical_json_bytes(self.catalog))
        with self.assertRaisesRegex(DistributionError, "content differs"):
            self.verify()

    def test_downloaded_release_requires_exact_catalog_and_signature(self):
        signature = self.root / distribution.SIGNATURE_FILE
        signature.write_bytes(b'{"reviewed": true}\n')
        shutil.copyfile(self.catalog_path, self.assets / distribution.CATALOG_FILE)
        shutil.copyfile(signature, self.assets / distribution.SIGNATURE_FILE)
        self.assertTrue(self.verify(downloaded_release=True, signature_path=signature)["downloadedRelease"])
        with self.assertRaisesRegex(DistributionError, "signature"):
            self.verify(downloaded_release=True)
        (self.assets / distribution.SIGNATURE_FILE).write_bytes(b"{}\n")
        with self.assertRaisesRegex(DistributionError, "signature differs"):
            self.verify(downloaded_release=True, signature_path=signature)
        # A schema 1 release carries catalog-v1.json and catalog-v1.sig.json instead.
        self.catalog["schemaVersion"] = 1
        self.catalog_path.write_bytes(distribution.canonical_json_bytes(self.catalog))
        with self.assertRaisesRegex(DistributionError, "catalog-v1.json, catalog-v1.sig.json"):
            self.verify(downloaded_release=True, signature_path=signature)
        (self.assets / distribution.CATALOG_FILE).unlink()
        (self.assets / distribution.SIGNATURE_FILE).unlink()
        shutil.copyfile(self.catalog_path, self.assets / "catalog-v1.json")
        shutil.copyfile(signature, self.assets / "catalog-v1.sig.json")
        self.assertTrue(self.verify(downloaded_release=True, signature_path=signature)["downloadedRelease"])

    def test_current_release_and_all_artifacts_modes_distinguish_historical_urls(self):
        self.catalog.update(catalogVersion=2, releaseTag="speech-models-v2", generatedAt=support.TIME2)
        self.catalog_path.write_bytes(distribution.canonical_json_bytes(self.catalog))
        self.assertEqual(2, self.verify(all_artifacts=True)["archives"])
        with self.assertRaisesRegex(DistributionError, "Unexpected"):
            self.verify()
        for path in list(self.assets.iterdir()):
            path.unlink()
        self.assertEqual(0, self.verify()["archives"])


class RemotePreflightTest(unittest.TestCase):
    def runner(self, replies):
        self.calls = []
        replies = iter(replies)

        def run(command, **kwargs):
            self.calls.append(command)
            item = next(replies)
            if isinstance(item, Exception):
                raise item
            return item

        return run

    def test_absence_requires_authenticated_repository_then_two_404s(self):
        release.check_remote_absent(REPOSITORY, "speech-models-v1",
                                    runner=self.runner([response(200, {"full_name": REPOSITORY}), response(404), response(404)]))
        self.assertEqual(3, len(self.calls))
        self.assertTrue(all(command[:7] == ["gh", "api", "--hostname", "github.com", "--method", "GET", "--include"] for command in self.calls))

    def test_existing_release_or_tag_errors_and_secrets_are_handled(self):
        for replies in ([response(200, {"full_name": REPOSITORY}), response(200)],
                        [response(200, {"full_name": REPOSITORY}), response(404), response(200)]):
            with self.assertRaisesRegex(DistributionError, "already exists"):
                release.check_remote_absent(REPOSITORY, "speech-models-v1", runner=self.runner(replies))
        failures = [response(status, stderr="TOKEN_SECRET") for status in (401, 403, 429, 500)]
        failures += [response(404, returncode=0), subprocess.TimeoutExpired("gh", 30)]
        for failure in failures:
            with self.assertRaises(DistributionError) as raised:
                release.check_remote_absent(REPOSITORY, "speech-models-v1",
                                            runner=self.runner([response(200, {"full_name": REPOSITORY}), failure]))
            self.assertNotIn("TOKEN_SECRET", str(raised.exception))
        for first in (response(404), response(200, {"full_name": "other/repository"})):
            with self.assertRaisesRegex(DistributionError, "Repository access"):
                release.check_remote_absent(REPOSITORY, "speech-models-v1", runner=self.runner([first]))

    def test_tags_and_repositories_are_validated_before_running_gh(self):
        for repository, tag in (("../repo", "speech-models-v1"), (REPOSITORY, "codegen-models-v1"),
                                (REPOSITORY, "speech-models-v0"), (REPOSITORY, "speech-models-v1; echo")):
            with self.assertRaises(DistributionError):
                release.check_remote_absent(repository, tag, runner=lambda *_a, **_k: self.fail("gh must not run"))


class WorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (support.REPOSITORY_ROOT / ".github/workflows/publish-speech-models.yml").read_text(encoding="utf-8")

    def test_review_reproduction_and_preflight_precede_mutation_and_readback_follows(self):
        ordered = ["Require the default branch", "Run speech model distribution tests", "Missing offline-reviewed signing input",
                   "Verify current and historical catalog signatures", "build_catalog.py", 'cmp "$CURRENT_CATALOG"',
                   "prepare_sources.py", "--asset-list build/speech-models-current/release-assets.txt", "--check-absent",
                   "gh api --method POST", "gh release create", "gh release edit", "gh release download", "--downloaded-release"]
        positions = [self.workflow.index(value) for value in ordered]
        self.assertEqual(sorted(positions), positions)
        for forbidden in ("--clobber", "gh release delete", "git push", "private", "secrets."):
            self.assertNotIn(forbidden, self.workflow)
        self.assertIn("--draft --verify-tag --latest=false", self.workflow)
        # File names follow the newest catalog schema; only the history lookup comment names catalog-v1.json.
        self.assertIn("distribution.CATALOG_FILE", self.workflow)
        self.assertNotIn("catalogs/catalog-v1", self.workflow)

    def test_permissions_environment_and_action_pins(self):
        for expected in ("workflow_dispatch:", "contents: write", "environment: speech-models-release",
                         "group: publish-speech-models-", "cancel-in-progress: false", "persist-credentials: false",
                         "python-version: '3.12'", "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
                         "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065", "default: speech-models-v2"):
            self.assertIn(expected, self.workflow)
        codegen = (support.REPOSITORY_ROOT / ".github/workflows/publish-codegen-models.yml").read_text(encoding="utf-8")
        self.assertNotIn("speech-models", codegen)

    def test_embedded_shell_scripts_have_valid_bash_syntax(self):
        candidates = []
        git = shutil.which("git")
        if git:
            candidates.append(Path(git).resolve().parents[1] / "bin/bash.exe")
        bash = next((str(path) for path in candidates if path.is_file()), None) or shutil.which("bash")
        if bash is None:
            self.skipTest("Bash is unavailable; GitHub's Linux runner executes this syntax check")
        scripts, current = [], None
        for line in self.workflow.splitlines():
            if line == "        run: |":
                current = []
                scripts.append(current)
            elif current is not None:
                if line.startswith("          "):
                    current.append(line[10:])
                elif not line.strip():
                    current.append("")
                else:
                    current = None
        self.assertGreaterEqual(len(scripts), 8)
        for index, script in enumerate(scripts):
            result = subprocess.run([bash, "-n"], input="\n".join(script) + "\n", text=True, capture_output=True, timeout=20)
            self.assertEqual(0, result.returncode, f"shell block {index}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
