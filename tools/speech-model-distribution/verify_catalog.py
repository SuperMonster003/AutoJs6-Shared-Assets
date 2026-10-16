#!/usr/bin/env python3
"""Verify a speech model catalog: schema rules, monotonic history, immutable versions and signature.

Without --signature the catalog is checked as an unsigned review candidate. --source-root also
rebuilds the catalog from the reviewed sources and requires identical bytes. With --signature,
--public-key and --expected-key-id the exact catalog bytes must carry a valid detached signature.
"""

import argparse
import importlib.util
from pathlib import Path
import sys


def _module(name, filename):
    key, path = "autojs6_speech_" + name, Path(__file__).with_name(filename).resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("Unexpected speech distribution module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def verify(args, distribution, crypto=None):
    data = Path(args.catalog).read_bytes()
    catalog = distribution.read_json(args.catalog)
    previous = distribution.read_json(args.previous_catalog) if args.previous_catalog else None
    distribution.validate_catalog(catalog, args.minimum_catalog_version, previous_catalog=previous,
                                  expected_repository=args.expected_repository)
    if data != distribution.canonical_json_bytes(catalog):
        raise distribution.DistributionError("Catalog bytes are not in canonical form")
    if args.source_root:
        rebuilt, _ = distribution.build_catalog(args.source_root, catalog["repository"], catalog["catalogVersion"],
                                                catalog["generatedAt"], previous_catalog=previous)
        if distribution.canonical_json_bytes(rebuilt) != data:
            raise distribution.DistributionError("Catalog differs from the catalog rebuilt from its sources")
    if args.signature:
        crypto.verify_catalog_material(args.catalog, args.signature, args.public_key, args.expected_key_id,
                                       args.minimum_catalog_version, args.openssl, expected_repository=args.expected_repository)
    return catalog


def main(argv=None):
    distribution = _module("distribution", "distribution.py")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--minimum-catalog-version", type=int, default=1)
    parser.add_argument("--expected-repository")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--expected-key-id")
    parser.add_argument("--openssl")
    args = parser.parse_args(argv)
    signed = (args.signature, args.public_key, args.expected_key_id)
    if any(signed) and not all(signed):
        parser.error("--signature, --public-key and --expected-key-id must be used together")
    try:
        crypto = _module("crypto", "crypto.py") if args.signature else None
        catalog = verify(args, distribution, crypto)
    except (distribution.DistributionError, OSError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    state = f"signed with key {args.expected_key_id}" if args.signature else "unsigned"
    print(f"Verified speech catalog v{catalog['catalogVersion']} with {len(catalog['models'])} models ({state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
