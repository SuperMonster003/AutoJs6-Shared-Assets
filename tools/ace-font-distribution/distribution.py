#!/usr/bin/env python3
"""Build and validate the reproducible AutoJs6 Ace font release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


DEFAULT_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
DEFAULT_MANIFEST = Path(__file__).with_name("font-sources.json")
OUTPUT_MARKER = ".ace-font-distribution-output"
RESERVED_FONT_IDS = frozenset({"system_monospace", "iosevka"})
FONT_FEATURE_VALUES = ("mono", "nerd", "variable", "cn", "jp")
FONT_FEATURE_SET = frozenset(FONT_FEATURE_VALUES)
FONT_VARIANT_FIELDS = (
    "groupId",
    "variantName",
    "variantOrder",
    "isDefaultVariant",
)
FONT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RELEASE_TAG_PATTERN = re.compile(r"^ace-fonts-v([1-9][0-9]*)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_FONT_FIELDS = frozenset(
    {
        "id",
        "displayName",
        "family",
        "order",
        "author",
        "licenseName",
        "licenseSpdx",
        "sourceRepository",
        "upstreamVersion",
        "artifactVersion",
        "artifactReleaseTag",
        "fontPath",
        "noticePaths",
    }
)


class DistributionError(ValueError):
    """A safe, user-facing distribution validation error."""


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DistributionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DistributionError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise DistributionError(f"JSON root must be an object: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_woff2(content: bytes, source: str = "font") -> None:
    """Validate the fixed WOFF2 header and all directly checkable ranges."""
    if len(content) < 48:
        raise DistributionError(f"{source}: WOFF2 file is shorter than its 48-byte header")
    (
        signature,
        _flavor,
        declared_length,
        num_tables,
        reserved,
        total_sfnt_size,
        total_compressed_size,
        _major_version,
        _minor_version,
        meta_offset,
        meta_length,
        meta_orig_length,
        private_offset,
        private_length,
    ) = struct.unpack(">4sIIHHIIHHIIIII", content[:48])
    if signature != b"wOF2":
        raise DistributionError(f"{source}: invalid WOFF2 signature")
    if declared_length != len(content):
        raise DistributionError(
            f"{source}: header length {declared_length} does not match {len(content)} bytes"
        )
    if num_tables == 0:
        raise DistributionError(f"{source}: WOFF2 contains no font tables")
    if reserved != 0:
        raise DistributionError(f"{source}: reserved WOFF2 header field must be zero")
    if total_sfnt_size == 0 or total_compressed_size == 0:
        raise DistributionError(f"{source}: invalid zero WOFF2 size field")
    if total_compressed_size > len(content) - 48:
        raise DistributionError(f"{source}: compressed data cannot fit inside the file")

    metadata = (meta_offset, meta_length, meta_orig_length)
    if any(metadata):
        if not all(metadata):
            raise DistributionError(f"{source}: incomplete WOFF2 metadata range")
        if meta_offset < 48 or meta_offset + meta_length > len(content):
            raise DistributionError(f"{source}: WOFF2 metadata range is outside the file")
    if bool(private_offset) != bool(private_length):
        raise DistributionError(f"{source}: incomplete WOFF2 private-data range")
    if private_offset and (
        private_offset < 48 or private_offset + private_length > len(content)
    ):
        raise DistributionError(f"{source}: WOFF2 private-data range is outside the file")


def _require_nonempty_string(container: dict[str, Any], key: str, context: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DistributionError(f"{context}.{key} must be a non-empty string")
    return value


def _validate_font_features(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise DistributionError(f"{context}.features must be an array")
    if any(
        not isinstance(feature, str) or feature not in FONT_FEATURE_SET
        for feature in value
    ):
        allowed = ", ".join(FONT_FEATURE_VALUES)
        raise DistributionError(f"{context}.features values must be one of: {allowed}")
    if len(value) != len(set(value)):
        raise DistributionError(f"{context}.features must not contain duplicates")
    canonical = [feature for feature in FONT_FEATURE_VALUES if feature in value]
    if value != canonical:
        raise DistributionError(
            f"{context}.features must use canonical order: "
            + ", ".join(FONT_FEATURE_VALUES)
        )
    return value


def _validate_variant_metadata(
    font: dict[str, Any], context: str, *, required: bool
) -> None:
    present = [key in font for key in FONT_VARIANT_FIELDS]
    if required and not all(present):
        missing = [
            key for key, is_present in zip(FONT_VARIANT_FIELDS, present) if not is_present
        ]
        raise DistributionError(
            f"{context} is missing variant metadata: {', '.join(missing)}"
        )
    if any(present) and not all(present):
        raise DistributionError(
            f"{context} must declare all variant metadata fields together"
        )
    if not any(present):
        return

    group_id = _require_nonempty_string(font, "groupId", context)
    if not FONT_ID_PATTERN.fullmatch(group_id) or group_id in RESERVED_FONT_IDS:
        raise DistributionError(f"{context}.groupId is invalid or reserved: {group_id}")
    _require_nonempty_string(font, "variantName", context)
    variant_order = font.get("variantOrder")
    if (
        not isinstance(variant_order, int)
        or isinstance(variant_order, bool)
        or variant_order < 0
    ):
        raise DistributionError(f"{context}.variantOrder must be a non-negative integer")
    if not isinstance(font.get("isDefaultVariant"), bool):
        raise DistributionError(f"{context}.isDefaultVariant must be a boolean")


def _validate_variant_groups(
    fonts: list[dict[str, Any]], context: str, *, required: bool
) -> None:
    if not required and not any("groupId" in font for font in fonts):
        return

    groups: dict[str, list[dict[str, Any]]] = {}
    for index, font in enumerate(fonts):
        item_context = f"{context}[{index}]"
        _validate_variant_metadata(font, item_context, required=required)
        if "groupId" in font:
            groups.setdefault(font["groupId"], []).append(font)

    for group_id, variants in groups.items():
        display_names = {font["displayName"] for font in variants}
        if len(display_names) != 1:
            raise DistributionError(
                f"{context} group {group_id} must use one displayName"
            )
        variant_names = [font["variantName"].casefold() for font in variants]
        if len(variant_names) != len(set(variant_names)):
            raise DistributionError(
                f"{context} group {group_id} has duplicate variantName values"
            )
        variant_orders = [font["variantOrder"] for font in variants]
        if len(variant_orders) != len(set(variant_orders)):
            raise DistributionError(
                f"{context} group {group_id} has duplicate variantOrder values"
            )
        defaults = [font for font in variants if font["isDefaultVariant"]]
        if len(defaults) != 1:
            raise DistributionError(
                f"{context} group {group_id} must have exactly one default variant"
            )
        if defaults[0]["variantOrder"] != max(variant_orders):
            raise DistributionError(
                f"{context} group {group_id} default must have the highest variantOrder"
            )
        ordered_variants = sorted(variants, key=lambda font: font["variantOrder"])
        orders = [font["order"] for font in ordered_variants]
        if orders != sorted(orders):
            raise DistributionError(
                f"{context} group {group_id} order must follow variantOrder"
            )


def validate_manifest(manifest: dict[str, Any]) -> None:
    for key in ("schemaVersion", "catalogVersion", "minHostVersionCode"):
        value = manifest.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise DistributionError(f"manifest.{key} must be a positive integer")
    if manifest["schemaVersion"] != 1:
        raise DistributionError("only manifest schemaVersion 1 is supported")
    release_tag = _require_nonempty_string(manifest, "releaseTag", "manifest")
    match = RELEASE_TAG_PATTERN.fullmatch(release_tag)
    if not match:
        raise DistributionError("manifest.releaseTag must look like ace-fonts-v1")
    release_version = int(match.group(1))
    if release_version != manifest["catalogVersion"]:
        raise DistributionError("releaseTag version must equal catalogVersion")

    fonts = manifest.get("fonts")
    if not isinstance(fonts, list) or not fonts:
        raise DistributionError("manifest.fonts must be a non-empty array")
    expected_count = manifest.get("expectedFontCount")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool):
        raise DistributionError("manifest.expectedFontCount must be an integer")
    if len(fonts) != expected_count:
        raise DistributionError(
            f"manifest expected {expected_count} fonts, but contains {len(fonts)}"
        )

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for index, font in enumerate(fonts):
        context = f"manifest.fonts[{index}]"
        if not isinstance(font, dict):
            raise DistributionError(f"{context} must be an object")
        missing = REQUIRED_FONT_FIELDS.difference(font)
        if missing:
            raise DistributionError(f"{context} is missing: {', '.join(sorted(missing))}")
        font_id = _require_nonempty_string(font, "id", context)
        if not FONT_ID_PATTERN.fullmatch(font_id):
            raise DistributionError(f"{context}.id is not a stable lower_snake_case ID")
        if font_id in RESERVED_FONT_IDS:
            raise DistributionError(f"{context}.id conflicts with bundled/reserved ID {font_id}")
        if font_id in seen_ids:
            raise DistributionError(f"duplicate font ID: {font_id}")
        seen_ids.add(font_id)

        for key in (
            "displayName",
            "family",
            "author",
            "licenseName",
            "licenseSpdx",
            "sourceRepository",
            "fontPath",
        ):
            _require_nonempty_string(font, key, context)
        if "features" in font:
            _validate_font_features(font["features"], context)
        elif manifest["catalogVersion"] >= 3:
            raise DistributionError(
                f"{context}.features is required from catalogVersion 3"
            )
        if not font["sourceRepository"].startswith("https://github.com/"):
            raise DistributionError(f"{context}.sourceRepository must be an HTTPS GitHub URL")
        upstream_version = font["upstreamVersion"]
        if upstream_version is not None and (
            not isinstance(upstream_version, str) or not upstream_version.strip()
        ):
            raise DistributionError(f"{context}.upstreamVersion must be null or non-empty")
        artifact_version = font.get("artifactVersion")
        if (
            not isinstance(artifact_version, int)
            or isinstance(artifact_version, bool)
            or artifact_version < 1
        ):
            raise DistributionError(f"{context}.artifactVersion must be a positive integer")
        artifact_release_tag = _require_nonempty_string(
            font, "artifactReleaseTag", context
        )
        artifact_match = RELEASE_TAG_PATTERN.fullmatch(artifact_release_tag)
        if not artifact_match:
            raise DistributionError(
                f"{context}.artifactReleaseTag must look like ace-fonts-v1"
            )
        if int(artifact_match.group(1)) != artifact_version:
            raise DistributionError(
                f"{context}.artifactReleaseTag must match artifactVersion"
            )
        if artifact_version > manifest["catalogVersion"]:
            raise DistributionError(
                f"{context}.artifactVersion cannot exceed catalogVersion"
            )
        commit = font.get("autoJs6SourceCommit")
        if commit is not None and (
            not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit)
        ):
            raise DistributionError(
                f"{context}.autoJs6SourceCommit must be null, absent, or a full Git SHA"
            )
        order = font["order"]
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise DistributionError(f"{context}.order must be a non-negative integer")
        if order in seen_orders:
            raise DistributionError(f"duplicate font order: {order}")
        seen_orders.add(order)
        notices = font["noticePaths"]
        if not isinstance(notices, list) or not notices:
            raise DistributionError(f"{context}.noticePaths must be a non-empty array")
        if any(not isinstance(item, str) or not item.strip() for item in notices):
            raise DistributionError(f"{context}.noticePaths contains an invalid path")

    _validate_variant_groups(
        fonts,
        "manifest.fonts",
        required=manifest["catalogVersion"] >= 4,
    )


def _source_file(source_root: Path, relative: str, context: str) -> Path:
    candidate = (source_root / relative).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as error:
        raise DistributionError(f"{context} escapes --source-root: {relative}") from error
    if not candidate.is_file():
        raise DistributionError(f"{context} does not exist: {candidate}")
    return candidate


def _release_url(repository: str, release_tag: str, file_name: str) -> str:
    return (
        f"https://github.com/{repository}/releases/download/"
        f"{quote(release_tag, safe='')}/{quote(file_name, safe='')}"
    )


def _notice_asset_name(font_id: str, artifact_version: int, source_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", source_name)
    return f"autojs6-ace-font-{font_id}-v{artifact_version}-{safe_name}"


def _prepare_fonts(
    manifest: dict[str, Any], source_root: Path, repository: str
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    current_release_tag = manifest["releaseTag"]
    assets: dict[str, bytes] = {}
    catalog_fonts: list[dict[str, Any]] = []

    for source in sorted(manifest["fonts"], key=lambda item: item["order"]):
        font_id = source["id"]
        font_path = _source_file(source_root, source["fontPath"], f"{font_id}.fontPath")
        font_content = font_path.read_bytes()
        validate_woff2(font_content, source["fontPath"])
        font_sha = sha256_bytes(font_content)
        artifact_version = source["artifactVersion"]
        artifact_release_tag = source["artifactReleaseTag"]
        font_asset = (
            f"autojs6-ace-font-{font_id}-v{artifact_version}-{font_sha[:8]}.woff2"
        )
        if artifact_release_tag == current_release_tag:
            if font_asset in assets:
                raise DistributionError(f"duplicate release asset name: {font_asset}")
            assets[font_asset] = font_content
        font_url = _release_url(repository, artifact_release_tag, font_asset)

        license_files: list[dict[str, Any]] = []
        seen_notice_names: set[str] = set()
        for notice_path_value in source["noticePaths"]:
            notice_path = _source_file(
                source_root, notice_path_value, f"{font_id}.noticePaths"
            )
            notice_asset = _notice_asset_name(
                font_id, artifact_version, notice_path.name
            )
            if notice_asset in seen_notice_names:
                raise DistributionError(f"duplicate release asset name: {notice_asset}")
            seen_notice_names.add(notice_asset)
            notice_content = notice_path.read_bytes()
            if not notice_content:
                raise DistributionError(f"empty notice file: {notice_path_value}")
            if artifact_release_tag == current_release_tag:
                if notice_asset in assets:
                    raise DistributionError(f"duplicate release asset name: {notice_asset}")
                assets[notice_asset] = notice_content
            license_files.append(
                {
                    "fileName": notice_asset,
                    "originalName": notice_path.name,
                    "sha256": sha256_bytes(notice_content),
                    "size": len(notice_content),
                    "url": _release_url(
                        repository, artifact_release_tag, notice_asset
                    ),
                }
            )

        catalog_font: dict[str, Any] = {
            "artifact": {
                "fileName": font_asset,
                "format": "woff2",
                "mimeType": "font/woff2",
                "sha256": font_sha,
                "size": len(font_content),
                "style": "normal",
                "url": font_url,
                "urls": [font_url],
                "version": artifact_version,
                "weight": 400,
            },
            "author": source["author"],
            "displayName": source["displayName"],
            "family": source["family"],
            "id": font_id,
            "license": {
                "files": license_files,
                "name": source["licenseName"],
                "spdx": source["licenseSpdx"],
            },
            "order": source["order"],
            "source": _catalog_source(source, manifest),
        }
        if "features" in source:
            catalog_font["features"] = source["features"]
        for key in FONT_VARIANT_FIELDS:
            if key in source:
                catalog_font[key] = source[key]
        catalog_fonts.append(catalog_font)
    return catalog_fonts, assets


def _catalog_source(
    source: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "repository": source["sourceRepository"],
        "upstreamVersion": source["upstreamVersion"],
    }
    commit = source.get("autoJs6SourceCommit")
    if commit is not None:
        value["autoJs6Snapshot"] = {
            "commit": commit,
            "path": (
                "app/src/main/assets/editor/ace-builds-1.4.12/fonts/"
                + source["fontPath"]
            ),
            "versionCode": manifest["minHostVersionCode"],
        }
    return value


def build_catalog(
    manifest: dict[str, Any],
    source_root: Path,
    repository: str,
    previous_catalog: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    validate_manifest(manifest)
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise DistributionError("--repository must be an owner/name GitHub repository slug")
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise DistributionError(f"--source-root is not a directory: {source_root}")
    fonts, assets = _prepare_fonts(manifest, source_root, repository)
    catalog = {
        "catalogVersion": manifest["catalogVersion"],
        "fonts": fonts,
        "minHostVersionCode": manifest["minHostVersionCode"],
        "releaseTag": manifest["releaseTag"],
        "repository": repository,
        "schemaVersion": manifest["schemaVersion"],
    }
    validate_catalog(catalog)
    validate_carried_forward_artifacts(catalog, previous_catalog)
    return catalog, assets


def validate_carried_forward_artifacts(
    catalog: dict[str, Any], previous_catalog: dict[str, Any] | None
) -> None:
    carried = [
        font
        for font in catalog["fonts"]
        if font["artifact"]["version"] < catalog["catalogVersion"]
    ]
    if not carried:
        return
    if previous_catalog is None:
        raise DistributionError(
            "a previous catalog is required when carrying assets from an older release"
        )
    validate_catalog(previous_catalog)
    expected_previous_version = catalog["catalogVersion"] - 1
    if previous_catalog["catalogVersion"] != expected_previous_version:
        raise DistributionError(
            "previous catalog version must be exactly "
            f"{expected_previous_version}"
        )
    if previous_catalog["repository"] != catalog["repository"]:
        raise DistributionError("previous catalog repository does not match")
    previous_by_id = {font["id"]: font for font in previous_catalog["fonts"]}
    for font in carried:
        context = f"catalog font {font['id']}"
        previous = previous_by_id.get(font["id"])
        if previous is None:
            raise DistributionError(
                f"{context} uses an old release but is absent from the previous catalog"
            )
        if font["artifact"] != previous["artifact"]:
            raise DistributionError(
                f"{context} changed artifact bytes or metadata without a new artifact release"
            )
        if font["license"]["files"] != previous["license"]["files"]:
            raise DistributionError(
                f"{context} changed notice assets without a new artifact release"
            )


def validate_catalog(catalog: dict[str, Any], minimum_catalog_version: int = 1) -> None:
    for key in ("schemaVersion", "catalogVersion", "minHostVersionCode"):
        value = catalog.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise DistributionError(f"catalog.{key} must be a positive integer")
    if catalog["schemaVersion"] != 1:
        raise DistributionError("unsupported catalog schemaVersion")
    if catalog["catalogVersion"] < minimum_catalog_version:
        raise DistributionError(
            f"catalogVersion {catalog['catalogVersion']} is below required {minimum_catalog_version}"
        )
    release_tag = _require_nonempty_string(catalog, "releaseTag", "catalog")
    match = RELEASE_TAG_PATTERN.fullmatch(release_tag)
    if not match or int(match.group(1)) != catalog["catalogVersion"]:
        raise DistributionError("catalog releaseTag must match catalogVersion")
    repository = _require_nonempty_string(catalog, "repository", "catalog")
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise DistributionError("catalog.repository must be owner/name")
    fonts = catalog.get("fonts")
    if not isinstance(fonts, list) or not fonts:
        raise DistributionError("catalog.fonts must be a non-empty array")

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    seen_assets: set[str] = set()
    for index, font in enumerate(fonts):
        context = f"catalog.fonts[{index}]"
        if not isinstance(font, dict):
            raise DistributionError(f"{context} must be an object")
        font_id = _require_nonempty_string(font, "id", context)
        if not FONT_ID_PATTERN.fullmatch(font_id) or font_id in RESERVED_FONT_IDS:
            raise DistributionError(f"{context}.id is invalid or reserved: {font_id}")
        if font_id in seen_ids:
            raise DistributionError(f"duplicate catalog font ID: {font_id}")
        seen_ids.add(font_id)
        for key in ("displayName", "family", "author"):
            _require_nonempty_string(font, key, context)
        features = font.get("features", [])
        _validate_font_features(features, context)
        if catalog["catalogVersion"] >= 3 and "features" not in font:
            raise DistributionError(f"{context}.features is required from catalogVersion 3")
        order = font.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise DistributionError(f"{context}.order must be a non-negative integer")
        if order in seen_orders:
            raise DistributionError(f"duplicate catalog font order: {order}")
        seen_orders.add(order)

        artifact = font.get("artifact")
        if not isinstance(artifact, dict):
            raise DistributionError(f"{context}.artifact must be an object")
        sha = _require_nonempty_string(artifact, "sha256", f"{context}.artifact")
        if not SHA256_PATTERN.fullmatch(sha):
            raise DistributionError(f"{context}.artifact.sha256 is invalid")
        version = artifact.get("version")
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version < 1
            or version > catalog["catalogVersion"]
        ):
            raise DistributionError(
                f"{context}.artifact.version must be between 1 and catalogVersion"
            )
        size = artifact.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            raise DistributionError(f"{context}.artifact.size must be positive")
        if artifact.get("format") != "woff2" or artifact.get("mimeType") != "font/woff2":
            raise DistributionError(f"{context}.artifact has unsupported format or MIME type")
        if artifact.get("style") != "normal" or artifact.get("weight") != 400:
            raise DistributionError(f"{context}.artifact must be Normal 400 in schema v1")
        file_name = _require_nonempty_string(
            artifact, "fileName", f"{context}.artifact"
        )
        expected_name = f"autojs6-ace-font-{font_id}-v{version}-{sha[:8]}.woff2"
        if file_name != expected_name:
            raise DistributionError(
                f"{context}.artifact.fileName must be {expected_name}"
            )
        if file_name in seen_assets:
            raise DistributionError(f"duplicate catalog asset: {file_name}")
        seen_assets.add(file_name)
        artifact_release_tag = f"ace-fonts-v{version}"
        expected_url = _release_url(repository, artifact_release_tag, file_name)
        if artifact.get("url") != expected_url or artifact.get("urls") != [expected_url]:
            raise DistributionError(f"{context}.artifact URL is not the immutable release URL")

        license_value = font.get("license")
        if not isinstance(license_value, dict):
            raise DistributionError(f"{context}.license must be an object")
        _require_nonempty_string(license_value, "name", f"{context}.license")
        _require_nonempty_string(license_value, "spdx", f"{context}.license")
        license_files = license_value.get("files")
        if not isinstance(license_files, list) or not license_files:
            raise DistributionError(f"{context}.license.files must be non-empty")
        for notice_index, notice in enumerate(license_files):
            notice_context = f"{context}.license.files[{notice_index}]"
            if not isinstance(notice, dict):
                raise DistributionError(f"{notice_context} must be an object")
            notice_name = _require_nonempty_string(notice, "fileName", notice_context)
            original_name = _require_nonempty_string(
                notice, "originalName", notice_context
            )
            expected_notice_name = _notice_asset_name(
                font_id, version, original_name
            )
            if notice_name != expected_notice_name:
                raise DistributionError(
                    f"{notice_context}.fileName must be {expected_notice_name}"
                )
            notice_sha = _require_nonempty_string(notice, "sha256", notice_context)
            if not SHA256_PATTERN.fullmatch(notice_sha):
                raise DistributionError(f"{notice_context}.sha256 is invalid")
            notice_size = notice.get("size")
            if not isinstance(notice_size, int) or isinstance(notice_size, bool) or notice_size < 1:
                raise DistributionError(f"{notice_context}.size must be positive")
            if notice_name in seen_assets:
                raise DistributionError(f"duplicate catalog asset: {notice_name}")
            seen_assets.add(notice_name)
            if notice.get("url") != _release_url(
                repository, artifact_release_tag, notice_name
            ):
                raise DistributionError(f"{notice_context}.url is not immutable")

        source = font.get("source")
        if not isinstance(source, dict):
            raise DistributionError(f"{context}.source must be an object")
        source_repository = _require_nonempty_string(source, "repository", f"{context}.source")
        if not source_repository.startswith("https://github.com/"):
            raise DistributionError(f"{context}.source.repository must be an HTTPS GitHub URL")
        snapshot = source.get("autoJs6Snapshot")
        if snapshot is not None:
            if not isinstance(snapshot, dict):
                raise DistributionError(
                    f"{context}.source.autoJs6Snapshot must be an object"
                )
            commit = _require_nonempty_string(
                snapshot, "commit", f"{context}.source.autoJs6Snapshot"
            )
            if not COMMIT_PATTERN.fullmatch(commit):
                raise DistributionError(
                    f"{context}.source.autoJs6Snapshot.commit is invalid"
                )
            _require_nonempty_string(
                snapshot, "path", f"{context}.source.autoJs6Snapshot"
            )
            if snapshot.get("versionCode") != catalog["minHostVersionCode"]:
                raise DistributionError(
                    f"{context}.source snapshot versionCode is inconsistent"
                )

    _validate_variant_groups(
        fonts,
        "catalog.fonts",
        required=catalog["catalogVersion"] >= 4,
    )


def write_release(
    catalog: dict[str, Any], assets: dict[str, bytes], output: Path, overwrite: bool
) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        marker = output / OUTPUT_MARKER
        if not overwrite:
            raise DistributionError(f"output already exists (use --overwrite): {output}")
        if not output.is_dir() or not marker.is_file():
            raise DistributionError(
                f"refusing to replace output without {OUTPUT_MARKER}: {output}"
            )

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (staging / OUTPUT_MARKER).write_text(
            "Generated by tools/ace-font-distribution/distribution.py.\n",
            encoding="utf-8",
        )
        assets_dir = staging / "assets"
        assets_dir.mkdir()
        for file_name, content in sorted(assets.items()):
            (assets_dir / file_name).write_bytes(content)
        catalog_bytes = canonical_json_bytes(catalog)
        (staging / "catalog-v1.json").write_bytes(catalog_bytes)
        # The bootstrap file is byte-for-byte identical so the Android project can
        # embed it as its last-known-good/offline catalog without another transform.
        (staging / "bootstrap-catalog-v1.json").write_bytes(catalog_bytes)
        asset_names = "\n".join(sorted(assets))
        (staging / "release-assets.txt").write_text(
            asset_names + ("\n" if asset_names else ""),
            encoding="utf-8",
            newline="\n",
        )
        if output.exists():
            shutil.rmtree(output)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Ace fonts directory")
    parser.add_argument("--output", type=Path, required=True, help="new build output directory")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY, help="GitHub owner/name")
    parser.add_argument(
        "--previous-catalog",
        type=Path,
        help="catalogVersion-1 catalog required when reusing older release assets",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace a prior marked output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = read_json(args.manifest.resolve())
        source_root = args.source_root.resolve()
        output = args.output.resolve()
        if (
            source_root == output
            or source_root.is_relative_to(output)
            or output.is_relative_to(source_root)
        ):
            raise DistributionError("--output and --source-root must not contain one another")
        previous_catalog = (
            read_json(args.previous_catalog.resolve())
            if args.previous_catalog is not None
            else None
        )
        catalog, assets = build_catalog(
            manifest, source_root, args.repository, previous_catalog
        )
        write_release(catalog, assets, output, args.overwrite)
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"Generated {len(catalog['fonts'])} fonts and {len(assets)} release assets in {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
