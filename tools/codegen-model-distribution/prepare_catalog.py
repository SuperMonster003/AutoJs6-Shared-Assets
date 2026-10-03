#!/usr/bin/env python3
"""Prepare unsigned model catalog and only its newly introduced release assets."""

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
    parser.add_argument("--source-root", type=Path, default=Path("codegen-models/sources"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", default=distribution.DEFAULT_REPOSITORY)
    parser.add_argument("--catalog-version", required=True, type=int)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--allow-test-models", action="store_true")
    parser.add_argument("--empty-bootstrap", action="store_true", help="Skip sources and stage an unsigned empty initial catalog")
    args = parser.parse_args(argv)
    try:
        catalog = distribution.prepare_catalog(args.source_root, args.output, args.repository, args.catalog_version,
                                               args.generated_at, previous_catalog=args.previous_catalog,
                                               allow_test_models=args.allow_test_models, empty_bootstrap=args.empty_bootstrap)
    except (distribution.DistributionError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(f"Prepared unsigned catalog v{catalog['catalogVersion']} with {len(catalog['models'])} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
