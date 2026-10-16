#!/usr/bin/env python3
"""Maintainer-only offline signing of a validated speech model catalog; the private key stays outside Git."""

import argparse
import importlib.util
from pathlib import Path
import sys


def _crypto():
    key, path = "autojs6_speech_crypto", Path(__file__).with_name("crypto.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("speech crypto module belongs to another file")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--expected-repository")
    parser.add_argument("--openssl")
    args = parser.parse_args(argv)
    crypto = _crypto()
    try:
        envelope = crypto.sign_catalog(args.catalog, args.private_key, args.output, args.key_id, args.openssl,
                                       expected_repository=args.expected_repository)
    except (crypto.DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Signed {envelope['catalog']} with key {envelope['keyId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
