#!/usr/bin/env python3
"""Verify holiday-calendars release assets locally, or confirm remote tag and release absence.

Local verification (staged assets before upload, or a downloaded Release afterwards) checks that the
directory holds exactly the assets listed in release-assets.txt, each with the size and SHA-256 the
catalog records, plus, for a downloaded Release, the catalog and signature with the exact signed
bytes. Remote preflight is read-only and uses the GitHub CLI, which manages authentication without
forwarding tokens to catalog URLs.

Usage:
    python verify_release.py CATALOG --assets-dir DIR --asset-list release-assets.txt [--downloaded-release --signature SIG]
    python verify_release.py --check-absent --repository OWNER/REPO --release-tag holiday-calendars-vN
    python verify_release.py --verify-signature CATALOG --signature SIG --public-key PEM --expected-key-id ID
        [--expected-repository OWNER/REPO]   (signature only; for history catalogs whose data has moved on)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calendar_format import (  # noqa: E402
    CATALOG_NAME,
    MAX_CATALOG_BYTES,
    RELEASE_TAG_PATTERN,
    SIGNATURE_NAME,
    DistributionError,
    new_assets,
    read_json,
    validate_catalog,
)

REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def verify_release(catalog_path: Path, assets_dir: Path, asset_list: Path, *, signature_path: Path | None = None,
                   downloaded_release: bool = False) -> int:
    catalog, catalog_bytes = read_json(catalog_path, MAX_CATALOG_BYTES)
    validate_catalog(catalog)
    listed = asset_list.read_text(encoding="ascii").splitlines()
    if listed != new_assets(catalog):
        raise DistributionError("release-assets.txt differs from the assets this catalog introduces")
    expected = set(listed)
    if downloaded_release:
        if signature_path is None:
            raise DistributionError("a downloaded Release check needs the signature")
        expected |= {CATALOG_NAME, SIGNATURE_NAME}
        if (assets_dir / CATALOG_NAME).read_bytes() != catalog_bytes:
            raise DistributionError("the released catalog differs from the signed catalog")
        if (assets_dir / SIGNATURE_NAME).read_bytes() != signature_path.read_bytes():
            raise DistributionError("the released signature differs from the committed signature")
    present = {path.name for path in assets_dir.iterdir() if path.is_file()}
    if present != expected:
        raise DistributionError(f"asset set differs: extra {sorted(present - expected)}, missing {sorted(expected - present)}")
    entries = {region["file"]["name"]: region["file"] for region in catalog["regions"]}
    for name in listed:
        data = (assets_dir / name).read_bytes()
        entry = entries[name]
        if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise DistributionError(f"{name}: size or SHA-256 differs from the catalog")
    return len(listed)


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
    if not isinstance(repository, str) or REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise DistributionError("Invalid repository identity")
    if not isinstance(release_tag, str) or RELEASE_TAG_PATTERN.fullmatch(release_tag) is None:
        raise DistributionError("Invalid holiday calendar release tag")
    status, info = _github_get(f"repos/{repository}", runner)
    if status != 200 or not isinstance(info.get("full_name"), str) or info["full_name"].casefold() != repository.casefold():
        raise DistributionError("Repository access/identity was not established; refusing release preflight")
    for resource, label in ((f"releases/tags/{release_tag}", "release"), (f"git/ref/tags/{release_tag}", "tag")):
        status, _ = _github_get(f"repos/{repository}/{resource}", runner)
        if status == 200:
            raise DistributionError(f"The {label} already exists; immutable releases cannot be replaced")
        if status != 404:
            raise DistributionError("Release/tag absence was not established")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("catalog", nargs="?", type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--asset-list", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--downloaded-release", action="store_true")
    parser.add_argument("--check-absent", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--release-tag")
    parser.add_argument("--verify-signature", action="store_true")
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--expected-key-id")
    parser.add_argument("--expected-repository")
    parser.add_argument("--openssl")
    args = parser.parse_args(argv)
    try:
        if args.verify_signature:
            if args.catalog is None or args.signature is None or args.public_key is None or args.expected_key_id is None:
                parser.error("--verify-signature needs CATALOG, --signature, --public-key and --expected-key-id")
            import crypto  # noqa: PLC0415 - OpenSSL is needed only here
            verified = crypto.verify_catalog_material(args.catalog, args.signature, args.public_key, args.expected_key_id,
                                                      1, args.openssl, expected_repository=args.expected_repository)
            print(f"Verified the signature of {args.catalog} (catalogVersion {verified.catalog['catalogVersion']}, "
                  f"key {verified.signature['keyId']})")
            return 0
        if args.check_absent:
            check_remote_absent(args.repository, args.release_tag)
            print(f"Remote preflight: {args.release_tag} has neither a tag nor a Release in {args.repository}")
            return 0
        if args.catalog is None or args.assets_dir is None or args.asset_list is None:
            parser.error("local verification needs CATALOG, --assets-dir and --asset-list")
        count = verify_release(args.catalog, args.assets_dir, args.asset_list, signature_path=args.signature,
                               downloaded_release=args.downloaded_release)
    except (DistributionError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Verified {count} release assets" + (" with the released catalog and signature" if args.downloaded_release else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
