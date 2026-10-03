#!/usr/bin/env python3
"""Verify immutable model release assets locally, or check remote tag/release absence.

Remote preflight is read-only. Downloads and publishing remain explicit workflow
steps using GitHub CLI, which manages authentication without forwarding tokens to
arbitrary catalog URLs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


def _module(name, filename):
    if name not in sys.modules:
        specification = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
        module = importlib.util.module_from_spec(specification)
        sys.modules[name] = module
        specification.loader.exec_module(module)
    return sys.modules[name]


distribution = _module("autojs6_codegen_distribution", "distribution.py")
DistributionError = distribution.DistributionError
OFFICIAL_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
CATALOG_NAME = "catalog-v1.json"
SIGNATURE_NAME = "catalog-v1.sig.json"


def _same_bytes(actual_path, expected):
    if actual_path.stat().st_size != len(expected):
        return False
    with actual_path.open("rb") as source:
        return source.read(len(expected) + 1) == expected


def _asset_hash(path, expected_size):
    digest, total = hashlib.sha256(), 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            total += len(block)
            if total > expected_size:
                raise DistributionError("Release model grew beyond its catalog size")
            digest.update(block)
    if total != expected_size:
        raise DistributionError("Release model size changed during verification")
    return digest.hexdigest()


def expected_assets(catalog, *, all_artifacts=False):
    result = {}
    for model in catalog["models"]:
        for version in model["versions"]:
            artifact = version["artifact"]
            parts = urlsplit(artifact["url"]).path.split("/")
            if not all_artifacts and parts[-2] != catalog["releaseTag"]:
                continue
            filename = artifact["fileName"]
            if filename in result:
                raise DistributionError("Duplicate release asset filename")
            result[filename] = (model, version)
    return result


def verify_release(catalog_path, assets_dir, *, signature_path=None, downloaded_release=False,
                   all_artifacts=False, expected_repository=None, allow_test_models=False,
                   asset_list=None):
    catalog_path = Path(catalog_path).resolve()
    catalog = distribution.read_json(catalog_path)
    distribution.validate_catalog(catalog, expected_repository=expected_repository, allow_test_models=allow_test_models)
    if allow_test_models and catalog["repository"].casefold() == OFFICIAL_REPOSITORY.casefold():
        raise DistributionError("Test models cannot be published to the canonical repository")
    assets_dir = Path(assets_dir).resolve()
    if not assets_dir.is_dir():
        raise DistributionError("Release asset directory does not exist")
    expected = expected_assets(catalog, all_artifacts=all_artifacts)
    names = set(expected)
    if downloaded_release:
        if signature_path is None:
            raise DistributionError("Downloaded-release verification requires the reviewed signature")
        names.update((CATALOG_NAME, SIGNATURE_NAME))
    actual = {}
    for path in assets_dir.iterdir():
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(assets_dir):
            raise DistributionError("Release assets must be ordinary files directly inside the download directory")
        actual[path.name] = path
    missing, unexpected = names - actual.keys(), actual.keys() - names
    if missing:
        raise DistributionError("Missing release assets: " + ", ".join(sorted(missing)))
    if unexpected:
        raise DistributionError("Unexpected release assets: " + ", ".join(sorted(unexpected)))
    if downloaded_release:
        if not _same_bytes(actual[CATALOG_NAME], catalog_path.read_bytes()):
            raise DistributionError("Downloaded catalog differs from the offline-reviewed catalog")
        if not _same_bytes(actual[SIGNATURE_NAME], Path(signature_path).read_bytes()):
            raise DistributionError("Downloaded signature differs from the offline-reviewed signature")
    if asset_list is not None:
        entries = Path(asset_list).read_text(encoding="utf-8").splitlines()
        if len(entries) != len(set(entries)) or set(entries) != set(expected):
            raise DistributionError("release-assets.txt does not exactly cover the expected model files")
    for filename, (model, version) in sorted(expected.items()):
        path, artifact = actual[filename], version["artifact"]
        if path.stat().st_size != artifact["size"]:
            raise DistributionError("Release model size differs from catalog: " + filename)
        digest = _asset_hash(path, artifact["size"])
        if digest != artifact["sha256"]:
            raise DistributionError("Release model SHA-256 differs from catalog: " + filename)
        manifest = distribution.validate_package(path)
        distribution.compare_release_version(manifest, model, version)
    return {"releaseTag": catalog["releaseTag"], "models": len(expected),
            "downloadedRelease": downloaded_release, "allArtifacts": all_artifacts}


def _github_get(endpoint, runner):
    try:
        process = runner(["gh", "api", "--hostname", "github.com", "--method", "GET", "--include", endpoint],
                         capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise DistributionError("GitHub preflight request failed; absence was not established") from error
    # Do not echo stdout/stderr on an error: authentication helpers or proxies can
    # include credentials in diagnostics. Only explicit HTTP status is surfaced.
    text = process.stdout.replace("\r\n", "\n") if isinstance(process.stdout, str) else ""
    header, separator, body = text.partition("\n\n")
    match = re.match(r"\AHTTP/\S+\s+(\d{3})(?:\s|$)", header)
    if not separator or match is None:
        raise DistributionError("GitHub preflight did not provide a verifiable HTTP status")
    status = int(match[1])
    if status == 404 and process.returncode == 1:
        return status, None
    if status != 200 or process.returncode != 0:
        raise DistributionError(f"GitHub preflight failed with HTTP {status}; absence was not established")
    try:
        payload = json.loads(body)
    except (ValueError, TypeError) as error:
        raise DistributionError("GitHub preflight returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise DistributionError("GitHub preflight returned an unexpected response")
    return status, payload


def check_remote_absent(repository, release_tag, *, runner=subprocess.run):
    """An authenticated repository read must succeed before either 404 is trusted."""
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository):
        raise DistributionError("Invalid repository identity")
    if not isinstance(release_tag, str) or not re.fullmatch(r"codegen-models-v[1-9][0-9]*", release_tag):
        raise DistributionError("Invalid model release tag")
    status, info = _github_get(f"repos/{repository}", runner)
    if status != 200 or not isinstance(info.get("full_name"), str) or info["full_name"].casefold() != repository.casefold():
        raise DistributionError("Repository access/identity was not established; refusing release preflight")
    for resource, label in ((f"releases/tags/{release_tag}", "release"), (f"git/ref/tags/{release_tag}", "tag")):
        status, _ = _github_get(f"repos/{repository}/{resource}", runner)
        if status == 200:
            raise DistributionError(f"The {label} already exists; immutable releases cannot be replaced")
        if status != 404:
            raise DistributionError("Release/tag absence was not established")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", nargs="?", type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--downloaded-release", action="store_true")
    parser.add_argument("--all-artifacts", action="store_true")
    parser.add_argument("--asset-list", type=Path)
    parser.add_argument("--expected-repository")
    parser.add_argument("--allow-test-models", action="store_true")
    parser.add_argument("--check-absent", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--release-tag")
    args = parser.parse_args(argv)
    try:
        if args.check_absent:
            if args.catalog or args.assets_dir or not args.repository or not args.release_tag:
                parser.error("--check-absent requires only --repository and --release-tag")
            check_remote_absent(args.repository, args.release_tag)
            print("Authenticated preflight confirmed that both release and tag are absent")
        else:
            if args.catalog is None or args.assets_dir is None:
                parser.error("catalog and --assets-dir are required")
            result = verify_release(args.catalog, args.assets_dir, signature_path=args.signature,
                                    downloaded_release=args.downloaded_release, all_artifacts=args.all_artifacts,
                                    expected_repository=args.expected_repository, allow_test_models=args.allow_test_models,
                                    asset_list=args.asset_list)
            print(json.dumps(result, sort_keys=True))
    except (DistributionError, OSError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
