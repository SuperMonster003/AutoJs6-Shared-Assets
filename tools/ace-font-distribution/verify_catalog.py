#!/usr/bin/env python3
"""Verify a catalog's detached ECDSA P-256/SHA-256 signature."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crypto import verify_catalog_signature
from distribution import DistributionError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--expected-key-id")
    parser.add_argument("--minimum-catalog-version", type=int, default=1)
    parser.add_argument("--openssl", help="path to the OpenSSL executable")
    args = parser.parse_args()
    try:
        envelope = verify_catalog_signature(
            args.catalog,
            args.signature,
            args.public_key,
            args.expected_key_id,
            args.minimum_catalog_version,
            args.openssl,
        )
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Verified {envelope['catalog']} with key {envelope['keyId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
