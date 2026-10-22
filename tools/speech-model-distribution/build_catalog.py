#!/usr/bin/env python3
"""Build an unsigned speech model catalog from reviewed sources, without network access.

The output directory receives catalog-v{schemaVersion}.json (catalog-v2.json for the current
schema), release-assets.txt (archives first published by this catalog version), preparation.json
and a marker file. Existing output is never replaced.
"""

import argparse
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile


def _distribution():
    key, path = "autojs6_speech_distribution", Path(__file__).with_name("distribution.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("Unexpected speech distribution module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def write_output(output, catalog, new_assets, distribution):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise distribution.DistributionError("Output already exists; use a new pending or build directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = distribution.expected_release_assets(catalog)
    if sorted(assets) != new_assets:
        raise distribution.DistributionError("Newly introduced archives differ from the catalog's release assets")
    temporary = Path(tempfile.mkdtemp(prefix="." + output.name + "-", dir=output.parent))
    try:
        # Before anything is written, so every file inherits the access rights of the final directory.
        distribution.inherit_parent_acl(temporary)
        (temporary / distribution.catalog_file(catalog["schemaVersion"])).write_bytes(distribution.canonical_json_bytes(catalog))
        (temporary / "release-assets.txt").write_text("".join(name + "\n" for name in new_assets), encoding="utf-8", newline="\n")
        (temporary / "preparation.json").write_bytes(distribution.canonical_json_bytes({
            "format": 1, "repository": catalog["repository"], "catalogVersion": catalog["catalogVersion"],
            "generatedAt": catalog["generatedAt"], "models": len(catalog["models"]),
            "releaseAssetCount": len(new_assets),
            "releaseAssetBytes": sum(version["mirror"]["size"] for _model, version in assets.values()),
            "upstreamOnlyVersions": len(distribution.upstream_only_versions(catalog)),
            "unsigned": True,
        }))
        (temporary / distribution.OUTPUT_MARKER).write_text("Unsigned speech model catalog staging.\n", encoding="utf-8", newline="\n")
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main(argv=None):
    distribution = _distribution()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("speech-models/sources"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", default=distribution.DEFAULT_REPOSITORY)
    parser.add_argument("--catalog-version", required=True, type=int)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--previous-catalog", type=Path)
    args = parser.parse_args(argv)
    try:
        previous = distribution.read_json(args.previous_catalog) if args.previous_catalog else None
        catalog, new_assets = distribution.build_catalog(args.source_root, args.repository, args.catalog_version,
                                                         args.generated_at, previous_catalog=previous)
        write_output(args.output, catalog, new_assets, distribution)
    except (distribution.DistributionError, OSError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    print(f"Prepared unsigned speech catalog v{catalog['catalogVersion']} with {len(catalog['models'])} models, "
          f"{len(new_assets)} new release archives and {len(distribution.upstream_only_versions(catalog))} upstream-only versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
