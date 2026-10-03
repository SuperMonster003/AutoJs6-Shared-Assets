#!/usr/bin/env python3
"""Maintainer-only offline P-256 key generation; private keys must stay outside Git."""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import sys


def _crypto():
    key = "autojs6_codegen_crypto"
    path = Path(__file__).with_name("crypto.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("codegen crypto module belongs to another file")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--public-key-pem", required=True, type=Path)
    parser.add_argument("--public-key-der", required=True, type=Path)
    parser.add_argument("--openssl")
    args = parser.parse_args()
    crypto = _crypto()
    try:
        key_id = crypto.generate_key_pair(args.private_key, args.public_key_pem, args.public_key_der, args.openssl)
    except (crypto.DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Generated offline ECDSA P-256 key pair; keyId: {key_id}")
    print("Keep the private key offline and outside every Git working tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
