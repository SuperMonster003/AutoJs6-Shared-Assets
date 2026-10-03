#!/usr/bin/env python3
"""Verify exact catalog bytes, a pinned SPKI key, and the codegen catalog schema."""
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
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--expected-key-id", required=True)
    parser.add_argument("--minimum-catalog-version", type=int, default=1)
    parser.add_argument("--expected-repository")
    parser.add_argument("--allow-test-models", action="store_true")
    parser.add_argument("--openssl")
    args = parser.parse_args()
    crypto = _crypto()
    try:
        envelope = crypto.verify_catalog_signature(args.catalog, args.signature, args.public_key, args.expected_key_id,
            args.minimum_catalog_version, args.openssl, allow_test_models=args.allow_test_models,
            expected_repository=args.expected_repository)
    except (crypto.DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Verified {envelope['catalog']} with key {envelope['keyId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
