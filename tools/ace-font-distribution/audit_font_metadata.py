#!/usr/bin/env python3
"""Generate deterministic cmap evidence for the reviewed Ace WOFF2 inventory.

This development-only auditor requires ``fonttools[woff]``. Release and CI
validation use the SHA-bound report and the standard-library-only
``validate_font_audit.py`` instead.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from distribution import (
    DistributionError,
    canonical_json_bytes,
    read_json,
    sha256_bytes,
    validate_manifest,
    validate_woff2,
)
from font_audit import (
    AUDIT_SCHEMA_VERSION,
    CN_PROBE_CODEPOINTS,
    EXPECTED_CRITERIA,
    JP_PROBE_CODEPOINTS,
    validate_font_audit,
)

try:
    import fontTools
    from fontTools.ttLib import TTFont
except ModuleNotFoundError as error:  # pragma: no cover - environment dependent
    print(
        "error: audit_font_metadata.py requires fonttools[woff] "
        "(install tools/ace-font-distribution/requirements-audit.txt)",
        file=sys.stderr,
    )
    raise SystemExit(2) from error


TOOL_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOL_DIR.parents[1]
DEFAULT_MANIFEST = TOOL_DIR / "font-sources.json"
DEFAULT_SOURCE_ROOT = REPOSITORY_ROOT / "ace-fonts/sources"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "ace-fonts/audits/font-audit-v4.json"


def _unicode_codepoints(font: TTFont) -> set[int]:
    codepoints: set[int] = set()
    for table in font["cmap"].tables:
        if table.isUnicode():
            codepoints.update(table.cmap)
    return codepoints


def _names(font: TTFont, name_id: int) -> list[str]:
    values: set[str] = set()
    for record in font["name"].names:
        if record.nameID != name_id:
            continue
        try:
            value = record.toUnicode().strip()
        except (UnicodeDecodeError, AttributeError):
            continue
        if value:
            values.add(value)
    return sorted(values, key=lambda value: (value.casefold(), value))


def _variation_axes(font: TTFont) -> list[str]:
    if "fvar" not in font:
        return []
    return sorted({axis.axisTag for axis in font["fvar"].axes})


def _audit_font(font_id: str, relative: str, source_root: Path) -> dict[str, Any]:
    path = (source_root / relative).resolve()
    try:
        path.relative_to(source_root)
    except ValueError as error:
        raise DistributionError(f"{font_id}.fontPath escapes source root") from error
    if not path.is_file():
        raise DistributionError(f"{font_id}.fontPath does not exist: {path}")
    content = path.read_bytes()
    validate_woff2(content, relative)
    try:
        font = TTFont(path, lazy=False)
    except Exception as error:
        raise DistributionError(f"cannot parse {relative} with fontTools: {error}") from error
    try:
        codepoints = _unicode_codepoints(font)
        widths = {
            width
            for glyph_name, (width, _left_side_bearing) in font["hmtx"].metrics.items()
            if glyph_name != ".notdef"
        }
        return {
            "cjkUnifiedCount": sum(0x4E00 <= value <= 0x9FFF for value in codepoints),
            "cnProbeCoverage": sum(value in codepoints for value in CN_PROBE_CODEPOINTS),
            "fontPath": relative,
            "hiraganaCount": sum(0x3040 <= value <= 0x309F for value in codepoints),
            "horizontalAdvanceWidthCount": len(widths),
            "id": font_id,
            "internalVersions": _names(font, 5),
            "jpProbeCoverage": sum(value in codepoints for value in JP_PROBE_CODEPOINTS),
            "katakanaCount": sum(0x30A0 <= value <= 0x30FF for value in codepoints),
            "legacyFamilyNames": _names(font, 1),
            "postIsFixedPitch": bool(font["post"].isFixedPitch),
            "privateUseCount": sum(
                0xE000 <= value <= 0xF8FF
                or 0xF0000 <= value <= 0xFFFFD
                or 0x100000 <= value <= 0x10FFFD
                for value in codepoints
            ),
            "sha256": sha256_bytes(content),
            "size": len(content),
            "typographicFamilyNames": _names(font, 16),
            "unicodeCodepointCount": len(codepoints),
            "variationAxes": _variation_axes(font),
        }
    finally:
        font.close()


def build_font_audit(manifest: dict[str, Any], source_root: Path) -> dict[str, Any]:
    validate_manifest(manifest)
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise DistributionError(f"source root does not exist: {source_root}")
    report = {
        "catalogVersion": manifest["catalogVersion"],
        "criteria": EXPECTED_CRITERIA,
        "fonts": [
            _audit_font(font["id"], font["fontPath"], source_root)
            for font in sorted(manifest["fonts"], key=lambda item: item["order"])
        ],
        "generator": {
            "fontToolsVersion": fontTools.__version__,
            "script": "audit_font_metadata.py",
        },
        "schemaVersion": AUDIT_SCHEMA_VERSION,
    }
    validate_font_audit(manifest, report, source_root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare generated canonical bytes with --output without modifying it",
    )
    args = parser.parse_args()
    try:
        manifest = read_json(args.manifest.resolve())
        report = build_font_audit(manifest, args.source_root.resolve())
        content = canonical_json_bytes(report)
        output = args.output.resolve()
        if args.check:
            if not output.is_file() or output.read_bytes() != content:
                raise DistributionError(f"font audit is stale: {output}")
            print(f"Font audit is current: {output}")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Generated SHA-bound font audit: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
