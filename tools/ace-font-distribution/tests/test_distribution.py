from __future__ import annotations

import copy
import base64
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TOOL_DIR.parents[1]
HOST_BOOTSTRAP = REPOSITORY_ROOT / "app/src/main/res/raw/ace_font_catalog_v1.json"
sys.path.insert(0, str(TOOL_DIR))

from crypto import (  # noqa: E402
    find_openssl,
    generate_key_pair,
    sign_catalog,
    verify_catalog_signature,
)
from distribution import (  # noqa: E402
    DistributionError,
    build_catalog,
    canonical_json_bytes,
    read_json,
    validate_catalog,
    validate_manifest,
    validate_woff2,
    write_release,
)
from export_sources import export_sources  # noqa: E402
from prepare_repository import PREPARE_MARKER, prepare_repository  # noqa: E402
from verify_release import verify_release  # noqa: E402


def synthetic_woff2() -> bytes:
    payload = b"x"
    length = 48 + len(payload)
    header = struct.pack(
        ">4sIIHHIIHHIIIII",
        b"wOF2",
        0x00010000,
        length,
        1,
        0,
        128,
        len(payload),
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    return header + payload


def synthetic_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "catalogVersion": 1,
        "minHostVersionCode": 5221,
        "releaseTag": "ace-fonts-v1",
        "expectedFontCount": 1,
        "fonts": [
            {
                "id": "test_mono",
                "displayName": "Test Mono",
                "family": "Test Mono",
                "order": 10,
                "author": "Test Author",
                "licenseName": "Test License",
                "licenseSpdx": "LicenseRef-Test",
                "sourceRepository": "https://github.com/example/test-mono",
                "upstreamVersion": None,
                "artifactVersion": 1,
                "artifactReleaseTag": "ace-fonts-v1",
                "autoJs6SourceCommit": "1" * 40,
                "fontPath": "test/Test-Regular.woff2",
                "noticePaths": ["test/LICENSE.txt"],
            }
        ],
    }


class Woff2ValidationTest(unittest.TestCase):
    def test_accepts_valid_fixed_header(self) -> None:
        validate_woff2(synthetic_woff2())

    def test_rejects_bad_signature(self) -> None:
        content = bytearray(synthetic_woff2())
        content[:4] = b"nope"
        with self.assertRaisesRegex(DistributionError, "signature"):
            validate_woff2(bytes(content))

    def test_rejects_declared_length_mismatch(self) -> None:
        content = bytearray(synthetic_woff2())
        content[8:12] = struct.pack(">I", len(content) + 1)
        with self.assertRaisesRegex(DistributionError, "length"):
            validate_woff2(bytes(content))


class ManifestValidationTest(unittest.TestCase):
    def test_rejects_bundled_iosevka_id(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"][0]["id"] = "iosevka"
        with self.assertRaisesRegex(DistributionError, "reserved"):
            validate_manifest(manifest)

    def test_rejects_duplicate_remote_id(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"].append(copy.deepcopy(manifest["fonts"][0]))
        manifest["fonts"][1]["order"] = 20
        manifest["expectedFontCount"] = 2
        with self.assertRaisesRegex(DistributionError, "duplicate font ID"):
            validate_manifest(manifest)

    def test_rejects_catalog_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test").mkdir()
            (root / "test/Test-Regular.woff2").write_bytes(synthetic_woff2())
            (root / "test/LICENSE.txt").write_text("license", encoding="utf-8")
            catalog, _ = build_catalog(synthetic_manifest(), root, "example/fonts")
            with self.assertRaisesRegex(DistributionError, "below required"):
                validate_catalog(catalog, minimum_catalog_version=2)

    def test_accepts_missing_autojs6_source_commit(self) -> None:
        manifest = synthetic_manifest()
        del manifest["fonts"][0]["autoJs6SourceCommit"]
        validate_manifest(manifest)

    def test_rejects_artifact_tag_version_mismatch(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"][0]["artifactReleaseTag"] = "ace-fonts-v2"
        with self.assertRaisesRegex(DistributionError, "match artifactVersion"):
            validate_manifest(manifest)

    def test_rejects_source_path_escape(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"][0]["fontPath"] = "../outside.woff2"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fonts"
            root.mkdir()
            (root.parent / "outside.woff2").write_bytes(synthetic_woff2())
            with self.assertRaisesRegex(DistributionError, "escapes"):
                build_catalog(manifest, root, "example/fonts")


class ReleaseGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        (self.source / "test").mkdir(parents=True)
        (self.source / "test/Test-Regular.woff2").write_bytes(synthetic_woff2())
        (self.source / "test/LICENSE.txt").write_text("test license\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reproducible_bundle_and_bootstrap_catalog(self) -> None:
        catalog, assets = build_catalog(synthetic_manifest(), self.source, "example/fonts")
        first = self.root / "first"
        second = self.root / "second"
        write_release(catalog, assets, first, overwrite=False)
        write_release(catalog, assets, second, overwrite=False)
        self.assertEqual(
            (first / "catalog-v1.json").read_bytes(),
            (second / "catalog-v1.json").read_bytes(),
        )
        self.assertEqual(
            (first / "catalog-v1.json").read_bytes(),
            (first / "bootstrap-catalog-v1.json").read_bytes(),
        )
        verify_release(catalog, first / "assets")

    def test_release_verifier_detects_tampering(self) -> None:
        catalog, assets = build_catalog(synthetic_manifest(), self.source, "example/fonts")
        output = self.root / "release"
        write_release(catalog, assets, output, overwrite=False)
        font_name = catalog["fonts"][0]["artifact"]["fileName"]
        (output / "assets" / font_name).write_bytes(b"tampered")
        with self.assertRaisesRegex(DistributionError, "size does not match"):
            verify_release(catalog, output / "assets")

    def test_refuses_to_overwrite_unmarked_directory(self) -> None:
        catalog, assets = build_catalog(synthetic_manifest(), self.source, "example/fonts")
        output = self.root / "unrelated"
        output.mkdir()
        (output / "keep.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "refusing"):
            write_release(catalog, assets, output, overwrite=True)
        self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "keep")

    def _version_two_manifest(self) -> dict:
        manifest = synthetic_manifest()
        manifest["catalogVersion"] = 2
        manifest["releaseTag"] = "ace-fonts-v2"
        added = copy.deepcopy(manifest["fonts"][0])
        added.update(
            {
                "id": "second_mono",
                "displayName": "Second Mono",
                "family": "Second Mono",
                "order": 20,
                "fontPath": "second/Second-Regular.woff2",
                "noticePaths": ["second/LICENSE.txt"],
                "artifactVersion": 2,
                "artifactReleaseTag": "ace-fonts-v2",
            }
        )
        del added["autoJs6SourceCommit"]
        manifest["fonts"].append(added)
        manifest["expectedFontCount"] = 2
        (self.source / "second").mkdir()
        (self.source / "second/Second-Regular.woff2").write_bytes(synthetic_woff2())
        (self.source / "second/LICENSE.txt").write_text(
            "second license\n", encoding="utf-8"
        )
        return manifest

    def test_catalog_v2_reuses_v1_and_outputs_only_v2_assets(self) -> None:
        repository = "example/shared-assets"
        catalog_v1, assets_v1 = build_catalog(
            synthetic_manifest(), self.source, repository
        )
        manifest_v2 = self._version_two_manifest()
        catalog_v2, assets_v2 = build_catalog(
            manifest_v2, self.source, repository, catalog_v1
        )

        original = next(font for font in catalog_v2["fonts"] if font["id"] == "test_mono")
        added = next(font for font in catalog_v2["fonts"] if font["id"] == "second_mono")
        self.assertIn("/ace-fonts-v1/", original["artifact"]["url"])
        self.assertIn("/ace-fonts-v2/", added["artifact"]["url"])
        self.assertNotIn("autoJs6Snapshot", added["source"])
        self.assertTrue(set(assets_v2).isdisjoint(assets_v1))
        self.assertEqual(
            set(assets_v2),
            {added["artifact"]["fileName"], added["license"]["files"][0]["fileName"]},
        )

        output = self.root / "release-v2"
        write_release(catalog_v2, assets_v2, output, overwrite=False)
        verify_release(catalog_v2, output / "assets")

    def test_reusing_old_release_requires_previous_catalog(self) -> None:
        manifest_v2 = self._version_two_manifest()
        with self.assertRaisesRegex(DistributionError, "previous catalog is required"):
            build_catalog(manifest_v2, self.source, "example/shared-assets")

    def test_reusing_old_release_rejects_changed_bytes(self) -> None:
        repository = "example/shared-assets"
        catalog_v1, _ = build_catalog(synthetic_manifest(), self.source, repository)
        manifest_v2 = self._version_two_manifest()
        changed = bytearray(synthetic_woff2())
        changed[-1] = ord("y")
        (self.source / "test/Test-Regular.woff2").write_bytes(changed)
        with self.assertRaisesRegex(DistributionError, "changed artifact"):
            build_catalog(manifest_v2, self.source, repository, catalog_v1)


class RepositoryPreparationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "source-repository"
        source = self.repository / "app/src/main/assets/editor/ace-builds-1.4.12/fonts/test"
        source.mkdir(parents=True)
        (source / "Test-Regular.woff2").write_bytes(synthetic_woff2())
        (source / "LICENSE.txt").write_text("committed license\n", encoding="utf-8")
        subprocess.run(["git", "init", str(self.repository)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.repository), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "-c",
                "user.name=AutoJs6 Test",
                "-c",
                "user.email=autojs6-test@example.invalid",
                "commit",
                "-m",
                "font sources",
            ],
            check=True,
            capture_output=True,
        )
        self.commit = subprocess.run(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exports_exact_committed_bytes_not_worktree_bytes(self) -> None:
        source = self.repository / "app/src/main/assets/editor/ace-builds-1.4.12/fonts/test"
        (source / "LICENSE.txt").write_text("changed worktree\n", encoding="utf-8")
        output = self.root / "exported"
        resolved = export_sources(
            self.repository, self.commit, synthetic_manifest(), output
        )
        self.assertEqual(resolved, self.commit)
        self.assertEqual(
            (output / "test/LICENSE.txt").read_text(encoding="utf-8"),
            "committed license\n",
        )

    def test_rejects_git_lfs_pointer_instead_of_notice_bytes(self) -> None:
        notice = (
            self.repository
            / "app/src/main/assets/editor/ace-builds-1.4.12/fonts/test/LICENSE.txt"
        )
        notice.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{'1' * 64}\n"
            "size 123\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(self.repository), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "-c",
                "user.name=AutoJs6 Test",
                "-c",
                "user.email=autojs6-test@example.invalid",
                "commit",
                "-m",
                "lfs pointer",
            ],
            check=True,
            capture_output=True,
        )
        pointer_commit = subprocess.run(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        with self.assertRaisesRegex(DistributionError, "Git LFS pointer"):
            export_sources(
                self.repository,
                pointer_commit,
                synthetic_manifest(),
                self.root / "lfs-export",
            )

    def test_prepares_unsigned_self_contained_repository(self) -> None:
        manifest_path = self.root / "manifest.json"
        manifest_path.write_bytes(canonical_json_bytes(synthetic_manifest()))
        destination = self.root / "shared-assets"
        commit, catalog_path = prepare_repository(
            self.repository,
            self.commit,
            destination,
            manifest_path,
            repository="example/shared-assets",
        )
        self.assertEqual(commit, self.commit)
        self.assertTrue((destination / "ace-fonts/sources/test/Test-Regular.woff2").is_file())
        self.assertTrue((destination / ".github/workflows/publish-ace-fonts.yml").is_file())
        self.assertFalse((destination / "ace-fonts/catalogs/catalog-v1.sig.json").exists())
        self.assertFalse(any(destination.rglob("*.private.pem")))
        self.assertFalse((destination / "tools/ace-font-distribution/sources").exists())
        self.assertEqual(read_json(catalog_path)["repository"], "example/shared-assets")
        self.assertIn(
            PREPARE_MARKER,
            (destination / ".gitignore").read_text(encoding="utf-8"),
        )
        workflow = (destination / ".github/workflows/publish-ace-fonts.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--draft", workflow)
        self.assertIn('--raw-field sha="$GITHUB_SHA"', workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("--latest=false", workflow)
        self.assertIn('refs/heads/$DEFAULT_BRANCH', workflow)
        self.assertIn('git ls-remote origin "refs/tags/$RELEASE_TAG"', workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("environment: ace-fonts-release", workflow)
        self.assertIn('gh release edit "$RELEASE_TAG" --draft=false', workflow)

    def test_prepares_from_a_tracked_source_snapshot_without_git_history(self) -> None:
        manifest_path = self.root / "manifest.json"
        manifest_path.write_bytes(canonical_json_bytes(synthetic_manifest()))
        tracked_source = (
            self.repository
            / "app/src/main/assets/editor/ace-builds-1.4.12/fonts"
        )
        destination = self.root / "shared-assets-from-tracked-sources"
        source_identity, catalog_path = prepare_repository(
            None,
            None,
            destination,
            manifest_path,
            repository="example/shared-assets",
            tracked_source_root=tracked_source,
        )
        self.assertTrue(source_identity.startswith("tracked:"))
        self.assertEqual(
            (destination / "ace-fonts/sources/test/LICENSE.txt").read_text(
                encoding="utf-8"
            ),
            "committed license\n",
        )
        self.assertEqual(read_json(catalog_path)["repository"], "example/shared-assets")

    def test_rejects_unreviewed_files_in_a_tracked_source_snapshot(self) -> None:
        manifest_path = self.root / "manifest.json"
        manifest_path.write_bytes(canonical_json_bytes(synthetic_manifest()))
        tracked_source = (
            self.repository
            / "app/src/main/assets/editor/ace-builds-1.4.12/fonts"
        )
        (tracked_source / "secret.txt").write_text("must not be copied\n", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "unreviewed file"):
            prepare_repository(
                None,
                None,
                self.root / "shared-assets-with-extra-file",
                manifest_path,
                repository="example/shared-assets",
                tracked_source_root=tracked_source,
            )


class CurrentFontIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(HOST_BOOTSTRAP.is_file(), "requires the AutoJs6 Android host checkout")
    def test_bootstrap_has_exact_eight_online_fonts(self) -> None:
        catalog = read_json(HOST_BOOTSTRAP)
        validate_catalog(catalog)
        self.assertEqual(catalog["repository"], "SuperMonster003/AutoJs6-Shared-Assets")
        self.assertEqual(catalog["releaseTag"], "ace-fonts-v1")
        self.assertEqual(
            {font["id"] for font in catalog["fonts"]},
            {
                "cascadia_code",
                "fira_code",
                "hack",
                "ibm_plex_mono",
                "intel_one_mono",
                "iosevka_slab",
                "jetbrains_mono",
                "source_code_pro",
            },
        )
        self.assertNotIn("iosevka", {font["id"] for font in catalog["fonts"]})
        hashes = {font["id"]: font["artifact"]["sha256"] for font in catalog["fonts"]}
        self.assertEqual(
            hashes["iosevka_slab"],
            "4e317adc0a6d556dd5cf361966cb2dd3487a3aa4a9e477770306ea68dd477e13",
        )
        self.assertEqual(catalog["minHostVersionCode"], 5221)
        for font in catalog["fonts"]:
            self.assertIn(
                "github.com/SuperMonster003/AutoJs6-Shared-Assets/releases/download/ace-fonts-v1/autojs6-ace-font-",
                font["artifact"]["url"],
            )

        packaged_fonts = (
            REPOSITORY_ROOT
            / "app/src/main/assets/editor/ace-builds-1.4.12/fonts"
        )
        packaged_woff2 = sorted(packaged_fonts.rglob("*.woff2"))
        self.assertEqual(
            [path.relative_to(packaged_fonts).as_posix() for path in packaged_woff2],
            ["iosevka/Iosevka-Regular.woff2"],
        )

    @unittest.skipUnless(HOST_BOOTSTRAP.is_file(), "requires the AutoJs6 Android host checkout")
    def test_host_pins_the_distribution_public_key(self) -> None:
        public_der = (
            REPOSITORY_ROOT
            / "app/src/main/res/raw/ace_font_catalog_public_key_v1.der"
        ).read_bytes()
        public_pem = (TOOL_DIR / "catalog-v1-signing-public.pem").read_text(
            encoding="ascii"
        )
        pem_der = base64.b64decode(
            public_pem.replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", "")
            .strip()
        )
        self.assertEqual(public_der, pem_der)
        key_id = f"p256-{hashlib.sha256(public_der).hexdigest()[:16]}"
        self.assertEqual(key_id, "p256-fc433f8ba81333f7")
        manager_source = (
            REPOSITORY_ROOT
            / "app/src/main/java/org/autojs/autojs/ui/edit/editor/ace/AceEditorFontManager.kt"
        ).read_text(encoding="utf-8")
        self.assertIn(f'CATALOG_KEY_ID = "{key_id}"', manager_source)
        self.assertIn(
            "SuperMonster003/AutoJs6-Shared-Assets/main/ace-fonts/catalogs/catalog-v1.json",
            manager_source,
        )
        self.assertIn(
            "SuperMonster003/AutoJs6-Shared-Assets/main/ace-fonts/catalogs/catalog-v1.sig.json",
            manager_source,
        )

    @unittest.skipUnless(HOST_BOOTSTRAP.is_file(), "requires the AutoJs6 Android host checkout")
    def test_initial_catalog_signature_matches_packaged_bootstrap(self) -> None:
        if read_json(HOST_BOOTSTRAP).get("repository") != "SuperMonster003/AutoJs6-Shared-Assets":
            self.skipTest("Android bootstrap has not yet migrated to Shared Assets")
        try:
            find_openssl()
        except DistributionError as error:
            self.skipTest(str(error))
        bootstrap = HOST_BOOTSTRAP.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "catalog-v1.json"
            catalog.write_bytes(bootstrap)
            envelope = verify_catalog_signature(
                catalog,
                TOOL_DIR / "catalog-v1.sig.json",
                TOOL_DIR / "catalog-v1-signing-public.pem",
                expected_key_id="p256-fc433f8ba81333f7",
            )
        self.assertEqual(envelope["catalog"], "catalog-v1.json")

    def test_schema_document_is_valid_json(self) -> None:
        schema = json.loads((TOOL_DIR / "catalog-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertIn("AutoJs6-Shared-Assets", schema["$id"])
        self.assertEqual(
            schema["properties"]["releaseTag"]["pattern"],
            "^ace-fonts-v[1-9][0-9]*$",
        )
        signature_schema = json.loads(
            (TOOL_DIR / "signature-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(signature_schema["additionalProperties"])
        self.assertEqual(
            signature_schema["properties"]["algorithm"]["const"],
            "ECDSA_P256_SHA256",
        )


class SignatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.openssl = find_openssl()
        except DistributionError as error:
            raise unittest.SkipTest(str(error))

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source/test"
        source.mkdir(parents=True)
        (source / "Test-Regular.woff2").write_bytes(synthetic_woff2())
        (source / "LICENSE.txt").write_text("license\n", encoding="utf-8")
        catalog, _ = build_catalog(
            synthetic_manifest(), self.root / "source", "example/fonts"
        )
        self.catalog_path = self.root / "catalog-v1.json"
        self.catalog_path.write_bytes(canonical_json_bytes(catalog))
        self.private_key = self.root / "private.pem"
        self.public_pem = self.root / "public.pem"
        self.public_der = self.root / "public.der"
        self.key_id = generate_key_pair(
            self.private_key,
            self.public_pem,
            self.public_der,
            self.openssl,
        )
        self.signature_path = self.root / "catalog-v1.sig.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_signs_and_verifies_with_pem_and_der_spki(self) -> None:
        sign_catalog(
            self.catalog_path,
            self.private_key,
            self.signature_path,
            self.key_id,
            self.openssl,
        )
        verify_catalog_signature(
            self.catalog_path,
            self.signature_path,
            self.public_pem,
            self.key_id,
            openssl_value=self.openssl,
        )
        verify_catalog_signature(
            self.catalog_path,
            self.signature_path,
            self.public_der,
            self.key_id,
            openssl_value=self.openssl,
        )

    def test_rejects_tampered_catalog(self) -> None:
        sign_catalog(
            self.catalog_path,
            self.private_key,
            self.signature_path,
            self.key_id,
            self.openssl,
        )
        catalog = read_json(self.catalog_path)
        catalog["fonts"][0]["displayName"] = "Tampered Mono"
        self.catalog_path.write_bytes(canonical_json_bytes(catalog))
        with self.assertRaisesRegex(DistributionError, "OpenSSL command failed"):
            verify_catalog_signature(
                self.catalog_path,
                self.signature_path,
                self.public_pem,
                self.key_id,
                openssl_value=self.openssl,
            )

    def test_rejects_unknown_signature_envelope_field(self) -> None:
        sign_catalog(
            self.catalog_path,
            self.private_key,
            self.signature_path,
            self.key_id,
            self.openssl,
        )
        envelope = read_json(self.signature_path)
        envelope["createdAt"] = "2026-07-18T00:00:00Z"
        self.signature_path.write_bytes(canonical_json_bytes(envelope))
        with self.assertRaisesRegex(DistributionError, "exactly"):
            verify_catalog_signature(
                self.catalog_path,
                self.signature_path,
                self.public_pem,
                self.key_id,
                openssl_value=self.openssl,
            )


if __name__ == "__main__":
    unittest.main()
