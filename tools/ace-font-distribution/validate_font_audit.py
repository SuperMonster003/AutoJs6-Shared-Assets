#!/usr/bin/env python3
"""Validate a SHA-bound Ace font cmap audit using only the standard library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from distribution import DistributionError
from font_audit import read_and_validate_font_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        read_and_validate_font_audit(
            args.manifest.resolve(),
            args.audit.resolve(),
            args.source_root.resolve(),
        )
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Validated SHA-bound font audit: {args.audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
