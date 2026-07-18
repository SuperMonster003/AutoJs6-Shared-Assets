#!/usr/bin/env python3
"""Sign a catalog with an offline ECDSA P-256 private key."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crypto import sign_catalog
from distribution import DistributionError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--openssl", help="path to the OpenSSL executable")
    args = parser.parse_args()
    try:
        envelope = sign_catalog(
            args.catalog,
            args.private_key,
            args.output,
            args.key_id,
            args.openssl,
        )
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Signed {envelope['catalog']} with key {envelope['keyId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
