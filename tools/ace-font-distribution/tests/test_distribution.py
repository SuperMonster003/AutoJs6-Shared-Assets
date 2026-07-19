from __future__ import annotations

import copy
import base64
import hashlib
import importlib.util
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
SHARED_MANIFEST = TOOL_DIR / "font-sources.json"
SHARED_SOURCE_ROOT = REPOSITORY_ROOT / "ace-fonts/sources"
SHARED_CATALOG = REPOSITORY_ROOT / "ace-fonts/catalogs/catalog-v1.json"
SHARED_SIGNATURE = REPOSITORY_ROOT / "ace-fonts/catalogs/catalog-v1.sig.json"
V1_HISTORY_CATALOG = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/history/v1/catalog-v1.json"
)
V1_HISTORY_SIGNATURE = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/history/v1/catalog-v1.sig.json"
)
V1_HISTORY_MANIFEST = (
    REPOSITORY_ROOT / "ace-fonts/manifests/history/v1/font-sources.json"
)
V2_HISTORY_CATALOG = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/history/v2/catalog-v1.json"
)
V2_HISTORY_SIGNATURE = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/history/v2/catalog-v1.sig.json"
)
V2_HISTORY_MANIFEST = (
    REPOSITORY_ROOT / "ace-fonts/manifests/history/v2/font-sources.json"
)
V3_HISTORY_CATALOG = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/history/v3/catalog-v1.json"
)
V3_HISTORY_SIGNATURE = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/history/v3/catalog-v1.sig.json"
)
V3_HISTORY_MANIFEST = (
    REPOSITORY_ROOT / "ace-fonts/manifests/history/v3/font-sources.json"
)
PENDING_V4_CATALOG = (
    REPOSITORY_ROOT / "ace-fonts/catalogs/pending/v4/catalog-v1.json"
)
FONT_AUDIT_V4 = REPOSITORY_ROOT / "ace-fonts/audits/font-audit-v4.json"
SHARED_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
CATALOG_KEY_ID = "p256-fc433f8ba81333f7"
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
from font_audit import EXPECTED_CRITERIA, validate_font_audit  # noqa: E402
from prepare_repository import (  # noqa: E402
    GIT_ATTRIBUTES,
    PREPARE_MARKER,
    prepare_repository,
)
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
                "features": [],
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

    def test_accepts_explicit_font_features(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"][0]["features"] = [
            "mono",
            "nerd",
            "variable",
            "cn",
            "jp",
        ]
        validate_manifest(manifest)

    def test_accepts_missing_font_features_before_catalog_v3(self) -> None:
        for catalog_version in (1, 2):
            with self.subTest(catalog_version=catalog_version):
                manifest = synthetic_manifest()
                manifest["catalogVersion"] = catalog_version
                manifest["releaseTag"] = f"ace-fonts-v{catalog_version}"
                del manifest["fonts"][0]["features"]
                validate_manifest(manifest)

    def test_requires_explicit_font_features_from_catalog_v3(self) -> None:
        manifest = synthetic_manifest()
        manifest["catalogVersion"] = 3
        manifest["releaseTag"] = "ace-fonts-v3"
        del manifest["fonts"][0]["features"]
        with self.assertRaisesRegex(
            DistributionError, "features is required from catalogVersion 3"
        ):
            validate_manifest(manifest)

    def test_rejects_unknown_font_feature(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"][0]["features"] = ["powerline"]
        with self.assertRaisesRegex(DistributionError, "features values"):
            validate_manifest(manifest)

    def test_rejects_duplicate_or_noncanonical_font_features(self) -> None:
        manifest = synthetic_manifest()
        manifest["fonts"][0]["features"] = ["nerd", "nerd"]
        with self.assertRaisesRegex(DistributionError, "duplicates"):
            validate_manifest(manifest)

        manifest["fonts"][0]["features"] = ["jp", "mono"]
        with self.assertRaisesRegex(DistributionError, "canonical order"):
            validate_manifest(manifest)

    def test_catalog_v4_requires_complete_variant_metadata(self) -> None:
        manifest = synthetic_manifest()
        manifest["catalogVersion"] = 4
        manifest["releaseTag"] = "ace-fonts-v4"
        manifest["fonts"][0]["artifactVersion"] = 4
        manifest["fonts"][0]["artifactReleaseTag"] = "ace-fonts-v4"
        with self.assertRaisesRegex(DistributionError, "variant metadata"):
            validate_manifest(manifest)

        manifest["fonts"][0].update(
            {
                "groupId": "test_mono",
                "variantName": "Regular",
                "variantOrder": 0,
                "isDefaultVariant": True,
            }
        )
        validate_manifest(manifest)

    def test_rejects_invalid_variant_group(self) -> None:
        manifest = synthetic_manifest()
        manifest["catalogVersion"] = 4
        manifest["releaseTag"] = "ace-fonts-v4"
        first = manifest["fonts"][0]
        first.update(
            {
                "artifactVersion": 4,
                "artifactReleaseTag": "ace-fonts-v4",
                "groupId": "test_mono",
                "variantName": "Regular",
                "variantOrder": 0,
                "isDefaultVariant": True,
            }
        )
        second = copy.deepcopy(first)
        second.update(
            {
                "id": "test_mono_nf",
                "order": 20,
                "variantName": "NF",
                "variantOrder": 1,
            }
        )
        manifest["fonts"].append(second)
        manifest["expectedFontCount"] = 2
        with self.assertRaisesRegex(DistributionError, "exactly one default"):
            validate_manifest(manifest)

        second["isDefaultVariant"] = False
        with self.assertRaisesRegex(DistributionError, "highest variantOrder"):
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
        self.assertEqual(catalog["fonts"][0]["features"], [])
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

    def test_catalog_v3_can_publish_metadata_without_republishing_assets(self) -> None:
        repository = "example/shared-assets"
        catalog_v1, _ = build_catalog(synthetic_manifest(), self.source, repository)
        manifest_v2 = self._version_two_manifest()
        catalog_v2, _ = build_catalog(
            manifest_v2, self.source, repository, catalog_v1
        )
        manifest_v3 = copy.deepcopy(manifest_v2)
        manifest_v3["catalogVersion"] = 3
        manifest_v3["releaseTag"] = "ace-fonts-v3"
        manifest_v3["fonts"][0]["features"] = ["nerd"]
        manifest_v3["fonts"][1]["features"] = ["cn"]

        catalog_v3, assets_v3 = build_catalog(
            manifest_v3, self.source, repository, catalog_v2
        )

        self.assertEqual(assets_v3, {})
        self.assertEqual(
            [font["features"] for font in catalog_v3["fonts"]],
            [["nerd"], ["cn"]],
        )
        self.assertEqual(
            [font["artifact"] for font in catalog_v3["fonts"]],
            [font["artifact"] for font in catalog_v2["fonts"]],
        )
        output = self.root / "release-v3"
        write_release(catalog_v3, assets_v3, output, overwrite=False)
        verify_release(catalog_v3, output / "assets")
        self.assertEqual(
            (output / "release-assets.txt").read_text(encoding="utf-8"),
            "",
        )

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
        attributes = (destination / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* text=auto eol=lf", attributes)
        self.assertIn("*.woff2 binary", attributes)
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
        self.assertIn("default: ace-fonts-v4", workflow)
        self.assertIn("validate_font_audit.py", workflow)


class SharedRepositoryV4IntegrationTest(unittest.TestCase):
    RETAINED_V1_IDS = {
        "cascadia_code",
        "fira_code",
        "hack",
        "ibm_plex_mono",
        "intel_one_mono",
        "iosevka_slab",
        "jetbrains_mono",
        "source_code_pro",
    }
    ADDED_V2_IDS = {
        "anonymous_pro",
        "atkinson_hyperlegible_mono",
        "commit_mono",
        "inconsolata",
        "maple_mono",
        "maple_mono_cn",
        "maple_mono_nf",
        "maple_mono_nf_cn",
        "martian_mono",
        "monaspace_argon",
        "monaspace_argon_nf",
        "monaspace_argon_variable",
        "monaspace_krypton",
        "monaspace_krypton_nf",
        "monaspace_krypton_variable",
        "monaspace_neon",
        "monaspace_neon_nf",
        "monaspace_neon_variable",
        "monaspace_radon",
        "monaspace_radon_nf",
        "monaspace_radon_variable",
        "monaspace_xenon",
        "monaspace_xenon_nf",
        "monaspace_xenon_variable",
        "recursive",
        "red_hat_mono",
        "sarasa_term_sc_nerd",
        "ubuntu_sans_mono",
        "victor_mono",
    }
    ADDED_V4_IDS = {
        "azeret_mono",
        "departure_mono",
        "fantasque_sans_mono",
        "fragment_mono",
        "geist",
        "geist_mono",
        "geist_pixel_circle",
        "geist_pixel_grid",
        "geist_pixel_line",
        "geist_pixel_square",
        "geist_pixel_triangle",
        "go_mono",
        "julia_mono",
        "m_plus_1",
        "m_plus_1_code",
        "m_plus_2",
        "m_plus_u",
        "monoid",
        "noto_sans_mono",
        "sarasa_mono_sc_nerd",
        "sarasa_mono_slab_sc_nerd",
        "sometype_mono",
        "space_mono",
        "zero_x_proto",
    }
    REMOVED_V2_IDS = {"sarasa_term_sc_nerd"}
    NERD_IDS = {
        "maple_mono_nf",
        "maple_mono_nf_cn",
        "monaspace_argon_nf",
        "monaspace_krypton_nf",
        "monaspace_neon_nf",
        "monaspace_radon_nf",
        "monaspace_xenon_nf",
        "sarasa_mono_sc_nerd",
        "sarasa_mono_slab_sc_nerd",
    }
    VARIABLE_IDS = {
        "monaspace_argon_variable",
        "monaspace_krypton_variable",
        "monaspace_neon_variable",
        "monaspace_radon_variable",
        "monaspace_xenon_variable",
    }
    CN_IDS = {
        "maple_mono_cn",
        "maple_mono_nf_cn",
        "sarasa_mono_sc_nerd",
        "sarasa_mono_slab_sc_nerd",
    }
    JP_IDS = CN_IDS | {"m_plus_1", "m_plus_1_code", "m_plus_2", "m_plus_u"}
    OTHER_IDS = {
        "geist",
        "geist_pixel_circle",
        "geist_pixel_grid",
        "geist_pixel_line",
        "geist_pixel_square",
        "geist_pixel_triangle",
    }

    @classmethod
    def expected_features(cls, font_id: str) -> list[str]:
        all_ids = (
            cls.RETAINED_V1_IDS
            | (cls.ADDED_V2_IDS - cls.REMOVED_V2_IDS)
            | cls.ADDED_V4_IDS
        )
        mono_ids = all_ids - cls.OTHER_IDS - {"m_plus_1", "m_plus_2", "m_plus_u"}
        feature_sets = (
            ("mono", mono_ids),
            ("nerd", cls.NERD_IDS),
            ("variable", cls.VARIABLE_IDS),
            ("cn", cls.CN_IDS),
            ("jp", cls.JP_IDS),
        )
        return [feature for feature, ids in feature_sets if font_id in ids]

    def test_manifest_pins_the_complete_v4_inventory_and_source_tree(self) -> None:
        self.assertEqual(
            (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8"),
            GIT_ATTRIBUTES,
        )
        manifest = read_json(SHARED_MANIFEST)
        validate_manifest(manifest)
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["catalogVersion"], 4)
        self.assertEqual(manifest["releaseTag"], "ace-fonts-v4")
        self.assertEqual(manifest["minHostVersionCode"], 5230)
        self.assertEqual(manifest["expectedFontCount"], 60)
        self.assertEqual(len(manifest["fonts"]), 60)

        by_version: dict[int, set[str]] = {}
        expected_source_files: set[str] = set()
        for font in manifest["fonts"]:
            by_version.setdefault(font["artifactVersion"], set()).add(font["id"])
            self.assertEqual(
                font["artifactReleaseTag"],
                f"ace-fonts-v{font['artifactVersion']}",
            )
            self.assertTrue(font["fontPath"].endswith(".woff2"))
            expected_source_files.add(font["fontPath"])
            expected_source_files.update(font["noticePaths"])
            self.assertEqual(
                font["features"],
                self.expected_features(font["id"]),
            )
            self.assertIn("groupId", font)
            self.assertTrue(font["variantName"])
            self.assertGreaterEqual(font["variantOrder"], 0)
            self.assertIsInstance(font["isDefaultVariant"], bool)

        self.assertEqual(
            by_version,
            {
                1: self.RETAINED_V1_IDS,
                2: self.ADDED_V2_IDS - self.REMOVED_V2_IDS,
                4: self.ADDED_V4_IDS,
            },
        )
        self.assertNotIn("sarasa_term_sc_nerd", {font["id"] for font in manifest["fonts"]})
        groups: dict[str, list[dict]] = {}
        for font in manifest["fonts"]:
            groups.setdefault(font["groupId"], []).append(font)
        self.assertEqual(len(groups), 43)
        for variants in groups.values():
            self.assertEqual(sum(font["isDefaultVariant"] for font in variants), 1)
            default = next(font for font in variants if font["isDefaultVariant"])
            self.assertEqual(
                default["variantOrder"],
                max(font["variantOrder"] for font in variants),
            )
        geist_pixel = sorted(groups["geist_pixel"], key=lambda font: font["variantOrder"])
        self.assertEqual(
            [font["variantName"] for font in geist_pixel],
            ["Line", "Circle", "Grid", "Square", "Triangle"],
        )
        self.assertEqual(
            next(font for font in geist_pixel if font["isDefaultVariant"])["variantName"],
            "Triangle",
        )
        actual_source_files = {
            path.relative_to(SHARED_SOURCE_ROOT).as_posix()
            for path in SHARED_SOURCE_ROOT.rglob("*")
            if path.is_file()
        }
        retired_source_files = {
            "retired/sarasa-term-sc-nerd/LICENSE.txt",
            "retired/sarasa-term-sc-nerd/SarasaTermSCNerd-Regular.woff2",
        }
        self.assertEqual(
            actual_source_files,
            expected_source_files | retired_source_files,
        )
        self.assertTrue(expected_source_files.isdisjoint(retired_source_files))
        source_font_suffixes = {
            path.suffix.lower()
            for path in SHARED_SOURCE_ROOT.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".woff2", ".ttf", ".otf"}
        }
        self.assertEqual(
            source_font_suffixes,
            {".woff2"},
        )

    def test_manifest_sources_are_already_git_clean_filter_stable(self) -> None:
        """Keep locally generated release bytes identical to a clean CI checkout."""
        source_paths: set[str] = set()
        for manifest_path in (
            SHARED_MANIFEST,
            V1_HISTORY_MANIFEST,
            V2_HISTORY_MANIFEST,
            V3_HISTORY_MANIFEST,
        ):
            for font in read_json(manifest_path)["fonts"]:
                source_paths.add(font["fontPath"])
                source_paths.update(font["noticePaths"])

        mismatches: list[str] = []
        for source_path in sorted(source_paths):
            repository_path = (
                SHARED_SOURCE_ROOT / source_path
            ).relative_to(REPOSITORY_ROOT).as_posix()
            raw_hash = subprocess.run(
                [
                    "git",
                    "hash-object",
                    "--no-filters",
                    "--",
                    repository_path,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            clean_hash = subprocess.run(
                [
                    "git",
                    "hash-object",
                    "--filters",
                    f"--path={repository_path}",
                    "--",
                    repository_path,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if raw_hash != clean_hash:
                mismatches.append(source_path)

        self.assertEqual(
            mismatches,
            [],
            "manifest source worktree bytes differ from Git clean-filter bytes; "
            "normalize these files before generating a catalog",
        )

    def test_v4_font_audit_is_sha_bound_and_enforces_feature_coverage(self) -> None:
        manifest = read_json(SHARED_MANIFEST)
        audit = read_json(FONT_AUDIT_V4)
        validate_font_audit(manifest, audit, SHARED_SOURCE_ROOT)
        self.assertEqual(audit["catalogVersion"], 4)
        self.assertEqual(audit["criteria"], EXPECTED_CRITERIA)
        self.assertEqual(len(audit["fonts"]), 60)

        evidence_by_id = {font["id"]: font for font in audit["fonts"]}
        for font_id in self.CN_IDS:
            evidence = evidence_by_id[font_id]
            self.assertGreaterEqual(evidence["cjkUnifiedCount"], 6000)
            self.assertEqual(evidence["cnProbeCoverage"], 7)
        for font_id in self.JP_IDS:
            evidence = evidence_by_id[font_id]
            self.assertGreaterEqual(evidence["cjkUnifiedCount"], 2000)
            self.assertGreaterEqual(evidence["hiraganaCount"], 80)
            self.assertGreaterEqual(evidence["katakanaCount"], 80)
            self.assertEqual(evidence["jpProbeCoverage"], 5)

        self.assertEqual(
            evidence_by_id["monaspace_krypton_nf"]["typographicFamilyNames"],
            ["Monaspace Krypton NF"],
        )
        self.assertEqual(
            evidence_by_id["monaspace_neon_nf"]["typographicFamilyNames"],
            ["Monaspace Neon NF"],
        )
        self.assertNotEqual(
            evidence_by_id["monaspace_krypton_nf"]["legacyFamilyNames"],
            evidence_by_id["monaspace_krypton_nf"]["typographicFamilyNames"],
        )
        self.assertNotEqual(
            evidence_by_id["monaspace_neon_nf"]["legacyFamilyNames"],
            evidence_by_id["monaspace_neon_nf"]["typographicFamilyNames"],
        )

        tampered = copy.deepcopy(audit)
        next(
            font for font in tampered["fonts"] if font["id"] == "maple_mono_cn"
        )["cnProbeCoverage"] = 6
        with self.assertRaisesRegex(DistributionError, "every cn probe"):
            validate_font_audit(manifest, tampered, SHARED_SOURCE_ROOT)

    @unittest.skipUnless(
        importlib.util.find_spec("fontTools") is not None,
        "optional fontTools audit dependency is not installed",
    )
    def test_fonttools_auditor_reproduces_the_reviewed_report(self) -> None:
        from audit_font_metadata import build_font_audit

        generated = build_font_audit(read_json(SHARED_MANIFEST), SHARED_SOURCE_ROOT)
        self.assertEqual(FONT_AUDIT_V4.read_bytes(), canonical_json_bytes(generated))

    def test_v1_history_is_canonical_signed_and_byte_pinned(self) -> None:
        catalog_bytes = V1_HISTORY_CATALOG.read_bytes()
        signature_bytes = V1_HISTORY_SIGNATURE.read_bytes()
        self.assertEqual(
            hashlib.sha256(catalog_bytes).hexdigest(),
            "e7840a817447aa7745a48828cb5b8a7debd279fd5df1d05fbec33f679b152440",
        )
        self.assertEqual(
            hashlib.sha256(signature_bytes).hexdigest(),
            "51ddc6b0982ead4afbfe43d57450cffe1422561ed35cd205590119ef00c12fc3",
        )
        history = read_json(V1_HISTORY_CATALOG)
        validate_catalog(history)
        self.assertEqual(catalog_bytes, canonical_json_bytes(history))
        self.assertEqual(history["schemaVersion"], 1)
        self.assertEqual(history["catalogVersion"], 1)
        self.assertEqual(history["releaseTag"], "ace-fonts-v1")
        self.assertEqual(history["repository"], SHARED_REPOSITORY)
        self.assertEqual(
            {font["id"] for font in history["fonts"]},
            self.RETAINED_V1_IDS,
        )
        self.assertEqual(
            {font["artifact"]["version"] for font in history["fonts"]},
            {1},
        )

        try:
            openssl = find_openssl()
        except DistributionError as error:
            self.skipTest(str(error))
        verify_catalog_signature(
            V1_HISTORY_CATALOG,
            V1_HISTORY_SIGNATURE,
            TOOL_DIR / "catalog-v1-signing-public.pem",
            CATALOG_KEY_ID,
            openssl_value=openssl,
        )

    def test_frozen_v1_manifest_reproduces_the_signed_catalog(self) -> None:
        manifest = read_json(V1_HISTORY_MANIFEST)
        validate_manifest(manifest)
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["catalogVersion"], 1)
        self.assertEqual(manifest["releaseTag"], "ace-fonts-v1")
        self.assertEqual(manifest["expectedFontCount"], 8)
        self.assertTrue(all("features" not in font for font in manifest["fonts"]))

        catalog, assets = build_catalog(
            manifest,
            SHARED_SOURCE_ROOT,
            SHARED_REPOSITORY,
        )
        self.assertEqual(
            V1_HISTORY_CATALOG.read_bytes(),
            canonical_json_bytes(catalog),
        )
        self.assertEqual(len(assets), 17)
        self.assertTrue(all("features" not in font for font in catalog["fonts"]))

    def test_v2_history_is_canonical_signed_and_byte_pinned(self) -> None:
        catalog_bytes = V2_HISTORY_CATALOG.read_bytes()
        signature_bytes = V2_HISTORY_SIGNATURE.read_bytes()
        self.assertEqual(
            hashlib.sha256(catalog_bytes).hexdigest(),
            "f93f31e8d2f56af04a8b86650df3094b03f177b1c15611eae4e988ee047f7204",
        )
        self.assertEqual(
            hashlib.sha256(signature_bytes).hexdigest(),
            "7927aa2c2a2b1e52af3bbb16d316cf21d8d6639abb888acf43efb3ae64a313f2",
        )
        history = read_json(V2_HISTORY_CATALOG)
        validate_catalog(history)
        self.assertEqual(catalog_bytes, canonical_json_bytes(history))
        self.assertEqual(history["schemaVersion"], 1)
        self.assertEqual(history["catalogVersion"], 2)
        self.assertEqual(history["releaseTag"], "ace-fonts-v2")
        self.assertEqual(history["repository"], SHARED_REPOSITORY)
        self.assertEqual(len(history["fonts"]), 37)
        self.assertTrue(all("features" not in font for font in history["fonts"]))
        self.assertEqual(
            {font["artifact"]["version"] for font in history["fonts"]},
            {1, 2},
        )

        try:
            openssl = find_openssl()
        except DistributionError as error:
            self.skipTest(str(error))
        verify_catalog_signature(
            V2_HISTORY_CATALOG,
            V2_HISTORY_SIGNATURE,
            TOOL_DIR / "catalog-v1-signing-public.pem",
            CATALOG_KEY_ID,
            openssl_value=openssl,
        )

    def test_v2_recovery_manifest_reproduces_the_signed_catalog(self) -> None:
        manifest_bytes = V2_HISTORY_MANIFEST.read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            "ed4f7b261ee42c9736712b907d3af8adf2dd022affef4f45ae00c38ffa0659e8",
        )
        manifest = read_json(V2_HISTORY_MANIFEST)
        validate_manifest(manifest)
        catalog, assets = build_catalog(
            manifest,
            SHARED_SOURCE_ROOT,
            SHARED_REPOSITORY,
            read_json(V1_HISTORY_CATALOG),
        )
        self.assertEqual(V2_HISTORY_CATALOG.read_bytes(), canonical_json_bytes(catalog))
        self.assertEqual(len(assets), 59)

    def test_v3_history_is_canonical_signed_and_byte_pinned(self) -> None:
        catalog_bytes = V3_HISTORY_CATALOG.read_bytes()
        signature_bytes = V3_HISTORY_SIGNATURE.read_bytes()
        manifest_bytes = V3_HISTORY_MANIFEST.read_bytes()
        self.assertEqual(
            hashlib.sha256(catalog_bytes).hexdigest(),
            "66b9a95a86b94a638dedbd9ef515b9a6d9a10b2d2f6bd7ecfcbea5367a99d469",
        )
        self.assertEqual(
            hashlib.sha256(signature_bytes).hexdigest(),
            "d9df550dab55ec57bba38648b8571fbe7c00f1e553e235fc00b62bcde7047507",
        )
        self.assertEqual(
            hashlib.sha256(manifest_bytes).hexdigest(),
            "0ff8c58999095b69626a02fa7e36d3cceae1264dd967385f29ed0aa2892f089d",
        )
        history = read_json(V3_HISTORY_CATALOG)
        validate_catalog(history, minimum_catalog_version=3)
        self.assertEqual(catalog_bytes, canonical_json_bytes(history))
        self.assertEqual(history["catalogVersion"], 3)
        self.assertEqual(history["releaseTag"], "ace-fonts-v3")
        self.assertEqual(len(history["fonts"]), 37)

        try:
            openssl = find_openssl()
        except DistributionError as error:
            self.skipTest(str(error))
        verify_catalog_signature(
            V3_HISTORY_CATALOG,
            V3_HISTORY_SIGNATURE,
            TOOL_DIR / "catalog-v1-signing-public.pem",
            CATALOG_KEY_ID,
            openssl_value=openssl,
        )

    def test_v3_recovery_manifest_reproduces_the_signed_catalog(self) -> None:
        manifest = read_json(V3_HISTORY_MANIFEST)
        validate_manifest(manifest)
        catalog, assets = build_catalog(
            manifest,
            SHARED_SOURCE_ROOT,
            SHARED_REPOSITORY,
            read_json(V2_HISTORY_CATALOG),
        )
        self.assertEqual(V3_HISTORY_CATALOG.read_bytes(), canonical_json_bytes(catalog))
        self.assertEqual(assets, {})

    def test_published_catalog_is_in_a_valid_v4_transition_state(self) -> None:
        current_bytes = SHARED_CATALOG.read_bytes()
        if current_bytes == V3_HISTORY_CATALOG.read_bytes():
            self.assertEqual(
                SHARED_SIGNATURE.read_bytes(),
                V3_HISTORY_SIGNATURE.read_bytes(),
            )
        else:
            self.assertEqual(current_bytes, PENDING_V4_CATALOG.read_bytes())
            current = read_json(SHARED_CATALOG)
            self.assertEqual(current["catalogVersion"], 4)
            self.assertEqual(current["releaseTag"], "ace-fonts-v4")

    def test_sources_reproduce_the_pending_v4_catalog_and_assets(self) -> None:
        manifest = read_json(SHARED_MANIFEST)
        history = read_json(V3_HISTORY_CATALOG)
        catalog, assets = build_catalog(
            manifest,
            SHARED_SOURCE_ROOT,
            SHARED_REPOSITORY,
            history,
        )
        self.assertEqual(PENDING_V4_CATALOG.read_bytes(), canonical_json_bytes(catalog))
        self.assertEqual(catalog["catalogVersion"], 4)
        self.assertEqual(catalog["minHostVersionCode"], 5230)
        self.assertEqual(len(catalog["fonts"]), 60)
        self.assertEqual(len({font["groupId"] for font in catalog["fonts"]}), 43)
        self.assertEqual(len(assets), 50)
        self.assertEqual(sum(name.endswith(".woff2") for name in assets), 24)
        history_by_id = {font["id"]: font for font in history["fonts"]}
        for font in catalog["fonts"]:
            if font["artifact"]["version"] < 4:
                previous = history_by_id[font["id"]]
                self.assertEqual(font["artifact"], previous["artifact"])
                self.assertEqual(font["license"]["files"], previous["license"]["files"])
        self.assertNotIn("sarasa_term_sc_nerd", {font["id"] for font in catalog["fonts"]})

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release-v4"
            write_release(catalog, assets, output, overwrite=False)
            verify_release(catalog, output / "assets")
            self.assertEqual(
                len(
                    (output / "release-assets.txt")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
                50,
            )

    def test_current_catalog_signature_is_valid(self) -> None:
        try:
            openssl = find_openssl()
        except DistributionError as error:
            self.skipTest(str(error))
        envelope = verify_catalog_signature(
            SHARED_CATALOG,
            SHARED_SIGNATURE,
            TOOL_DIR / "catalog-v1-signing-public.pem",
            CATALOG_KEY_ID,
            openssl_value=openssl,
        )
        self.assertEqual(envelope["catalog"], SHARED_CATALOG.name)


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
        self.assertEqual(
            (TOOL_DIR / "catalog-v1.schema.json").read_bytes(),
            (REPOSITORY_ROOT / "ace-fonts/schemas/catalog-v1.schema.json").read_bytes(),
        )
        schema = json.loads((TOOL_DIR / "catalog-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertIn("AutoJs6-Shared-Assets", schema["$id"])
        self.assertEqual(
            schema["properties"]["releaseTag"]["pattern"],
            "^ace-fonts-v[1-9][0-9]*$",
        )
        features = schema["$defs"]["font"]["properties"]["features"]
        self.assertEqual(
            features["items"]["enum"],
            ["mono", "nerd", "variable", "cn", "jp"],
        )
        self.assertTrue(features["uniqueItems"])
        self.assertNotIn("features", schema["$defs"]["font"]["required"])
        variant_properties = schema["$defs"]["font"]["properties"]
        for key in ("groupId", "variantName", "variantOrder", "isDefaultVariant"):
            self.assertIn(key, variant_properties)
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
