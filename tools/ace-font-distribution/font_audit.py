"""Validate SHA-bound cmap evidence for the reviewed Ace font inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from distribution import (
    DistributionError,
    SHA256_PATTERN,
    read_json,
    sha256_bytes,
    validate_manifest,
)


AUDIT_SCHEMA_VERSION = 1
CN_PROBE_CODEPOINTS = (0x4E00, 0x4E2D, 0x56FD, 0x7B80, 0x4F53, 0x6C49, 0x5B57)
JP_PROBE_CODEPOINTS = (0x3042, 0x30A2, 0x65E5, 0x672C, 0x8A9E)
EXPECTED_CRITERIA = {
    "cn": {
        "cjkUnifiedMinimum": 6000,
        "probeCodepoints": [f"U+{value:04X}" for value in CN_PROBE_CODEPOINTS],
    },
    "jp": {
        "cjkUnifiedMinimum": 2000,
        "hiraganaMinimum": 80,
        "katakanaMinimum": 80,
        "probeCodepoints": [f"U+{value:04X}" for value in JP_PROBE_CODEPOINTS],
    },
    "nerd": {
        "privateUseMinimum": 1000,
    },
}
AUDIT_FONT_FIELDS = frozenset(
    {
        "cjkUnifiedCount",
        "cnProbeCoverage",
        "fontPath",
        "horizontalAdvanceWidthCount",
        "id",
        "internalVersions",
        "jpProbeCoverage",
        "hiraganaCount",
        "katakanaCount",
        "legacyFamilyNames",
        "postIsFixedPitch",
        "privateUseCount",
        "sha256",
        "size",
        "typographicFamilyNames",
        "unicodeCodepointCount",
        "variationAxes",
    }
)


def _nonnegative_integer(value: Any, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DistributionError(f"{context} must be a non-negative integer")
    return value


def _string_array(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise DistributionError(f"{context} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise DistributionError(f"{context} must not contain duplicates")
    return value


def _source_path(source_root: Path, relative: str, context: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise DistributionError(f"{context} must be a non-empty string")
    candidate = (source_root / relative).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as error:
        raise DistributionError(f"{context} escapes source root: {relative}") from error
    if not candidate.is_file():
        raise DistributionError(f"{context} does not exist: {candidate}")
    return candidate


def validate_font_audit(
    manifest: dict[str, Any], audit: dict[str, Any], source_root: Path
) -> None:
    """Validate recorded cmap evidence and bind it to the exact manifest bytes."""

    validate_manifest(manifest)
    if audit.get("schemaVersion") != AUDIT_SCHEMA_VERSION:
        raise DistributionError(
            f"font audit schemaVersion must be {AUDIT_SCHEMA_VERSION}"
        )
    if audit.get("catalogVersion") != manifest["catalogVersion"]:
        raise DistributionError("font audit catalogVersion does not match manifest")
    if audit.get("criteria") != EXPECTED_CRITERIA:
        raise DistributionError("font audit criteria do not match the reviewed thresholds")
    generator = audit.get("generator")
    if not isinstance(generator, dict):
        raise DistributionError("font audit generator must be an object")
    if generator.get("script") != "audit_font_metadata.py":
        raise DistributionError("font audit generator script is invalid")
    fonttools_version = generator.get("fontToolsVersion")
    if not isinstance(fonttools_version, str) or not fonttools_version.strip():
        raise DistributionError("font audit generator fontToolsVersion is invalid")

    audit_fonts = audit.get("fonts")
    if not isinstance(audit_fonts, list) or not audit_fonts:
        raise DistributionError("font audit fonts must be a non-empty array")
    manifest_by_id = {font["id"]: font for font in manifest["fonts"]}
    seen_ids: set[str] = set()
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise DistributionError(f"font audit source root does not exist: {source_root}")

    for index, evidence in enumerate(audit_fonts):
        context = f"fontAudit.fonts[{index}]"
        if not isinstance(evidence, dict):
            raise DistributionError(f"{context} must be an object")
        unknown = set(evidence).difference(AUDIT_FONT_FIELDS)
        missing = AUDIT_FONT_FIELDS.difference(evidence)
        if unknown:
            raise DistributionError(
                f"{context} has unknown fields: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise DistributionError(
                f"{context} is missing fields: {', '.join(sorted(missing))}"
            )
        font_id = evidence["id"]
        if not isinstance(font_id, str) or font_id not in manifest_by_id:
            raise DistributionError(f"{context}.id is absent from the manifest")
        if font_id in seen_ids:
            raise DistributionError(f"duplicate font audit ID: {font_id}")
        seen_ids.add(font_id)
        manifest_font = manifest_by_id[font_id]
        if evidence["fontPath"] != manifest_font["fontPath"]:
            raise DistributionError(f"{context}.fontPath does not match the manifest")

        font_path = _source_path(source_root, evidence["fontPath"], f"{context}.fontPath")
        content = font_path.read_bytes()
        size = _nonnegative_integer(evidence["size"], f"{context}.size")
        if size != len(content) or size == 0:
            raise DistributionError(f"{context}.size does not match the source WOFF2")
        sha = evidence["sha256"]
        if not isinstance(sha, str) or not SHA256_PATTERN.fullmatch(sha):
            raise DistributionError(f"{context}.sha256 is invalid")
        if sha256_bytes(content) != sha:
            raise DistributionError(f"{context}.sha256 does not match the source WOFF2")

        for key in (
            "unicodeCodepointCount",
            "cjkUnifiedCount",
            "hiraganaCount",
            "katakanaCount",
            "privateUseCount",
            "cnProbeCoverage",
            "jpProbeCoverage",
            "horizontalAdvanceWidthCount",
        ):
            _nonnegative_integer(evidence[key], f"{context}.{key}")
        if not isinstance(evidence["postIsFixedPitch"], bool):
            raise DistributionError(f"{context}.postIsFixedPitch must be a boolean")
        for key in (
            "internalVersions",
            "legacyFamilyNames",
            "typographicFamilyNames",
        ):
            _string_array(evidence[key], f"{context}.{key}")
        variation_axes = evidence["variationAxes"]
        if not isinstance(variation_axes, list) or any(
            not isinstance(axis, str) or not axis.strip() for axis in variation_axes
        ):
            raise DistributionError(f"{context}.variationAxes must be a string array")
        if len(variation_axes) != len(set(variation_axes)):
            raise DistributionError(f"{context}.variationAxes must not contain duplicates")

        features = set(manifest_font["features"])
        if "cn" in features:
            if evidence["cjkUnifiedCount"] < EXPECTED_CRITERIA["cn"]["cjkUnifiedMinimum"]:
                raise DistributionError(f"{context} does not meet cn CJK coverage")
            if evidence["cnProbeCoverage"] != len(CN_PROBE_CODEPOINTS):
                raise DistributionError(f"{context} does not cover every cn probe")
        if "jp" in features:
            for count_key, threshold_key in (
                ("cjkUnifiedCount", "cjkUnifiedMinimum"),
                ("hiraganaCount", "hiraganaMinimum"),
                ("katakanaCount", "katakanaMinimum"),
            ):
                if evidence[count_key] < EXPECTED_CRITERIA["jp"][threshold_key]:
                    raise DistributionError(
                        f"{context} does not meet jp {count_key} coverage"
                    )
            if evidence["jpProbeCoverage"] != len(JP_PROBE_CODEPOINTS):
                raise DistributionError(f"{context} does not cover every jp probe")
        if "nerd" in features and evidence["privateUseCount"] < EXPECTED_CRITERIA["nerd"]["privateUseMinimum"]:
            raise DistributionError(f"{context} does not meet nerd private-use coverage")
        if "variable" in features and not variation_axes:
            raise DistributionError(f"{context} is marked variable but has no variation axes")

    if seen_ids != set(manifest_by_id):
        missing_ids = sorted(set(manifest_by_id).difference(seen_ids))
        raise DistributionError(
            "font audit is missing manifest ID(s): " + ", ".join(missing_ids)
        )


def read_and_validate_font_audit(
    manifest_path: Path, audit_path: Path, source_root: Path
) -> None:
    validate_font_audit(read_json(manifest_path), read_json(audit_path), source_root)
