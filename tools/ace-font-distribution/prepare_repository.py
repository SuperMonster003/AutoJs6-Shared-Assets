#!/usr/bin/env python3
"""Prepare a self-contained AutoJs6-Shared-Assets repository tree."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from distribution import (
    DEFAULT_MANIFEST,
    DEFAULT_REPOSITORY,
    DistributionError,
    build_catalog,
    canonical_json_bytes,
    read_json,
)
from export_sources import DEFAULT_SOURCE_PREFIX, export_sources


TOOL_DIR = Path(__file__).resolve().parent
PREPARE_MARKER = ".autojs6-shared-assets-prepared"
PRIVATE_SUFFIXES = (".private.pem", ".private.der")
GIT_ATTRIBUTES = """* text=auto eol=lf
ace-fonts/sources/** whitespace=-trailing-space

*.woff2 binary
*.ttf binary
*.otf binary
*.der binary
*.png binary
*.jpg binary
*.jpeg binary
*.webp binary
*.zip binary
*.tar binary
*.gz binary
*.xz binary
"""


def _ignore_tool_entries(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in {
            "__pycache__",
            "keys",
            "catalog-v1.sig.json",
        }:
            ignored.add(name)
        elif name.endswith(".pyc") or name.endswith(PRIVATE_SUFFIXES):
            ignored.add(name)
    return ignored


def _copy_template(source: Path, destination: Path, repository: str) -> None:
    content = source.read_text(encoding="utf-8").replace(
        DEFAULT_REPOSITORY, repository
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")


def prepare_repository(
    source_repository_root: Path,
    source_ref: str,
    destination: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    repository: str = DEFAULT_REPOSITORY,
    source_prefix: str = DEFAULT_SOURCE_PREFIX,
    overwrite: bool = False,
) -> tuple[str, Path]:
    manifest_path = manifest_path.resolve()
    manifest = read_json(manifest_path)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        marker = destination / PREPARE_MARKER
        if not overwrite:
            raise DistributionError(
                f"destination already exists (use --overwrite): {destination}"
            )
        if not destination.is_dir() or not marker.is_file():
            raise DistributionError(
                f"refusing to replace destination without {PREPARE_MARKER}: "
                f"{destination}"
            )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        tools_destination = staging / "tools/ace-font-distribution"
        shutil.copytree(
            TOOL_DIR,
            tools_destination,
            ignore=_ignore_tool_entries,
            dirs_exist_ok=False,
        )
        shutil.copy2(manifest_path, tools_destination / "font-sources.json")

        workflow = TOOL_DIR / "workflow/release-fonts.yml"
        workflow_destination = staging / ".github/workflows/publish-ace-fonts.yml"
        workflow_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workflow, workflow_destination)

        _copy_template(
            TOOL_DIR / "standalone-repository-README.md",
            staging / "README.md",
            repository,
        )
        _copy_template(
            TOOL_DIR / "ace-fonts-README.md",
            staging / "ace-fonts/README.md",
            repository,
        )
        (staging / ".gitignore").write_text(
            "build/\n__pycache__/\n*.pyc\n*.private.pem\n*.private.der\n"
            f"{PREPARE_MARKER}\n",
            encoding="utf-8",
            newline="\n",
        )
        (staging / ".gitattributes").write_text(
            GIT_ATTRIBUTES,
            encoding="utf-8",
            newline="\n",
        )

        sources = staging / "ace-fonts/sources"
        source_commit = export_sources(
            source_repository_root,
            source_ref,
            manifest,
            sources,
            source_prefix,
            overwrite=False,
        )

        catalog, _assets = build_catalog(manifest, sources, repository)
        catalogs = staging / "ace-fonts/catalogs"
        catalogs.mkdir(parents=True, exist_ok=True)
        catalog_path = catalogs / "catalog-v1.json"
        catalog_path.write_bytes(canonical_json_bytes(catalog))

        schemas = staging / "ace-fonts/schemas"
        schemas.mkdir(parents=True, exist_ok=True)
        for name in ("catalog-v1.schema.json", "signature-v1.schema.json"):
            shutil.copy2(TOOL_DIR / name, schemas / name)

        public_key = TOOL_DIR / "catalog-v1-signing-public.pem"
        if not public_key.is_file():
            raise DistributionError(f"distribution public key is missing: {public_key}")
        keys = staging / "ace-fonts/keys"
        keys.mkdir(parents=True, exist_ok=True)
        shutil.copy2(public_key, keys / "catalog-signing-public.pem")

        (staging / PREPARE_MARKER).write_text(
            "Prepared by tools/ace-font-distribution/prepare_repository.py.\n",
            encoding="utf-8",
            newline="\n",
        )
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return source_commit, destination / "ace-fonts/catalogs/catalog-v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--source-prefix", default=DEFAULT_SOURCE_PREFIX)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        source_commit, catalog_path = prepare_repository(
            args.source_repository_root,
            args.source_ref,
            args.destination,
            args.manifest,
            args.repository,
            args.source_prefix,
            args.overwrite,
        )
    except (DistributionError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Prepared {args.destination.resolve()} from source commit {source_commit}")
    print(f"Review and offline-sign the unsigned catalog: {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
