#!/usr/bin/env python3
"""Validate an AutoJs6 font catalog without third-party dependencies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from distribution import DistributionError, read_json, validate_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--minimum-catalog-version", type=int, default=1)
    args = parser.parse_args()
    try:
        catalog = read_json(args.catalog.resolve())
        validate_catalog(catalog, args.minimum_catalog_version)
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"Valid catalog v{catalog['catalogVersion']} with {len(catalog['fonts'])} fonts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
