import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib


TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
NAME = "autojs6_codegen_verify_release"
if NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(NAME, TOOLS / "verify_release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[NAME] = module
    spec.loader.exec_module(module)
release = sys.modules[NAME]
DistributionError = release.DistributionError
REPOSITORY = "fixture-owner/codegen-release-test"


def response(status, payload=None, returncode=None, stderr=""):
    return subprocess.CompletedProcess([], 0 if status == 200 and returncode is None else 1 if returncode is None else returncode,
                                       f"HTTP/2.0 {status} Result\nContent-Type: application/json\n\n" + json.dumps(payload or {}), stderr)


def write_package(path):
    binary = struct.pack("<4sHHIdd", b"AJCG", 1, 1, 1, 0., 1.) + struct.pack("<BHfff", 1, 0, .5, -.25, .75)
    binary += struct.pack("<I", zlib.crc32(binary) & 0xFFFFFFFF)
    names = ["rule_rank_norm"]
    names_hash = hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]
    empty = {"groups": 0, "top1Survival": None, "ruleTop1Survival": None, "regret": None}
    manifest = {
        "format": 1, "modelId": "autojs6.codegen.tiny-test", "displayName": {"en": "Test model"},
        "versionCode": 1, "versionName": "1.0.0", "kind": "ranker", "algorithm": "catboost-oblivious",
        "featureSchemaVersion": 1, "featureNamesHash": names_hash,
        "model": {"file": "model.bin", "size": len(binary), "sha256": hashlib.sha256(binary).hexdigest(), "trees": 1, "depth": 1, "features": 1},
        "dataset": {"datasetId": "test-dataset", "groups": 3, "createdAt": "2026-10-03T00:00:00Z"},
        "metrics": {"test": {"groups": 3, "top1Survival": 1., "ruleTop1Survival": .5, "regret": 0.}, "realTest": empty},
        "training": {"catboostVersion": "1.2.10", "pythonVersion": "3.12.12", "hostCommit": "a" * 40, "trainedAt": "2026-10-03T00:00:00Z"},
        "minHostVersionCode": 1, "license": "MPL-2.0", "publisher": "AutoJs6",
    }
    schema = {"format": 1, "featureSchemaVersion": 1, "names": names, "namesHash": names_hash}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in (("manifest.json", json.dumps(manifest).encode()), ("model.bin", binary),
                              ("features.json", json.dumps(schema).encode()), ("MODEL_CARD.md", b"# Controlled test model\n"),
                              ("LICENSE", b"MPL-2.0\n")):
            archive.writestr(name, content)
    return manifest


class ReleaseVerificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        temporary = self.assets / "temporary.ajcgm"
        manifest = write_package(temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        self.filename = f"autojs6-codegen-{manifest['modelId']}-v1-{digest[:8]}.ajcgm"
        self.package = self.assets / self.filename
        temporary.rename(self.package)
        url = f"https://github.com/{REPOSITORY}/releases/download/codegen-models-v1/{self.filename}"
        version = {field: manifest[field] for field in ("versionCode", "versionName", "featureSchemaVersion", "featureNamesHash", "minHostVersionCode", "metrics")}
        version.update({"datasetId": "test-dataset", "license": {"spdx": "MPL-2.0"}, "releasedAt": "2026-10-03T01:00:00Z",
                        "artifact": {"fileName": self.filename, "size": self.package.stat().st_size, "sha256": digest, "url": url, "urls": [url]}})
        self.catalog = {"schemaVersion": 1, "catalogVersion": 1, "releaseTag": "codegen-models-v1",
                        "generatedAt": "2026-10-03T01:00:00Z", "repository": REPOSITORY,
                        "models": [{"modelId": manifest["modelId"], "displayName": manifest["displayName"],
                                    "summary": {"en": "Controlled distribution fixture"}, "recommendedVersionCode": 1, "versions": [version]}]}
        self.catalog_path = self.root / "catalog-v1.json"
        self.signature = self.root / "catalog-v1.sig.json"
        self.signature.write_bytes(b'{"offline-review-fixture":true}\n')
        self.save_catalog()

    def save_catalog(self):
        self.catalog_path.write_bytes(release.distribution.canonical_json_bytes(self.catalog))

    def verify(self, **kwargs):
        return release.verify_release(self.catalog_path, self.assets, expected_repository=REPOSITORY, allow_test_models=True, **kwargs)

    def test_valid_current_assets_and_exact_downloaded_reviewed_files(self):
        self.assertEqual(1, self.verify()["models"])
        (self.assets / "catalog-v1.json").write_bytes(self.catalog_path.read_bytes())
        (self.assets / "catalog-v1.sig.json").write_bytes(self.signature.read_bytes())
        result = self.verify(downloaded_release=True, signature_path=self.signature)
        self.assertTrue(result["downloadedRelease"])

    def test_conflict_in_earlier_signed_history_is_not_hidden_by_an_unchanged_latest_version(self):
        first = json.loads(json.dumps(self.catalog))
        second = json.loads(json.dumps(first))
        second.update(catalogVersion=2, releaseTag="codegen-models-v2")
        second["models"][0]["versions"][0]["datasetId"] = "changed-immutable-metadata"
        third = json.loads(json.dumps(second))
        third.update(catalogVersion=3, releaseTag="codegen-models-v3")
        # Isolated signatures and only the latest edge cannot detect an older conflict.
        for catalog in (first, second, third):
            release.distribution.validate_catalog(catalog, allow_test_models=True)
        release.distribution.validate_catalog(third, previous_catalog=second, allow_test_models=True)
        with self.assertRaisesRegex(DistributionError, "Historical model version content changed"):
            release.distribution.validate_catalog(second, previous_catalog=first, allow_test_models=True)

    def test_downloaded_catalog_or_signature_byte_changes_are_rejected(self):
        for filename, source in (("catalog-v1.json", self.catalog_path), ("catalog-v1.sig.json", self.signature)):
            (self.assets / filename).write_bytes(source.read_bytes())
        for filename in ("catalog-v1.json", "catalog-v1.sig.json"):
            path = self.assets / filename
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(filename=filename), self.assertRaisesRegex(DistributionError, "differs from the offline-reviewed"):
                self.verify(downloaded_release=True, signature_path=self.signature)
            path.write_bytes(original)

    def test_missing_unexpected_or_nested_assets_are_rejected(self):
        content = self.package.read_bytes()
        self.package.unlink()
        with self.assertRaisesRegex(DistributionError, "Missing release"):
            self.verify()
        self.package.write_bytes(content)
        extra = self.assets / "unexpected.txt"
        extra.write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "Unexpected release"):
            self.verify()
        extra.unlink()
        (self.assets / "nested").mkdir()
        with self.assertRaisesRegex(DistributionError, "ordinary files"):
            self.verify()

    def test_asset_size_and_hash_are_checked_before_package_parsing(self):
        original = self.package.read_bytes()
        self.package.write_bytes(original + b"x")
        with self.assertRaisesRegex(DistributionError, "size differs"):
            self.verify()
        changed = bytearray(original)
        changed[-1] ^= 1
        self.package.write_bytes(changed)
        with self.assertRaisesRegex(DistributionError, "SHA-256 differs"):
            self.verify()

    def test_valid_package_must_match_catalog_manifest_fields(self):
        self.catalog["models"][0]["versions"][0]["datasetId"] = "different-dataset"
        self.save_catalog()
        with self.assertRaisesRegex(DistributionError, "dataset"):
            self.verify()

    def test_current_release_and_all_artifacts_modes_distinguish_historical_urls(self):
        self.catalog.update(catalogVersion=2, releaseTag="codegen-models-v2", generatedAt="2026-10-04T00:00:00Z")
        self.save_catalog()
        self.assertEqual(1, self.verify(all_artifacts=True)["models"])
        with self.assertRaisesRegex(DistributionError, "Unexpected release"):
            self.verify()
        self.package.unlink()
        self.assertEqual(0, self.verify()["models"])
        with self.assertRaisesRegex(DistributionError, "Missing release"):
            self.verify(all_artifacts=True)

    def test_release_asset_list_cannot_add_duplicate_or_unexpected_paths(self):
        listing = self.root / "release-assets.txt"
        listing.write_text(self.filename + "\n", encoding="utf-8")
        self.verify(asset_list=listing)
        for entries in (self.filename + "\n" + self.filename, "../outside.ajcgm", ""):
            listing.write_text(entries, encoding="utf-8")
            with self.subTest(entries=entries), self.assertRaisesRegex(DistributionError, "release-assets.txt"):
                self.verify(asset_list=listing)

    def test_tiny_model_requires_explicit_noncanonical_test_policy(self):
        with self.assertRaises(DistributionError):
            release.verify_release(self.catalog_path, self.assets, expected_repository=REPOSITORY)
        for repository in (release.OFFICIAL_REPOSITORY, release.OFFICIAL_REPOSITORY.lower()):
            self.catalog["repository"] = repository
            artifact = self.catalog["models"][0]["versions"][0]["artifact"]
            artifact["url"] = artifact["urls"][0] = f"https://github.com/{repository}/releases/download/codegen-models-v1/{self.filename}"
            self.save_catalog()
            with self.subTest(repository=repository), self.assertRaises(DistributionError):
                release.verify_release(self.catalog_path, self.assets, expected_repository=repository, allow_test_models=True)


class RemotePreflightTest(unittest.TestCase):
    def runner(self, responses):
        self.calls = []
        replies = iter(responses)

        def run(command, **kwargs):
            self.calls.append(command)
            item = next(replies)
            if isinstance(item, Exception):
                raise item
            return item

        return run

    def test_absence_requires_authenticated_repository_then_two_explicit_404s(self):
        runner = self.runner([response(200, {"full_name": REPOSITORY}), response(404), response(404)])
        release.check_remote_absent(REPOSITORY, "codegen-models-v1", runner=runner)
        self.assertEqual(3, len(self.calls))
        self.assertEqual(f"repos/{REPOSITORY}", self.calls[0][-1])
        self.assertTrue(all(command[:7] == ["gh", "api", "--hostname", "github.com", "--method", "GET", "--include"] for command in self.calls))

    def test_existing_release_or_tag_is_never_accepted(self):
        for replies in ([response(200, {"full_name": REPOSITORY}), response(200)],
                        [response(200, {"full_name": REPOSITORY}), response(404), response(200)]):
            with self.subTest(replies=len(replies)), self.assertRaisesRegex(DistributionError, "already exists"):
                release.check_remote_absent(REPOSITORY, "codegen-models-v1", runner=self.runner(replies))

    def test_auth_rate_limit_server_transport_and_malformed_responses_fail_closed(self):
        errors = [response(status, stderr="TOKEN_SECRET") for status in (401, 403, 429, 500)]
        errors += [response(404, returncode=0), response(200, returncode=1),
                   subprocess.CompletedProcess([], 1, "", "TOKEN_SECRET"), subprocess.TimeoutExpired("gh", 30)]
        for error in errors:
            with self.subTest(error=type(error).__name__), self.assertRaises(DistributionError) as raised:
                release.check_remote_absent(REPOSITORY, "codegen-models-v1", runner=self.runner([response(200, {"full_name": REPOSITORY}), error]))
            self.assertNotIn("TOKEN_SECRET", str(raised.exception))

    def test_inaccessible_or_wrong_repository_never_reaches_release_lookup(self):
        for first in (response(404), response(200, {"full_name": "other/repository"}), response(200)):
            with self.assertRaisesRegex(DistributionError, "Repository access/identity"):
                release.check_remote_absent(REPOSITORY, "codegen-models-v1", runner=self.runner([first]))
            self.assertEqual(1, len(self.calls))

    def test_repository_and_tag_cannot_inject_remote_commands(self):
        for repository, tag in (("../repo", "codegen-models-v1"), (REPOSITORY, "v1; echo secret"),
                                 (REPOSITORY, "codegen-models-v0"), (REPOSITORY, "ace-fonts-v1")):
            with self.assertRaises(DistributionError):
                release.check_remote_absent(repository, tag, runner=lambda *_args, **_kwargs: self.fail("Must reject before invoking gh"))


class WorkflowContractTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/publish-codegen-models.yml").read_text(encoding="utf-8")

    def test_review_precedes_mutation_and_full_readback_follows_publication(self):
        ordered = ["Require the default branch", "Run model distribution tests", "Verify current and historical catalog signatures",
                   "Reproduce the reviewed catalog", "--check-absent", 'gh api --method POST', 'gh release create',
                   'gh release edit', 'gh release download', '--downloaded-release']
        positions = [self.workflow.index(value) for value in ordered]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("--draft --verify-tag --latest=false", self.workflow)
        self.assertNotIn("--clobber", self.workflow)
        self.assertNotIn("gh release delete", self.workflow)
        self.assertNotIn("git push", self.workflow)
        self.assertIn("Missing offline-reviewed signing input", self.workflow)

    def test_permissions_scopes_and_action_pins_match_existing_distribution(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("contents: write", self.workflow)
        self.assertIn("environment: codegen-models-release", self.workflow)
        self.assertIn("group: publish-codegen-models-", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertIn("python-version: '3.12'", self.workflow)
        self.assertIn("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", self.workflow)
        self.assertIn("actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065", self.workflow)
        self.assertIn("repository.casefold()", self.workflow)
        self.assertIn("default: false", self.workflow)
        self.assertIn('"1" if not catalog["models"] else "0"', self.workflow)
        self.assertIn('if [[ "$EMPTY_BOOTSTRAP" == "1" ]]; then bootstrap_args=(--empty-bootstrap); fi', self.workflow)

    def test_each_verified_history_edge_is_checked_before_release_reproduction(self):
        history_loop = self.workflow.split('for (( version=1; version<CATALOG_VERSION; version++ )); do', 1)[1].split('\n          done', 1)[0]
        self.assertIn('verify_catalog.py', history_loop)
        self.assertIn('validate_catalog.py "$history/catalog-v1.json"', history_loop)
        self.assertIn('--previous-catalog "codegen-models/catalogs/history/v$((version - 1))/catalog-v1.json"', history_loop)
        self.assertIn('"${previous_history_args[@]}"', history_loop)

    def test_embedded_shell_scripts_have_valid_bash_syntax(self):
        candidates = []
        git = shutil.which("git")
        if git:
            candidates.append(Path(git).resolve().parents[1] / "bin/bash.exe")
        candidates += [Path("C:/Program Files/Git/bin/bash.exe")]
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
        self.assertGreaterEqual(len(scripts), 7)
        for index, script in enumerate(scripts):
            result = subprocess.run([bash, "-n"], input="\n".join(script) + "\n", text=True, capture_output=True, timeout=20)
            self.assertEqual(0, result.returncode, f"shell block {index}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
