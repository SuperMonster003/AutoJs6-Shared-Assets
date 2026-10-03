#!/usr/bin/env python3
"""Validate codegen catalog shape, immutable history, URLs, and status changes."""

import argparse
import importlib.util
from pathlib import Path
import sys


def _distribution():
    key, path = "autojs6_codegen_distribution", Path(__file__).with_name("distribution.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise ValueError("Unexpected codegen distribution module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    distribution = _distribution()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--minimum-catalog-version", type=int, default=1)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--expected-repository")
    parser.add_argument("--allow-test-models", action="store_true")
    args = parser.parse_args(argv)
    try:
        catalog = distribution.read_json(args.catalog)
        previous = distribution.read_json(args.previous_catalog) if args.previous_catalog else None
        distribution.validate_catalog(catalog, args.minimum_catalog_version, previous_catalog=previous,
                                      expected_repository=args.expected_repository, allow_test_models=args.allow_test_models)
    except (distribution.DistributionError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(f"Valid catalog v{catalog['catalogVersion']} with {len(catalog['models'])} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
