#!/usr/bin/env python3
"""Export the manifest's reviewed font inputs from one exact Git commit."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from distribution import (
    COMMIT_PATTERN,
    DistributionError,
    canonical_json_bytes,
    read_json,
    validate_manifest,
    validate_woff2,
)


DEFAULT_MANIFEST = Path(__file__).with_name("font-sources.json")
DEFAULT_SOURCE_PREFIX = "app/src/main/assets/editor/ace-builds-1.4.12/fonts"
EXPORT_MARKER = ".ace-font-sources-export"


def _run_git(repository_root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise DistributionError(f"cannot run Git: {error}") from error
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise DistributionError(f"Git command failed: {message or arguments[0]}")
    return result.stdout


def resolve_commit(repository_root: Path, source_ref: str) -> str:
    repository_root = repository_root.resolve()
    if not repository_root.is_dir():
        raise DistributionError(f"Git repository is not a directory: {repository_root}")
    if not source_ref or "\x00" in source_ref:
        raise DistributionError("--source-ref must not be blank")
    resolved = _run_git(
        repository_root, "rev-parse", "--verify", f"{source_ref}^{{commit}}"
    ).decode("ascii", errors="strict").strip()
    if not COMMIT_PATTERN.fullmatch(resolved):
        raise DistributionError("--source-ref did not resolve to a full Git commit SHA")
    return resolved


def _safe_relative_path(value: str, context: str) -> PurePosixPath:
    if "\\" in value or "\x00" in value:
        raise DistributionError(f"{context} is not a safe POSIX relative path: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise DistributionError(f"{context} is not a safe POSIX relative path: {value}")
    return path


def _read_git_regular_file(
    repository_root: Path, commit: str, git_path: PurePosixPath
) -> bytes:
    path_value = git_path.as_posix()
    listing = _run_git(
        repository_root,
        "ls-tree",
        "--full-tree",
        commit,
        "--",
        path_value,
    ).decode("utf-8", errors="strict")
    lines = [line for line in listing.splitlines() if line]
    if len(lines) != 1 or "\t" not in lines[0]:
        raise DistributionError(f"source file does not exist at {commit}: {path_value}")
    metadata, listed_path = lines[0].split("\t", 1)
    fields = metadata.split()
    if listed_path != path_value or len(fields) != 3:
        raise DistributionError(f"unexpected Git tree entry for {path_value}")
    mode, object_type, object_id = fields
    if mode not in {"100644", "100755"} or object_type != "blob":
        raise DistributionError(f"source path is not a regular Git file: {path_value}")
    content = _run_git(repository_root, "cat-file", "blob", object_id)
    if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        raise DistributionError(
            f"source path is a Git LFS pointer rather than reviewed bytes: {path_value}"
        )
    return content


def required_source_paths(manifest: dict[str, Any]) -> list[tuple[str, bool]]:
    validate_manifest(manifest)
    paths: dict[str, bool] = {}
    for font in manifest["fonts"]:
        font_path = font["fontPath"]
        if font_path in paths and not paths[font_path]:
            raise DistributionError(
                f"source path is used as both font and notice: {font_path}"
            )
        paths[font_path] = True
        for notice_path in font["noticePaths"]:
            if notice_path in paths and paths[notice_path]:
                raise DistributionError(
                    f"source path is used as both font and notice: {notice_path}"
                )
            paths[notice_path] = False
    return list(paths.items())


def export_sources(
    repository_root: Path,
    source_ref: str,
    manifest: dict[str, Any],
    output: Path,
    source_prefix: str = DEFAULT_SOURCE_PREFIX,
    overwrite: bool = False,
) -> str:
    repository_root = repository_root.resolve()
    commit = resolve_commit(repository_root, source_ref)
    prefix = _safe_relative_path(source_prefix.rstrip("/"), "--source-prefix")
    required = required_source_paths(manifest)

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        marker = output / EXPORT_MARKER
        if not overwrite:
            raise DistributionError(f"output already exists (use --overwrite): {output}")
        if not output.is_dir() or not marker.is_file():
            raise DistributionError(
                f"refusing to replace output without {EXPORT_MARKER}: {output}"
            )

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        for relative_value, is_font in required:
            relative = _safe_relative_path(relative_value, "manifest source path")
            content = _read_git_regular_file(
                repository_root, commit, prefix.joinpath(relative)
            )
            if is_font:
                validate_woff2(content, relative.as_posix())
            elif not content:
                raise DistributionError(
                    f"notice file is empty at {commit}: {relative.as_posix()}"
                )
            destination = staging.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

        provenance = {
            "commit": commit,
            "sourcePrefix": prefix.as_posix(),
        }
        (staging / ".source-export.json").write_bytes(
            canonical_json_bytes(provenance)
        )
        (staging / EXPORT_MARKER).write_text(
            "Generated by tools/ace-font-distribution/export_sources.py.\n",
            encoding="utf-8",
            newline="\n",
        )
        if output.exists():
            shutil.rmtree(output)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-prefix", default=DEFAULT_SOURCE_PREFIX)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = read_json(args.manifest.resolve())
        commit = export_sources(
            args.repository_root,
            args.source_ref,
            manifest,
            args.output,
            args.source_prefix,
            args.overwrite,
        )
    except (DistributionError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Exported reviewed font sources from {commit} to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
