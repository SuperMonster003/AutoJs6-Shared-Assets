#!/usr/bin/env python3
"""Generate an offline P-256 key and export its X.509/SPKI public key."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from crypto import generate_key_pair
from distribution import DistributionError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key-pem", type=Path, required=True)
    parser.add_argument("--public-key-der", type=Path, required=True)
    parser.add_argument("--openssl", help="path to the OpenSSL executable")
    args = parser.parse_args()
    try:
        suggested_key_id = generate_key_pair(
            args.private_key,
            args.public_key_pem,
            args.public_key_der,
            args.openssl,
        )
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    der_base64 = base64.b64encode(args.public_key_der.resolve().read_bytes()).decode("ascii")
    print(f"Generated ECDSA P-256 key pair; suggested key ID: {suggested_key_id}")
    print(f"Android SPKI DER Base64: {der_base64}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
