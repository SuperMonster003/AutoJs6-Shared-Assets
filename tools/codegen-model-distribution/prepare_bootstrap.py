#!/usr/bin/env python3
"""Stage verified bootstrap resources; optionally install the reviewed pair into a host."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


def _crypto():
    key = "autojs6_codegen_crypto"
    path = Path(__file__).with_name("crypto.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("codegen crypto module belongs to another file")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


crypto = _crypto()
DistributionError = crypto.DistributionError
PUBLIC_KEY_RESOURCE = "codegen_model_catalog_public_key_v1.der"
CATALOG_RESOURCE = "codegen_model_catalog_v1.json"
CANONICAL_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"


def _is_host_resource_directory(directory: Path) -> bool:
    directory = directory.resolve()
    for possible_host in (directory, *directory.parents):
        if (possible_host / "app/build.gradle.kts").is_file() and (possible_host / "version.properties").is_file():
            resources = (possible_host / "app/src/main/res").resolve()
            if directory.is_relative_to(resources):
                return True
    return False


def _atomic_pair(directory: Path, contents: dict[str, bytes]) -> None:
    """Replace both files with rollback; retain backups if rollback itself is blocked.

    Each rename is atomic, but two independent paths are not a filesystem transaction.
    A crash between renames can leave a mismatched pair, which host verification rejects.
    """
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    targets = {name: directory / name for name in contents}
    for target in targets.values():
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise DistributionError("bootstrap targets must be regular files")
    temporary = Path(tempfile.mkdtemp(prefix=".codegen-bootstrap-", dir=directory))
    previous: set[str] = set()
    replaced: list[str] = []
    retain_backups = False
    try:
        for name, content in contents.items():
            with (temporary / name).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if targets[name].exists():
                shutil.copyfile(targets[name], temporary / ("old-" + name))
                previous.add(name)
        try:
            for name, target in targets.items():
                os.replace(temporary / name, target)
                replaced.append(name)
        except BaseException as error:
            failures: list[str] = []
            for name in reversed(replaced):
                try:
                    if name in previous:
                        os.replace(temporary / ("old-" + name), targets[name])
                    else:
                        targets[name].unlink(missing_ok=True)
                except OSError:
                    failures.append(name)
            if failures:
                retain_backups = True
                raise DistributionError(f"bootstrap rollback was blocked; recovery files retained at {temporary}") from error
            raise
    finally:
        if not retain_backups:
            # The only recursively removed directory is this freshly created private transaction.
            if temporary.parent.resolve() != directory or not temporary.name.startswith(".codegen-bootstrap-"):
                raise DistributionError("unexpected bootstrap temporary directory")
            shutil.rmtree(temporary)


def prepare_bootstrap(
    catalog_path: Path,
    signature_path: Path,
    public_key: Path,
    expected_key_id: str,
    output_directory: Path,
    *,
    host_root: Path | None = None,
    minimum_catalog_version: int = 1,
    openssl_value: str | None = None,
    allow_test_models: bool = False,
    expected_repository: str | None = None,
) -> dict[str, Any]:
    if _is_host_resource_directory(output_directory):
        raise DistributionError("stage outside host main resources; use --host-root for verified installation")
    if host_root is not None and allow_test_models:
        raise DistributionError("test-mode bootstrap material may only be staged, never installed into host resources")
    material = crypto.verify_catalog_material(catalog_path, signature_path, public_key, expected_key_id,
        minimum_catalog_version, openssl_value, allow_test_models=allow_test_models,
        expected_repository=expected_repository)
    destination: Path | None = None
    if host_root is not None:
        if material.catalog["repository"].casefold() != CANONICAL_REPOSITORY.casefold():
            raise DistributionError("host resources require the canonical official repository")
        host_root = host_root.resolve()
        if not (host_root / "app/build.gradle.kts").is_file() or not (host_root / "version.properties").is_file():
            raise DistributionError("--host-root must name an AutoJs6 host checkout")
        destination = host_root / "app/src/main/res/raw"
    # Catalog bytes are the immutable bytes that actually passed signature verification.
    envelope = {"format": 1, "catalogBase64": base64.b64encode(material.catalog_bytes).decode("ascii"), "signature": material.signature}
    contents = {
        PUBLIC_KEY_RESOURCE: material.public_der,
        CATALOG_RESOURCE: crypto.canonical_json_bytes(envelope),
    }
    inputs = {path.resolve() for path in (catalog_path, signature_path, public_key)}
    directories = [output_directory.resolve()] + ([destination.resolve()] if destination is not None else [])
    if any(directory / name in inputs for directory in directories for name in contents):
        raise DistributionError("bootstrap outputs must not overwrite signing inputs")
    _atomic_pair(output_directory, contents)
    if destination is not None and destination.resolve() != output_directory.resolve():
        _atomic_pair(destination, contents)
    return {
        "keyId": expected_key_id,
        "catalogVersion": material.catalog["catalogVersion"],
        "repository": material.catalog["repository"],
        "catalogSha256": hashlib.sha256(material.catalog_bytes).hexdigest(),
        "publicKeySha256": hashlib.sha256(material.public_der).hexdigest(),
        "outputDirectory": str(output_directory.resolve()),
        "installed": destination is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--expected-key-id", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--host-root", type=Path)
    parser.add_argument("--minimum-catalog-version", type=int, default=1)
    parser.add_argument("--expected-repository")
    parser.add_argument("--allow-test-models", action="store_true")
    parser.add_argument("--openssl")
    args = parser.parse_args()
    try:
        result = prepare_bootstrap(args.catalog, args.signature, args.public_key, args.expected_key_id, args.out_dir,
            host_root=args.host_root, minimum_catalog_version=args.minimum_catalog_version,
            openssl_value=args.openssl, allow_test_models=args.allow_test_models, expected_repository=args.expected_repository)
    except (DistributionError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Verified bootstrap staged at {result['outputDirectory']} with key {result['keyId']}")
    if result["installed"]:
        print("Installed the verified two-file resource pair into the host checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
