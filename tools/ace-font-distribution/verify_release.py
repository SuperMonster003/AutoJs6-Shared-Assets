#!/usr/bin/env python3
"""Verify release asset bytes against a validated font catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from distribution import (
    DistributionError,
    read_json,
    sha256_bytes,
    validate_catalog,
    validate_woff2,
)


def _expected_assets(catalog: dict[str, Any]) -> dict[str, tuple[int, str, bool]]:
    expected: dict[str, tuple[int, str, bool]] = {}
    for font in catalog["fonts"]:
        artifact = font["artifact"]
        if artifact["version"] != catalog["catalogVersion"]:
            continue
        expected[artifact["fileName"]] = (
            artifact["size"],
            artifact["sha256"],
            True,
        )
        for notice in font["license"]["files"]:
            expected[notice["fileName"]] = (
                notice["size"],
                notice["sha256"],
                False,
            )
    return expected


def verify_release(catalog: dict[str, Any], assets_dir: Path) -> None:
    validate_catalog(catalog)
    assets_dir = assets_dir.resolve()
    if not assets_dir.is_dir():
        raise DistributionError(f"assets directory does not exist: {assets_dir}")
    expected = _expected_assets(catalog)
    actual = {path.name for path in assets_dir.iterdir() if path.is_file()}
    missing = sorted(set(expected).difference(actual))
    unexpected = sorted(actual.difference(expected))
    if missing:
        raise DistributionError("missing release asset(s): " + ", ".join(missing))
    if unexpected:
        raise DistributionError("unexpected release asset(s): " + ", ".join(unexpected))
    for file_name, (expected_size, expected_sha, is_font) in expected.items():
        content = (assets_dir / file_name).read_bytes()
        if len(content) != expected_size:
            raise DistributionError(f"{file_name}: size does not match catalog")
        if sha256_bytes(content) != expected_sha:
            raise DistributionError(f"{file_name}: SHA-256 does not match catalog")
        if is_font:
            validate_woff2(content, file_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--assets-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        catalog = read_json(args.catalog.resolve())
        verify_release(catalog, args.assets_dir)
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"Verified {len(_expected_assets(catalog))} assets for "
        f"{catalog['releaseTag']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
