#!/usr/bin/env python3
"""Detached ECDSA P-256/SHA-256 catalog signatures using the OpenSSL CLI."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from distribution import (
    DistributionError,
    canonical_json_bytes,
    read_json,
    validate_catalog,
)


ALGORITHM = "ECDSA_P256_SHA256"
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SIGNATURE_FIELDS = frozenset({"algorithm", "catalog", "keyId", "signature"})


def find_openssl(explicit: str | None = None) -> str:
    candidates: list[Path | str] = []
    if explicit:
        candidates.append(explicit)
    environment_value = os.environ.get("OPENSSL")
    if environment_value:
        candidates.append(environment_value)
    discovered = shutil.which("openssl")
    if discovered:
        candidates.append(discovered)
    git = shutil.which("git")
    if git and os.name == "nt":
        git_root = Path(git).resolve().parent.parent
        candidates.extend(
            [
                git_root / "mingw64" / "bin" / "openssl.exe",
                git_root / "usr" / "bin" / "openssl.exe",
            ]
        )
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(str(candidate))
        if resolved:
            return resolved
    raise DistributionError(
        "OpenSSL was not found; install it, set OPENSSL, or pass --openssl"
    )


def _run(command: list[str], *, sensitive: bool = False) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        detail = ""
        if not sensitive:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise DistributionError(f"OpenSSL command failed{suffix}")
    return result


def _is_der_public_key(key: Path) -> bool:
    return not key.read_bytes().lstrip().startswith(b"-----BEGIN")


def _assert_p256_key(openssl: str, key: Path, public: bool) -> None:
    command = [openssl, "pkey"]
    if public:
        command.append("-pubin")
        if _is_der_public_key(key):
            command.extend(["-inform", "DER"])
    command.extend(["-in", str(key), "-text_pub", "-noout"])
    result = _run(command, sensitive=not public)
    description = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if "prime256v1" not in description and "P-256" not in description:
        raise DistributionError("the signing key must use ECDSA P-256 (prime256v1)")


def sign_catalog(
    catalog_path: Path,
    private_key: Path,
    signature_path: Path,
    key_id: str,
    openssl_value: str | None = None,
) -> dict[str, Any]:
    if not KEY_ID_PATTERN.fullmatch(key_id):
        raise DistributionError("--key-id must contain only letters, digits, dot, dash, underscore")
    catalog_path = catalog_path.resolve()
    private_key = private_key.resolve()
    signature_path = signature_path.resolve()
    if signature_path in {catalog_path, private_key}:
        raise DistributionError("signature output must differ from the catalog and private key")
    if not private_key.is_file():
        raise DistributionError(f"private key does not exist: {private_key}")
    catalog = read_json(catalog_path)
    validate_catalog(catalog)
    openssl = find_openssl(openssl_value)
    _assert_p256_key(openssl, private_key, public=False)

    temporary = tempfile.NamedTemporaryFile(prefix="autojs6-font-signature-", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        _run(
            [
                openssl,
                "dgst",
                "-sha256",
                "-sign",
                str(private_key),
                "-out",
                str(temporary_path),
                str(catalog_path),
            ],
            sensitive=True,
        )
        signature = temporary_path.read_bytes()
    finally:
        temporary_path.unlink(missing_ok=True)
    if not signature:
        raise DistributionError("OpenSSL produced an empty signature")
    envelope = {
        "algorithm": ALGORITHM,
        "catalog": catalog_path.name,
        "keyId": key_id,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_bytes(canonical_json_bytes(envelope))
    return envelope


def generate_key_pair(
    private_key: Path,
    public_key_pem: Path,
    public_key_der: Path,
    openssl_value: str | None = None,
) -> str:
    """Generate a private P-256 key and X.509/SPKI public key encodings."""
    targets = [path.resolve() for path in (private_key, public_key_pem, public_key_der)]
    if len(set(targets)) != 3:
        raise DistributionError("private key and public key output paths must be distinct")
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise DistributionError("refusing to overwrite key file(s): " + ", ".join(existing))
    openssl = find_openssl(openssl_value)
    with tempfile.TemporaryDirectory(prefix="autojs6-font-keys-") as temporary_value:
        temporary = Path(temporary_value)
        private_temp = temporary / "private.pem"
        public_pem_temp = temporary / "public.pem"
        public_der_temp = temporary / "public.der"
        _run(
            [
                openssl,
                "genpkey",
                "-algorithm",
                "EC",
                "-pkeyopt",
                "ec_paramgen_curve:P-256",
                "-out",
                str(private_temp),
            ],
            sensitive=True,
        )
        _assert_p256_key(openssl, private_temp, public=False)
        _run(
            [
                openssl,
                "pkey",
                "-in",
                str(private_temp),
                "-pubout",
                "-out",
                str(public_pem_temp),
            ],
            sensitive=True,
        )
        _run(
            [
                openssl,
                "pkey",
                "-pubin",
                "-in",
                str(public_pem_temp),
                "-outform",
                "DER",
                "-out",
                str(public_der_temp),
            ]
        )
        _assert_p256_key(openssl, public_pem_temp, public=True)
        _assert_p256_key(openssl, public_der_temp, public=True)
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(private_temp, targets[0])
        try:
            os.chmod(targets[0], 0o600)
        except OSError:
            pass
        shutil.copyfile(public_pem_temp, targets[1])
        shutil.copyfile(public_der_temp, targets[2])
    fingerprint = hashlib.sha256(targets[2].read_bytes()).hexdigest()
    return f"p256-{fingerprint[:16]}"


def verify_catalog_signature(
    catalog_path: Path,
    signature_path: Path,
    public_key: Path,
    expected_key_id: str | None = None,
    minimum_catalog_version: int = 1,
    openssl_value: str | None = None,
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    signature_path = signature_path.resolve()
    public_key = public_key.resolve()
    catalog = read_json(catalog_path)
    validate_catalog(catalog, minimum_catalog_version)
    envelope = read_json(signature_path)
    if set(envelope) != SIGNATURE_FIELDS:
        raise DistributionError(
            "signature envelope must contain exactly algorithm, catalog, keyId, signature"
        )
    if envelope.get("algorithm") != ALGORITHM:
        raise DistributionError(f"signature algorithm must be {ALGORITHM}")
    if envelope.get("catalog") != catalog_path.name:
        raise DistributionError("signature envelope names a different catalog")
    key_id = envelope.get("keyId")
    if not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id):
        raise DistributionError("signature keyId is invalid")
    if expected_key_id is not None and key_id != expected_key_id:
        raise DistributionError(
            f"signature keyId {key_id!r} does not match expected {expected_key_id!r}"
        )
    signature_value = envelope.get("signature")
    if not isinstance(signature_value, str):
        raise DistributionError("signature value must be base64 text")
    try:
        signature = base64.b64decode(signature_value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise DistributionError("signature is not valid base64") from error
    if not signature:
        raise DistributionError("signature is empty")
    if not public_key.is_file():
        raise DistributionError(f"public key does not exist: {public_key}")
    openssl = find_openssl(openssl_value)
    _assert_p256_key(openssl, public_key, public=True)
    key_form_arguments = ["-keyform", "DER"] if _is_der_public_key(public_key) else []

    temporary = tempfile.NamedTemporaryFile(prefix="autojs6-font-signature-", delete=False)
    temporary_path = Path(temporary.name)
    try:
        temporary.write(signature)
        temporary.close()
        _run(
            [
                openssl,
                "dgst",
                "-sha256",
                "-verify",
                str(public_key),
                *key_form_arguments,
                "-signature",
                str(temporary_path),
                str(catalog_path),
            ]
        )
    finally:
        temporary.close()
        temporary_path.unlink(missing_ok=True)
    return envelope
