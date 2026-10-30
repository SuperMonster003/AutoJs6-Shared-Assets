#!/usr/bin/env python3
"""Verify speech model release archives locally, or confirm remote tag and release absence.

Local verification checks every expected archive by name, size, SHA-256 and canonical USTAR
content against the catalog files[]. Remote preflight is read-only and uses the GitHub CLI,
which manages authentication without forwarding tokens to catalog URLs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
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


distribution = _module("distribution", "distribution.py")
DistributionError = distribution.DistributionError


def _same_bytes(actual_path, expected):
    if actual_path.stat().st_size != len(expected):
        return False
    with actual_path.open("rb") as source:
        return source.read(len(expected) + 1) == expected


def _companion(path, catalog, archives, expected_repository):
    """A catalog of an older schema published by the same release (decision D127), e.g. catalog-v2.json next to catalog-v3.json."""
    companion = distribution.read_json(path)
    distribution.validate_catalog(companion, expected_repository=expected_repository)
    if (companion["catalogVersion"], companion["releaseTag"]) != (catalog["catalogVersion"], catalog["releaseTag"]):
        raise DistributionError("A companion catalog must belong to the same release")
    if companion["schemaVersion"] >= catalog["schemaVersion"]:
        raise DistributionError("A companion catalog must use an older schema than the release catalog")
    if not set(distribution.expected_release_assets(companion)) <= archives:
        raise DistributionError("A companion catalog names archives that the release catalog does not")
    return companion


def verify_release(catalog_path, assets_dir, *, signature_path=None, downloaded_release=False, all_artifacts=False,
                   expected_repository=None, asset_list=None, companions=()):
    """companions: (catalog, signature) path pairs that a downloaded release also carries byte for byte."""
    catalog_path = Path(catalog_path).resolve()
    catalog = distribution.read_json(catalog_path)
    distribution.validate_catalog(catalog, expected_repository=expected_repository)
    assets_dir = Path(assets_dir).resolve()
    if not assets_dir.is_dir():
        raise DistributionError("Release asset directory does not exist")
    expected = distribution.expected_release_assets(catalog, all_artifacts=all_artifacts)
    names = set(expected)
    catalog_name = distribution.catalog_file(catalog["schemaVersion"])
    signature_name = distribution.signature_file(catalog["schemaVersion"])
    reviewed = {}
    if companions and not downloaded_release:
        raise DistributionError("Companion catalogs are verified only in a downloaded release")
    if downloaded_release:
        if signature_path is None:
            raise DistributionError("Downloaded-release verification requires the reviewed signature")
        reviewed = {catalog_name: catalog_path.read_bytes(), signature_name: Path(signature_path).read_bytes()}
        for companion_path, companion_signature in companions:
            schema = _companion(companion_path, catalog, set(distribution.expected_release_assets(catalog)), expected_repository)["schemaVersion"]
            if distribution.catalog_file(schema) in reviewed:
                raise DistributionError("Each companion catalog needs its own schema")
            reviewed[distribution.catalog_file(schema)] = Path(companion_path).read_bytes()
            reviewed[distribution.signature_file(schema)] = Path(companion_signature).read_bytes()
        names.update(reviewed)
    actual = {}
    for path in assets_dir.iterdir():
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(assets_dir):
            raise DistributionError("Release assets must be ordinary files directly inside the asset directory")
        actual[path.name] = path
    missing, unexpected = names - actual.keys(), actual.keys() - names
    if missing:
        raise DistributionError("Missing release assets: " + ", ".join(sorted(missing)))
    if unexpected:
        raise DistributionError("Unexpected release assets: " + ", ".join(sorted(unexpected)))
    for name, content in reviewed.items():
        if not _same_bytes(actual[name], content):
            kind = "signature" if name.endswith(".sig.json") else "catalog"
            raise DistributionError(f"Downloaded {kind} differs from the offline-reviewed {kind}: {name}")
    if asset_list is not None:
        entries = Path(asset_list).read_text(encoding="utf-8").splitlines()
        if len(entries) != len(set(entries)) or set(entries) != set(expected):
            raise DistributionError("release-assets.txt does not exactly cover the expected archives")
    total = 0
    for filename, (_model, version) in sorted(expected.items()):
        path, mirror = actual[filename], version["mirror"]
        if path.stat().st_size != mirror["size"]:
            raise DistributionError("Release archive size differs from the catalog: " + filename)
        digest, _ = distribution.sha256_file(path, mirror["size"])
        if digest != mirror["sha256"]:
            raise DistributionError("Release archive SHA-256 differs from the catalog: " + filename)
        if distribution.read_archive(path) != version["files"]:
            raise DistributionError("Release archive content differs from the catalog files: " + filename)
        total += mirror["size"]
    return {"releaseTag": catalog["releaseTag"], "archives": len(expected), "bytes": total,
            "downloadedRelease": downloaded_release, "allArtifacts": all_artifacts, "catalogs": sorted(reviewed)}


def _github_get(endpoint, runner):
    try:
        process = runner(["gh", "api", "--hostname", "github.com", "--method", "GET", "--include", endpoint],
                         capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise DistributionError("GitHub preflight request failed; absence was not established") from error
    # Never echo stdout/stderr on errors: credential helpers or proxies can include secrets.
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
    if not isinstance(repository, str) or distribution.REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise DistributionError("Invalid repository identity")
    if not isinstance(release_tag, str) or distribution.RELEASE_TAG_PATTERN.fullmatch(release_tag) is None:
        raise DistributionError("Invalid speech model release tag")
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
    parser.add_argument("--companion", nargs=2, type=Path, action="append", default=[], metavar=("CATALOG", "SIGNATURE"),
                        help="A same-release catalog of an older schema and its signature (downloaded release only)")
    parser.add_argument("--expected-repository")
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
                                    expected_repository=args.expected_repository, asset_list=args.asset_list,
                                    companions=[tuple(pair) for pair in args.companion])
            print(json.dumps(result, sort_keys=True))
    except (DistributionError, OSError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
