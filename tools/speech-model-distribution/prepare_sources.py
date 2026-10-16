#!/usr/bin/env python3
"""Download pinned upstream sherpa-onnx assets and rebuild the content-addressed mirror archives.

Without --update-sources every rebuilt archive and file list must equal source.json, which makes
the step a reproducibility check. With --update-sources the measured archive and file records
are written back (use it only when adding or reviewing a new model version). Upstream-only
sources (mirror false) get their files[] measured but no archive; --catalog never selects them.
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


def select_sources(sources, models, catalog, distribution):
    selected = list(sources)
    if catalog is not None:
        wanted = {(model["modelId"], version["versionCode"]): version["mirror"]
                  for model, version in distribution.expected_release_assets(catalog).values()}
        selected = [(folder, source) for folder, source in selected if (source["modelId"], source["versionCode"]) in wanted]
        if len(selected) != len(wanted):
            raise distribution.DistributionError("The catalog's current release names versions without sources")
        for _folder, source in selected:
            mirror = wanted[(source["modelId"], source["versionCode"])]
            if (mirror["size"], mirror["sha256"]) != (source["archive"]["size"], source["archive"]["sha256"]):
                raise distribution.DistributionError("source.json differs from the catalog mirror record: " + source["modelId"])
    if models:
        requested = set(models)
        selected = [(folder, source) for folder, source in selected if f"{source['modelId']}/{source['versionCode']}" in requested]
        found = {f"{source['modelId']}/{source['versionCode']}" for _folder, source in selected}
        if found != requested:
            raise distribution.DistributionError("Unknown --model selection: " + ", ".join(sorted(requested - found)))
    return selected


def main(argv=None):
    distribution = _module("distribution", "distribution.py")
    preparation = _module("preparation", "preparation.py")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("speech-models/sources"))
    parser.add_argument("--cache-dir", type=Path, default=Path("build/speech-models/upstream"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/speech-models/assets"))
    parser.add_argument("--model", action="append", default=[], metavar="MODEL_ID/VERSION_CODE",
                        help="Limit preparation to one model version; repeatable")
    parser.add_argument("--catalog", type=Path, help="Prepare only the archives first published by this catalog's release")
    parser.add_argument("--update-sources", action="store_true", help="Record measured archive and file digests in source.json")
    parser.add_argument("--offline", action="store_true", help="Use only the verified upstream cache")
    args = parser.parse_args(argv)
    try:
        if args.update_sources and args.catalog:
            parser.error("--update-sources cannot be combined with --catalog")
        sources = distribution.load_sources(args.source_root, require_measured=not args.update_sources)
        catalog = None
        if args.catalog:
            catalog = distribution.validate_catalog(distribution.read_json(args.catalog))
        selected = select_sources(sources, args.model, catalog, distribution)
        result = preparation.prepare(selected, args.cache_dir, args.output_dir, update_sources=args.update_sources,
                                     offline=args.offline)
    except (distribution.DistributionError, OSError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    archives = [path for _source, path in result if path is not None]
    total = sum(path.stat().st_size for path in archives)
    print(f"Prepared {len(archives)} speech model archives ({total} bytes) in {args.output_dir}; "
          f"{len(result) - len(archives)} upstream-only versions verified without an archive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
