#!/usr/bin/env python3
"""Speech model catalogs signed with ECDSA P-256/SHA-256 in the Ace and codegen envelope format.

Adapted from ../codegen-model-distribution/crypto.py. The four-field signature envelope and the
OpenSSL digest operations are unchanged; catalog validation is local to this asset family, and
the Ace font and codegen model keys are refused as speech catalog keys.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


def _load_distribution():
    name = "autojs6_speech_distribution"
    path = Path(__file__).with_name("distribution.py").resolve()
    existing = sys.modules.get(name)
    if existing is not None:
        if Path(existing.__file__).resolve() != path:
            raise RuntimeError("speech distribution module name belongs to another file")
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


distribution = _load_distribution()
DistributionError = distribution.DistributionError
canonical_json_bytes = distribution.canonical_json_bytes
ALGORITHM = "ECDSA_P256_SHA256"
CATALOG_NAME = distribution.CATALOG_FILE
SIGNATURE_FIELDS = frozenset({"algorithm", "catalog", "keyId", "signature"})
KEY_ID_PATTERN = re.compile(r"^p256-[0-9a-f]{16}$")
MAX_CATALOG_BYTES = distribution.MAX_CATALOG_BYTES
MAX_SIGNATURE_BYTES = 64 * 1024
MAX_KEY_BYTES = 16 * 1024
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OTHER_FAMILY_KEYS = (REPOSITORY_ROOT / "ace-fonts/keys/catalog-signing-public.pem",
                     REPOSITORY_ROOT / "codegen-models/keys/catalog-signing-public.pem")
# Historical pins stay forbidden even if those repository keys later rotate.
FORBIDDEN_KEY_SHA256 = frozenset({
    "fc433f8ba81333f78c3b64ab4d29d52653f45d9073a1225c78c5e25608766214",  # Ace fonts
    "f1a540e052cf086520619e429cd3e3240fa3f8a4b8fca46e3531358906a67de3",  # codegen models
})


def find_openssl(explicit: str | None = None) -> str:
    candidates = [explicit] if explicit else [
        os.environ.get("OPENSSL"), shutil.which("openssl"),
        r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe" if os.name == "nt" else None,
    ]
    if not explicit and os.name == "nt" and (git := shutil.which("git")):
        root = Path(git).resolve().parent.parent
        candidates.extend([str(root / "mingw64/bin/openssl.exe"), str(root / "usr/bin/openssl.exe")])
    for candidate in candidates:
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_file():
                return str(path.resolve())
            if resolved := shutil.which(candidate):
                return resolved
    raise DistributionError("OpenSSL was not found; install it, set OPENSSL, or pass --openssl")


def _run(command: list[str], *, sensitive: bool = False) -> bytes:
    try:
        result = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DistributionError("OpenSSL could not complete the operation") from error
    if result.returncode:
        detail = "" if sensitive else result.stderr.decode("utf-8", errors="replace").strip()[:512]
        raise DistributionError("OpenSSL command failed" + (f": {detail}" if detail else ""))
    return result.stdout


def _bytes(path: Path, limit: int, description: str) -> bytes:
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise DistributionError(f"cannot read {description}: {path}") from error
    if len(data) > limit:
        raise DistributionError(f"{description} exceeds its size limit")
    return data


def assert_private_key_outside_git(path: Path) -> Path:
    """Resolve symlinks/junctions, including linked worktrees' .git files."""
    resolved = Path(path).expanduser().resolve()
    for directory in (resolved.parent, *resolved.parents):
        marker = directory / ".git"
        if marker.exists() or marker.is_symlink():
            raise DistributionError("private signing keys must remain outside every Git working tree")
    return resolved


def _key_is_der(path: Path) -> bool:
    return not _bytes(path, MAX_KEY_BYTES, "key").lstrip().startswith(b"-----BEGIN")


def _assert_p256(openssl: str, path: Path, *, public: bool) -> None:
    command = [openssl, "pkey"]
    if public:
        command.append("-pubin")
        if _key_is_der(path):
            command.extend(["-inform", "DER"])
    command.extend(["-in", str(path), "-text_pub", "-noout"])
    text = _run(command, sensitive=not public).decode("utf-8", errors="replace")
    if "prime256v1" not in text and "P-256" not in text:
        raise DistributionError("the signing key must use ECDSA P-256 (prime256v1)")


def pem_spki_sha256(path: Path) -> str:
    """SHA-256 of the SubjectPublicKeyInfo DER inside a PEM public key, without OpenSSL."""
    pem = _bytes(path, MAX_KEY_BYTES, "public key").decode("ascii")
    lines = [line.strip() for line in pem.strip().splitlines()]
    if not lines or lines[0] != "-----BEGIN PUBLIC KEY-----" or lines[-1] != "-----END PUBLIC KEY-----":
        raise DistributionError("expected one PEM PUBLIC KEY block")
    try:
        return hashlib.sha256(base64.b64decode("".join(lines[1:-1]), validate=True)).hexdigest()
    except (ValueError, binascii.Error) as error:
        raise DistributionError("PEM public key body is not valid base64") from error


def _assert_new_key(der: bytes) -> None:
    forbidden = set(FORBIDDEN_KEY_SHA256)
    for key in OTHER_FAMILY_KEYS:
        if key.is_file():
            forbidden.add(pem_spki_sha256(key))
    if hashlib.sha256(der).hexdigest() in forbidden:
        raise DistributionError("speech models require their own key; reusing the Ace or codegen catalog key is forbidden")


def public_key_der(public_key: Path, openssl_value: str | None = None) -> bytes:
    openssl = find_openssl(openssl_value)
    public_key = Path(public_key).resolve()
    _assert_p256(openssl, public_key, public=True)
    command = [openssl, "pkey", "-pubin", "-in", str(public_key)]
    der_input = _key_is_der(public_key)
    if der_input:
        command.extend(["-inform", "DER"])
    der = _run(command + ["-pubout", "-outform", "DER"])
    if der_input and der != _bytes(public_key, MAX_KEY_BYTES, "public key"):
        raise DistributionError("public DER must be exactly one canonical SPKI key")
    _assert_new_key(der)
    return der


def key_id_for_der(der: bytes) -> str:
    return "p256-" + hashlib.sha256(der).hexdigest()[:16]


def _require_key_id(value: str, der: bytes) -> None:
    if not isinstance(value, str) or not KEY_ID_PATTERN.fullmatch(value) or value != key_id_for_der(der):
        raise DistributionError("expected keyId must equal p256- followed by the SPKI SHA-256 prefix")


def _catalog(data: bytes, directory: Path, minimum_version: int, expected_repository: str | None) -> tuple[Path, dict[str, Any]]:
    path = directory / CATALOG_NAME
    path.write_bytes(data)
    parsed = distribution.read_json(path)
    distribution.validate_catalog(parsed, minimum_version, expected_repository=expected_repository)
    return path, parsed


def _signature_bytes(envelope: dict[str, Any], expected_key_id: str, der: bytes) -> bytes:
    if set(envelope) != SIGNATURE_FIELDS or envelope.get("algorithm") != ALGORITHM or envelope.get("catalog") != CATALOG_NAME:
        raise DistributionError("signature envelope must contain the fixed algorithm/catalog and exactly four fields")
    _require_key_id(expected_key_id, der)
    if envelope.get("keyId") != expected_key_id:
        raise DistributionError("signature keyId does not match the expected key")
    value = envelope.get("signature")
    if not isinstance(value, str) or len(value) > 128:
        raise DistributionError("signature must be bounded base64 text")
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise DistributionError("signature is not valid base64") from error
    if base64.b64encode(signature).decode("ascii") != value:
        raise DistributionError("signature base64 must be canonical")
    if not 8 <= len(signature) <= 72 or signature[0] != 0x30 or signature[1] != len(signature) - 2:
        raise DistributionError("signature must be one canonical DER ECDSA sequence")
    at = 2
    for _ in range(2):
        if at + 2 > len(signature) or signature[at] != 2:
            raise DistributionError("signature must contain two DER integers")
        size = signature[at + 1]
        at += 2
        integer = signature[at:at + size]
        if not 1 <= size <= 33 or len(integer) != size or integer[0] & 0x80 or (size > 1 and integer[0] == 0 and integer[1] < 0x80) or not any(integer):
            raise DistributionError("signature contains an invalid DER integer")
        at += size
    if at != len(signature):
        raise DistributionError("signature has trailing DER data")
    return signature


def _verify(openssl: str, directory: Path, catalog_path: Path, der: bytes, signature: bytes) -> None:
    key_path, signature_path = directory / "public.der", directory / "signature.der"
    key_path.write_bytes(der)
    signature_path.write_bytes(signature)
    _run([openssl, "dgst", "-sha256", "-verify", str(key_path), "-keyform", "DER", "-signature", str(signature_path), str(catalog_path)])


def _atomic_write(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise DistributionError("output may not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, value = tempfile.mkstemp(prefix=".speech-signature-", dir=path.parent)
    temporary = Path(value)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sign_catalog(catalog_path: Path, private_key: Path, signature_path: Path, key_id: str, openssl_value: str | None = None, *, expected_repository: str | None = None) -> dict[str, Any]:
    catalog_path, signature_path = Path(catalog_path), Path(signature_path)
    if catalog_path.name != CATALOG_NAME:
        raise DistributionError(f"catalog filename must be {CATALOG_NAME}")
    private_key = assert_private_key_outside_git(private_key)
    if signature_path.resolve() in {catalog_path.resolve(), private_key}:
        raise DistributionError("signature output must differ from the catalog and private key")
    data = _bytes(catalog_path, MAX_CATALOG_BYTES, "catalog")
    _bytes(private_key, MAX_KEY_BYTES, "private key")
    openssl = find_openssl(openssl_value)
    _assert_p256(openssl, private_key, public=False)
    with tempfile.TemporaryDirectory(prefix="autojs6-speech-sign-") as value:
        directory = Path(value)
        snapshot, _ = _catalog(data, directory, 1, expected_repository)
        pem = directory / "public.pem"
        _run([openssl, "pkey", "-in", str(private_key), "-pubout", "-out", str(pem)], sensitive=True)
        der = public_key_der(pem, openssl)
        _require_key_id(key_id, der)
        signature_path_temp = directory / "signature.der"
        _run([openssl, "dgst", "-sha256", "-sign", str(private_key), "-out", str(signature_path_temp), str(snapshot)], sensitive=True)
        signature = _bytes(signature_path_temp, 128, "signature")
        envelope = {"algorithm": ALGORITHM, "catalog": CATALOG_NAME, "keyId": key_id, "signature": base64.b64encode(signature).decode("ascii")}
        _verify(openssl, directory, snapshot, der, _signature_bytes(envelope, key_id, der))
    if _bytes(catalog_path, MAX_CATALOG_BYTES, "catalog") != data:
        raise DistributionError("catalog changed while signing; no signature was written")
    _atomic_write(signature_path, canonical_json_bytes(envelope))
    return envelope


@dataclass(frozen=True)
class VerifiedCatalog:
    catalog_bytes: bytes
    catalog: dict[str, Any]
    signature: dict[str, Any]
    public_der: bytes


def verify_catalog_material(catalog_path: Path, signature_path: Path, public_key: Path, expected_key_id: str, minimum_catalog_version: int = 1, openssl_value: str | None = None, *, expected_repository: str | None = None) -> VerifiedCatalog:
    catalog_path = Path(catalog_path)
    if catalog_path.name != CATALOG_NAME:
        raise DistributionError(f"catalog filename must be {CATALOG_NAME}")
    data = _bytes(catalog_path, MAX_CATALOG_BYTES, "catalog")
    signature_data = _bytes(signature_path, MAX_SIGNATURE_BYTES, "signature envelope")
    openssl = find_openssl(openssl_value)
    der = public_key_der(public_key, openssl)
    _require_key_id(expected_key_id, der)
    with tempfile.TemporaryDirectory(prefix="autojs6-speech-verify-") as value:
        directory = Path(value)
        snapshot, catalog = _catalog(data, directory, minimum_catalog_version, expected_repository)
        envelope = distribution.parse_json(signature_data)
        signature = _signature_bytes(envelope, expected_key_id, der)
        _verify(openssl, directory, snapshot, der, signature)
    return VerifiedCatalog(data, catalog, envelope, der)


def generate_key_pair(private_key: Path, public_key_pem: Path, public_key_der_path: Path, openssl_value: str | None = None) -> str:
    """Test and rotation helper; the production key was generated offline on 2026-10-16."""
    paths = (Path(private_key), Path(public_key_pem), Path(public_key_der_path))
    if any(path.exists() or path.is_symlink() for path in paths):
        raise DistributionError("refusing to overwrite an existing key file")
    targets = [path.expanduser().resolve() for path in paths]
    if len(set(targets)) != 3:
        raise DistributionError("private key and public key output paths must be distinct")
    assert_private_key_outside_git(targets[0])
    openssl = find_openssl(openssl_value)
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autojs6-speech-keys-", dir=targets[0].parent) as value:
        temporary = Path(value)
        secret, pem = temporary / "private.pem", temporary / "public.pem"
        _run([openssl, "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(secret)], sensitive=True)
        _run([openssl, "pkey", "-in", str(secret), "-pubout", "-out", str(pem)], sensitive=True)
        der = public_key_der(pem, openssl)
        created = []
        try:
            for index, (target, data) in enumerate(zip(targets, (secret.read_bytes(), pem.read_bytes(), der))):
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if index == 0 else 0o644)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                created.append(target)
        except OSError:
            for target in created:
                target.unlink(missing_ok=True)
            raise
    return key_id_for_der(der)
