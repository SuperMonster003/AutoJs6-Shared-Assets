#!/usr/bin/env python3
"""Build a pending holiday-calendars catalog from the committed data files.

Usage:
    python build_catalog.py --data-dir holiday-calendars/data --output-dir holiday-calendars/catalogs/pending/v<N>
        --catalog-version <N> --generated-at 2026-11-12T00:00:00Z
        [--previous-catalog holiday-calendars/catalogs/history/v<N-1>/catalog-v1.json] [--stage-assets DIR]

Writes catalog-v1.json, release-assets.txt (assets this release introduces) and preparation.json.
A region whose data is unchanged since the previous catalog keeps its earlier release asset.
With --stage-assets, the new assets are copied there under their content-addressed names.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calendar_format import (  # noqa: E402
    CATALOG_NAME,
    DEFAULT_REPOSITORY,
    FAMILY,
    MAX_CALENDAR_BYTES,
    MAX_CATALOG_BYTES,
    SCHEMA_VERSION,
    FormatError,
    asset_name,
    asset_url,
    canonical_json_bytes,
    check_catalog_history,
    new_assets,
    read_json,
    release_tag,
    summary_of,
    validate_calendar,
    validate_catalog,
)

GENERATION_FILE = "generation.json"


def data_files(data_dir: Path) -> list[Path]:
    files = sorted(path for path in data_dir.glob("*.json") if path.name != GENERATION_FILE)
    if not files:
        raise FormatError(f"{data_dir} has no calendar files")
    return files


def build(data_dir: Path, catalog_version: int, generated_at: str, previous: dict | None,
          repository: str = DEFAULT_REPOSITORY) -> tuple[dict, dict[str, Path]]:
    generation, _ = read_json(data_dir / GENERATION_FILE, 64 * 1024)
    tag = release_tag(catalog_version)
    previous_files = {region["code"]: region["file"] for region in (previous or {}).get("regions", [])}
    regions = []
    sources: dict[str, Path] = {}
    for path in data_files(data_dir):
        document, data = read_json(path, MAX_CALENDAR_BYTES)
        validate_calendar(document)
        if path.name != f"{document['region']}.json":
            raise FormatError(f"{path.name} holds region {document['region']}")
        if document["source"]["version"] != generation["source"]["version"]:
            raise FormatError(f"{path.name} was generated from another package version")
        digest = hashlib.sha256(data).hexdigest()
        old = previous_files.get(document["region"])
        if old is not None and old["sha256"] == digest:
            entry = dict(old)
        else:
            name = asset_name(document["region"], digest)
            entry = {"name": name, "releaseTag": tag, "sha256": digest, "size": len(data),
                     "url": asset_url(repository, tag, name)}
            sources[name] = path
        region = summary_of(document)
        region["file"] = entry
        regions.append(region)
    source = generation["source"]
    catalog = {
        "schemaVersion": SCHEMA_VERSION,
        "family": FAMILY,
        "catalogVersion": catalog_version,
        "generatedAt": generated_at,
        "repository": repository,
        "releaseTag": tag,
        "source": {key: source[key] for key in ("homepage", "license", "name", "package", "version")},
        "years": generation["years"],
        "regions": regions,
    }
    validate_catalog(catalog, catalog_version, expected_repository=repository)
    check_catalog_history(catalog, previous)
    if not sources:
        raise FormatError("no calendar changed since the previous catalog; nothing to release")
    if len(canonical_json_bytes(catalog)) > MAX_CATALOG_BYTES:
        raise FormatError("catalog is too large")
    return catalog, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--catalog-version", type=int, required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--stage-assets", type=Path, help="copy the new assets here under their release names")
    args = parser.parse_args(argv)
    try:
        previous = None
        if args.previous_catalog is not None:
            previous, _ = read_json(args.previous_catalog, MAX_CATALOG_BYTES)
            validate_catalog(previous, expected_repository=args.repository)
        catalog, sources = build(args.data_dir, args.catalog_version, args.generated_at, previous, args.repository)
    except (FormatError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names = new_assets(catalog)
    (args.output_dir / CATALOG_NAME).write_bytes(canonical_json_bytes(catalog))
    (args.output_dir / "release-assets.txt").write_bytes("".join(f"{name}\n" for name in names).encode("ascii"))
    preparation = {
        "catalogVersion": catalog["catalogVersion"],
        "format": 1,
        "generatedAt": catalog["generatedAt"],
        "previousCatalogVersion": previous["catalogVersion"] if previous else None,
        "regions": len(catalog["regions"]),
        "releaseAssetBytes": sum(sources[name].stat().st_size for name in names),
        "releaseAssetCount": len(names),
        "repository": catalog["repository"],
        "source": f"{catalog['source']['name']} {catalog['source']['version']}",
        "subdivisions": sum(len(region["subdivisions"]) for region in catalog["regions"]),
        "unsigned": True,
    }
    (args.output_dir / "preparation.json").write_bytes(canonical_json_bytes(preparation))
    if args.stage_assets is not None:
        args.stage_assets.mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copyfile(sources[name], args.stage_assets / name)
    print(f"catalog v{catalog['catalogVersion']}: {len(catalog['regions'])} regions, "
          f"{len(names)} new assets ({preparation['releaseAssetBytes']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
