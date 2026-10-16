"""Reviewed speech model sources, signed catalogs and content-addressed mirror archives.

Python 3.12 standard library only. Model binaries are never stored in Git: every source
records the upstream sherpa-onnx release assets, their SHA-256 digests and the members
that are repacked into one deterministic USTAR archive per model version. A version whose
source sets mirror to false is upstream-only: it keeps files[] and upstream[] but has no
archive, and the catalog records mirror as null for it.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit


DEFAULT_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
FAMILY_DIRECTORY = "speech-models"
CATALOG_FILE = "catalog-v1.json"
SIGNATURE_FILE = "catalog-v1.sig.json"
OUTPUT_MARKER = ".speech-model-distribution-output"
UPSTREAM_REPOSITORY = "k2-fsa/sherpa-onnx"

MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_SOURCE_JSON_BYTES = 4 * 1024 * 1024
MAX_SOURCE_TEXT_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 2**31 - 1
MAX_FILE_BYTES = 2**31 - 1
MAX_UPSTREAM_BYTES = 2**31 - 1
MAX_INSTALL_BYTES = 4 * 1024**3
MAX_FILES = 4096
MAX_MODELS = 1024
MAX_VERSIONS = 1024
MAX_UPSTREAM_PARTS = 8
MAX_PATH_LENGTH = 240
MAX_PATH_DEPTH = 12
BLOCK = 512

REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
RELEASE_TAG_PATTERN = re.compile(r"speech-models-v([1-9][0-9]{0,9})")
MODEL_ID_PATTERN = re.compile(r"(asr|kws|tts)\.[a-z0-9][a-z0-9._-]{1,59}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
LANGUAGE_PATTERN = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
MAP_LANGUAGE_PATTERN = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
NOTICE_KEY_PATTERN = re.compile(r"speech_model_license_[a-z0-9_]{1,40}")
SPDX_PATTERN = re.compile(r"[A-Za-z0-9.+-]+(?: (?:AND|OR|WITH) [A-Za-z0-9.+-]+)*")
SEMVER_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,3})\.(?:0|[1-9][0-9]{0,3})\.(?:0|[1-9][0-9]{0,3})")
PATH_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9_+!](?:[A-Za-z0-9 _.+!-]{0,126}[A-Za-z0-9_+!-])?")
UPSTREAM_TAG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
UPSTREAM_ASSET_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}")
VERSION_DIRECTORY_PATTERN = re.compile(r"[1-9][0-9]{0,9}")
LICENSE_FILE_PATTERN = re.compile(r"LICENSE(?:-[A-Za-z0-9._-]{1,64})?")
TIMESTAMP_PATTERN = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9])"
    r"(?:\.([0-9]{1,9}))?(Z|[+-](?:0[0-9]|1[0-8]):[0-5][0-9])"
)

KINDS = ("asr", "kws", "tts")
COMMERCIAL_USE_VALUES = (True, False, "unknown")
LIST_ROLES = frozenset({"lexicon", "ruleFsts", "ruleFars"})
DIRECTORY_ROLES = frozenset({"dataDir"})
VALUE_ROLES = {"modelType": ("zipformer", "zipformer2")}
TTS_OPTIONAL = ("lexicon", "ruleFsts", "ruleFars", "dataDir")
# Each modelType maps to one sherpa-onnx configuration family (sherpa-onnx 1.13.8 Kotlin API names).
MODEL_TYPES = {
    "online-transducer": {"kind": "asr", "required": ("encoder", "decoder", "joiner", "tokens", "modelType"), "optional": ("bpeVocab",)},
    "sense-voice": {"kind": "asr", "required": ("model", "tokens"), "optional": ()},
    "kws-transducer": {"kind": "kws", "required": ("encoder", "decoder", "joiner", "tokens", "modelType"), "optional": ("lexicon",)},
    "vits": {"kind": "tts", "required": ("model", "tokens"), "optional": TTS_OPTIONAL},
    "matcha": {"kind": "tts", "required": ("acousticModel", "vocoder", "tokens"), "optional": TTS_OPTIONAL},
    "kokoro": {"kind": "tts", "required": ("model", "voices", "tokens"), "optional": TTS_OPTIONAL},
}

SOURCE_REQUIRED = ("format", "modelId", "versionCode", "kind", "modelType", "displayName", "summary", "recommended",
                   "languages", "sampleRate", "releasedAt", "license", "runtime", "mirror", "upstream", "archive", "files")
FLAG_FIELDS = ("deprecated", "revoked")
SOURCE_OPTIONAL = ("speakers",) + FLAG_FIELDS
CATALOG_FIELDS = ("schemaVersion", "catalogVersion", "releaseTag", "generatedAt", "repository", "models")
MODEL_FIELDS = ("modelId", "kind", "displayName", "summary", "recommended", "versions", "recommendedVersionCode")
VERSION_REQUIRED = ("versionCode", "modelType", "languages", "sampleRate", "releasedAt", "license", "runtime",
                    "sourceUrl", "mirror", "upstream", "files")
VERSION_OPTIONAL = ("speakers",) + FLAG_FIELDS
LICENSE_FIELDS = ("spdx", "commercialUse", "noticeKey")
RUNTIME_FIELDS = ("minSherpaOnnx", "config")
MIRROR_FIELDS = ("fileName", "format", "size", "sha256", "url")
ARCHIVE_FIELDS = ("format", "size", "sha256")
FILE_FIELDS = ("path", "size", "sha256")
UPSTREAM_ARCHIVE_FIELDS = ("url", "size", "sha256", "format", "members")
UPSTREAM_FILE_FIELDS = ("url", "size", "sha256", "format", "path")


class DistributionError(ValueError):
    """A validation failure that can be shown without a Python traceback."""


# JSON ----------------------------------------------------------------------------------------

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DistributionError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise DistributionError("Non-finite JSON number")
    return number


def _constant(value):
    raise DistributionError("Non-finite JSON constant: " + value)


def parse_json(data):
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_float=_finite, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, DistributionError):
            raise
        raise DistributionError("Invalid UTF-8 JSON: " + str(error)) from error
    if not isinstance(value, dict):
        raise DistributionError("JSON root must be an object")
    return value


def read_json(path, limit=MAX_CATALOG_BYTES):
    path = Path(path)
    try:
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
    except OSError as error:
        raise DistributionError(f"Cannot read JSON {path}: {error}") from error
    if len(content) > limit:
        raise DistributionError(f"JSON input exceeds the size limit: {path}")
    try:
        return parse_json(content)
    except DistributionError as error:
        raise DistributionError(f"Cannot read JSON {path}: {error}") from error


def canonical_json_bytes(value):
    try:
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise DistributionError("Cannot serialize finite UTF-8 JSON: " + str(error)) from error


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def sha256_file(path, expected_size=None):
    digest, total = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(block)
            if expected_size is not None and total > expected_size:
                raise DistributionError(f"File grew beyond its expected size: {path}")
            digest.update(block)
    if expected_size is not None and total != expected_size:
        raise DistributionError(f"File size differs from the expected size: {path}")
    return digest.hexdigest(), total


# Scalar validation ---------------------------------------------------------------------------

def fields(value, required, optional=(), name="object"):
    if not isinstance(value, dict):
        raise DistributionError(name + " must be an object")
    missing, unknown = set(required) - value.keys(), value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise DistributionError(f"{name} has missing fields {sorted(missing)} or unknown fields {sorted(unknown)}")
    return value


def integer(value, name, minimum=1, maximum=2**31 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DistributionError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise DistributionError(name + " must be a boolean")
    return value


def text(value, name, maximum=1024):
    valid = isinstance(value, str) and value.strip() == value and value and len(value) <= maximum
    if not valid or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise DistributionError("Invalid bounded text: " + name)
    return value


def sha256_text(value, name):
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise DistributionError(name + " must be a lowercase SHA-256 digest")
    return value


def timestamp(value, name):
    text(value, name, 64)
    matched = TIMESTAMP_PATTERN.fullmatch(value)
    if matched is None:
        raise DistributionError("Invalid calendar timestamp: " + name)
    try:
        parsed = datetime.fromisoformat(matched[1] + matched[3].replace("Z", "+00:00"))
        offset = int(parsed.utcoffset().total_seconds())
        if abs(offset) > 18 * 3600:
            raise ValueError("offset exceeds 18 hours")
    except ValueError as error:
        raise DistributionError("Invalid offset timestamp: " + name) from error
    seconds = parsed.toordinal() * 86400 + parsed.hour * 3600 + parsed.minute * 60 + parsed.second - offset
    return seconds, int((matched[2] or "").ljust(9, "0"))


def language_map(value, name, maximum=256):
    if not isinstance(value, dict) or not {"en", "zh-CN"} <= value.keys() or len(value) > 64:
        raise DistributionError(name + " must contain at least en and zh-CN texts")
    for language, content in value.items():
        if MAP_LANGUAGE_PATTERN.fullmatch(language) is None:
            raise DistributionError("Invalid language tag in " + name)
        text(content, name, maximum)
    return value


def languages(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 32 or len(set(map(str, value))) != len(value):
        raise DistributionError("languages must be a nonempty array of distinct tags")
    for item in value:
        if not isinstance(item, str) or LANGUAGE_PATTERN.fullmatch(item) is None:
            raise DistributionError("Invalid recognition or synthesis language tag")
    return value


def repository_name(value):
    if not isinstance(value, str) or REPOSITORY_PATTERN.fullmatch(value) is None:
        raise DistributionError("repository must be a GitHub owner/repository name")
    return value


# Paths and the USTAR archive format ----------------------------------------------------------

def ustar_split(path):
    raw = path.encode("ascii")
    if len(raw) <= 100:
        return raw, b""
    for index, value in enumerate(raw):
        if value == 0x2F and len(raw) - index - 1 <= 100:
            if 0 < index <= 155:
                return raw[index + 1:], raw[:index]
            break
    raise DistributionError("Path cannot be stored in a USTAR header: " + path)


def install_path(value, name="path"):
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH or not value.isascii():
        raise DistributionError(f"Invalid {name}: must be bounded ASCII")
    segments = value.split("/")
    if len(segments) > MAX_PATH_DEPTH:
        raise DistributionError(f"Invalid {name}: too deep")
    for segment in segments:
        if segment in (".", "..") or PATH_SEGMENT_PATTERN.fullmatch(segment) is None:
            raise DistributionError(f"Invalid {name} segment in {value!r}")
    ustar_split(value)
    return value


def _octal(value, width):
    encoded = b"%0*o" % (width - 1, value)
    if len(encoded) != width - 1:
        raise DistributionError("Value does not fit in a USTAR field")
    return encoded + b"\0"


def tar_header(path, size):
    """One canonical USTAR header: mode 0644, uid/gid 0, mtime 0, empty owner names."""
    integer(size, "archive member size", 0, MAX_FILE_BYTES)
    name, prefix = ustar_split(install_path(path))
    header = bytearray(BLOCK)
    header[0:len(name)] = name
    header[100:108] = _octal(0o644, 8)
    header[108:116] = _octal(0, 8)
    header[116:124] = _octal(0, 8)
    header[124:136] = _octal(size, 12)
    header[136:148] = _octal(0, 12)
    header[148:156] = b" " * 8
    header[156:157] = b"0"
    header[257:263] = b"ustar\0"
    header[263:265] = b"00"
    header[329:337] = _octal(0, 8)
    header[337:345] = _octal(0, 8)
    header[345:345 + len(prefix)] = prefix
    header[148:156] = b"%06o\0 " % sum(header)
    return bytes(header)


def padded(size):
    return -(-size // BLOCK) * BLOCK


def archive_size(sizes):
    return sum(BLOCK + padded(size) for size in sizes) + 2 * BLOCK


def archive_file_name(model_id, version_code, digest):
    return f"autojs6-speech-{model_id}-v{version_code}-{digest[:8]}.tar"


def write_archive(stream, entries):
    """Write sorted (path, size, open_function) entries and return (sha256, size)."""
    digest, total, previous = hashlib.sha256(), 0, None

    def emit(chunk):
        nonlocal total
        stream.write(chunk)
        digest.update(chunk)
        total += len(chunk)

    for path, size, opener in entries:
        if previous is not None and path <= previous:
            raise DistributionError("Archive entries must use ascending unique paths")
        previous = path
        emit(tar_header(path, size))
        remaining = size
        with opener() as source:
            while remaining:
                chunk = source.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise DistributionError("Archive member ended early: " + path)
                emit(chunk)
                remaining -= len(chunk)
            if source.read(1):
                raise DistributionError("Archive member grew while archiving: " + path)
        emit(b"\0" * (padded(size) - size))
    emit(b"\0" * (2 * BLOCK))
    return digest.hexdigest(), total


def _read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise DistributionError("Archive is truncated")
    return data


def read_archive(path, limit=MAX_ARCHIVE_BYTES):
    """Strictly parse a canonical archive and return [{path, size, sha256}] in archive order."""
    path = Path(path)
    if path.stat().st_size > limit:
        raise DistributionError("Archive exceeds its size limit")
    entries, previous = [], None
    with path.open("rb") as stream:
        while True:
            header = _read_exact(stream, BLOCK)
            if header == b"\0" * BLOCK:
                if _read_exact(stream, BLOCK) != b"\0" * BLOCK or stream.read(1):
                    raise DistributionError("Archive must end with exactly two zero blocks")
                return entries
            try:
                name = header[0:100].split(b"\0", 1)[0].decode("ascii")
                prefix = header[345:500].split(b"\0", 1)[0].decode("ascii")
                size = int(header[124:135].decode("ascii"), 8)
            except (UnicodeError, ValueError) as error:
                raise DistributionError("Archive header is not canonical") from error
            member = prefix + "/" + name if prefix else name
            if header != tar_header(member, size):
                raise DistributionError("Archive header is not canonical: " + member)
            if previous is not None and member <= previous:
                raise DistributionError("Archive members are not in ascending path order")
            previous = member
            digest, remaining = hashlib.sha256(), size
            while remaining:
                chunk = _read_exact(stream, min(remaining, 1024 * 1024))
                digest.update(chunk)
                remaining -= len(chunk)
            if _read_exact(stream, padded(size) - size).strip(b"\0"):
                raise DistributionError("Archive padding must be zero bytes")
            entries.append({"path": member, "size": size, "sha256": digest.hexdigest()})
            if len(entries) > MAX_FILES:
                raise DistributionError("Archive contains too many files")


# Structured validation -----------------------------------------------------------------------

def validate_files(files):
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise DistributionError(f"files must be an array of 1..{MAX_FILES} entries")
    by_path, folded, directories, previous, total = {}, set(), set(), None, 0
    for item in files:
        fields(item, FILE_FIELDS, name="file")
        path = install_path(item["path"])
        integer(item["size"], "file size", 0, MAX_FILE_BYTES)
        sha256_text(item["sha256"], "file sha256")
        if previous is not None and path <= previous:
            raise DistributionError("files must use ascending unique path order")
        previous = path
        if path.casefold() in folded:
            raise DistributionError("files contain paths that differ only by case")
        folded.add(path.casefold())
        segments = path.casefold().split("/")
        directories.update("/".join(segments[:index]) for index in range(1, len(segments)))
        by_path[path] = item
        total += item["size"]
    if folded & directories:
        raise DistributionError("A file path is also used as a directory")
    if total > MAX_INSTALL_BYTES:
        raise DistributionError("Installed files exceed the size limit")
    return by_path, {"/".join(path.split("/")[:index]) for path in by_path for index in range(1, path.count("/") + 1)}


def upstream_url(value, name="upstream url"):
    text(value, name, 2048)
    parsed = urlsplit(value)
    prefix = f"/{UPSTREAM_REPOSITORY}/releases/download/"
    parts = parsed.path[len(prefix):].split("/") if parsed.path.startswith(prefix) else []
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment or len(parts) != 2
            or UPSTREAM_TAG_PATTERN.fullmatch(parts[0]) is None or UPSTREAM_ASSET_PATTERN.fullmatch(parts[1]) is None):
        raise DistributionError("Upstream URLs must name a k2-fsa/sherpa-onnx GitHub release asset")
    return parts[0], parts[1]


def validate_upstream(parts, file_paths=None):
    """Return {installPath: (partIndex, member or None)}; file_paths, when given, must match exactly."""
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_UPSTREAM_PARTS:
        raise DistributionError("upstream must be an array of 1..8 release assets")
    mapping, assets = {}, set()
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or part.get("format") not in ("tar.bz2", "file"):
            raise DistributionError("upstream format must be tar.bz2 or file")
        archive = part["format"] == "tar.bz2"
        fields(part, UPSTREAM_ARCHIVE_FIELDS if archive else UPSTREAM_FILE_FIELDS, name="upstream asset")
        tag, asset = upstream_url(part["url"])
        if (tag, asset) in assets:
            raise DistributionError("Duplicate upstream release asset")
        assets.add((tag, asset))
        integer(part["size"], "upstream size", 1, MAX_UPSTREAM_BYTES)
        sha256_text(part["sha256"], "upstream sha256")
        if archive:
            members = part["members"]
            if not asset.endswith(".tar.bz2"):
                raise DistributionError("tar.bz2 upstream assets must use the .tar.bz2 extension")
            if not isinstance(members, dict) or not 1 <= len(members) <= MAX_FILES:
                raise DistributionError("upstream members must map 1..4096 archive members")
            pairs = [(install_path(member, "upstream member"), install_path(target)) for member, target in members.items()]
        else:
            pairs = [(None, install_path(part["path"]))]
        for member, target in pairs:
            if target in mapping:
                raise DistributionError("Two upstream members install the same path: " + target)
            mapping[target] = (index, member)
    if file_paths is not None and set(mapping) != set(file_paths):
        raise DistributionError("Upstream members must cover exactly the files array")
    return mapping


def validate_license(value):
    fields(value, LICENSE_FIELDS, name="license")
    if not isinstance(value["spdx"], str) or len(value["spdx"]) > 256 or SPDX_PATTERN.fullmatch(value["spdx"]) is None:
        raise DistributionError("license.spdx must be an SPDX expression of license IDs or LicenseRef identifiers")
    commercial = value["commercialUse"]
    if not any(type(commercial) is type(allowed) and commercial == allowed for allowed in COMMERCIAL_USE_VALUES):
        raise DistributionError('license.commercialUse must be true, false or "unknown"')
    if not isinstance(value["noticeKey"], str) or NOTICE_KEY_PATTERN.fullmatch(value["noticeKey"]) is None:
        raise DistributionError("license.noticeKey must match speech_model_license_*")
    return value


def validate_runtime(value, model_type, file_paths, directories):
    fields(value, RUNTIME_FIELDS, name="runtime")
    if not isinstance(value["minSherpaOnnx"], str) or SEMVER_PATTERN.fullmatch(value["minSherpaOnnx"]) is None:
        raise DistributionError("runtime.minSherpaOnnx must be a plain semantic version")
    specification = MODEL_TYPES[model_type]
    config = fields(value["config"], specification["required"], specification["optional"], name="runtime.config")
    for role, item in config.items():
        if role in VALUE_ROLES:
            if item not in VALUE_ROLES[role]:
                raise DistributionError(f"runtime.config.{role} has an unsupported value")
        elif role in LIST_ROLES:
            if (not isinstance(item, list) or not 1 <= len(item) <= 16 or len(set(map(str, item))) != len(item)
                    or any(path not in file_paths for path in item)):
                raise DistributionError(f"runtime.config.{role} must list distinct installed files")
        elif role in DIRECTORY_ROLES:
            if not isinstance(item, str) or item not in directories:
                raise DistributionError(f"runtime.config.{role} must name an installed directory")
        elif not isinstance(item, str) or item not in file_paths:
            raise DistributionError(f"runtime.config.{role} must name an installed file")
    return value


def _common_version(value, kind, file_paths, directories):
    model_type = value["modelType"]
    if model_type not in MODEL_TYPES or MODEL_TYPES[model_type]["kind"] != kind:
        raise DistributionError("modelType does not belong to the model kind")
    languages(value["languages"])
    integer(value["sampleRate"], "sampleRate", 8000, 192000)
    if kind == "tts":
        integer(value.get("speakers"), "speakers", 1, 100000)
    elif "speakers" in value:
        raise DistributionError("speakers is only valid for tts models")
    validate_license(value["license"])
    validate_runtime(value["runtime"], model_type, file_paths, directories)
    for flag in FLAG_FIELDS:
        if flag in value:
            boolean(value[flag], flag)


def validate_source(value, *, require_measured=True):
    fields(value, SOURCE_REQUIRED, SOURCE_OPTIONAL, name="source.json")
    if type(value["format"]) is not int or value["format"] != 1:
        raise DistributionError("Unsupported source.json format")
    model_id = value["modelId"]
    if not isinstance(model_id, str) or MODEL_ID_PATTERN.fullmatch(model_id) is None:
        raise DistributionError("Invalid modelId")
    kind = value["kind"]
    if kind not in KINDS or not model_id.startswith(kind + "."):
        raise DistributionError("modelId must start with its kind")
    integer(value["versionCode"], "versionCode")
    language_map(value["displayName"], "displayName")
    language_map(value["summary"], "summary", 1024)
    boolean(value["recommended"], "recommended")
    timestamp(value["releasedAt"], "releasedAt")
    mirrored = boolean(value["mirror"], "mirror")
    if not mirrored and value["archive"] is not None:
        raise DistributionError("archive must be null when mirror is false (upstream-only version)")
    if mirrored and (value["archive"] is None) != (value["files"] is None):
        raise DistributionError("archive and files must both be measured or both be null")
    if value["files"] is not None:
        by_path, directories = validate_files(value["files"])
        mapping = validate_upstream(value["upstream"], by_path)
        if mirrored:
            fields(value["archive"], ARCHIVE_FIELDS, name="archive")
            if value["archive"]["format"] != "tar":
                raise DistributionError("archive.format must be tar")
            integer(value["archive"]["size"], "archive size", 1, MAX_ARCHIVE_BYTES)
            sha256_text(value["archive"]["sha256"], "archive sha256")
            if value["archive"]["size"] != archive_size(item["size"] for item in value["files"]):
                raise DistributionError("archive.size differs from the canonical size of its files")
        for target, (index, member) in mapping.items():
            if member is None and (by_path[target]["size"], by_path[target]["sha256"]) != (
                    value["upstream"][index]["size"], value["upstream"][index]["sha256"]):
                raise DistributionError("A raw upstream file differs from its installed file record")
    elif require_measured:
        raise DistributionError("source.json has no measured files; run prepare_sources.py --update-sources")
    else:
        mapping = validate_upstream(value["upstream"])
        by_path = dict.fromkeys(mapping)
        directories = {"/".join(path.split("/")[:index]) for path in by_path for index in range(1, path.count("/") + 1)}
        validate_files([{"path": path, "size": 0, "sha256": "0" * 64} for path in sorted(by_path)])
    _common_version(value, kind, by_path, directories)
    return value


def release_url(repository, release_tag, file_name):
    return f"https://github.com/{repository}/releases/download/{release_tag}/{file_name}"


def source_url(repository, release_tag, model_id, version_code):
    return f"https://github.com/{repository}/tree/{release_tag}/{FAMILY_DIRECTORY}/sources/{model_id}/{version_code}"


def _release_number(tag):
    matched = RELEASE_TAG_PATTERN.fullmatch(tag)
    if matched is None:
        raise DistributionError("Invalid speech-models release tag")
    return int(matched.group(1))


def _validate_catalog_version(item, model, repository, catalog_version, generated):
    fields(item, VERSION_REQUIRED, VERSION_OPTIONAL, name="catalog version")
    code = integer(item["versionCode"], "versionCode")
    by_path, directories = validate_files(item["files"])
    validate_upstream(item["upstream"], by_path)
    _common_version(item, model["kind"], by_path, directories)
    if timestamp(item["releasedAt"], "releasedAt") > generated:
        raise DistributionError("releasedAt cannot be later than the catalog generatedAt")
    if item["mirror"] is None:
        # Upstream-only version: no release archive; files[] are installed from upstream[] alone.
        prefix = f"https://github.com/{repository}/tree/"
        url = item["sourceUrl"]
        tag = url[len(prefix):].split("/", 1)[0] if isinstance(url, str) and url.startswith(prefix) else ""
        if not RELEASE_TAG_PATTERN.fullmatch(tag) or url != source_url(repository, tag, model["modelId"], code):
            raise DistributionError("sourceUrl of an upstream-only version must name its source directory at a release tag")
        if _release_number(tag) > catalog_version:
            raise DistributionError("sourceUrl cannot use a later release than the catalog")
        return code, None
    mirror = fields(item["mirror"], MIRROR_FIELDS, name="mirror")
    if mirror["format"] != "tar":
        raise DistributionError("mirror.format must be tar")
    integer(mirror["size"], "mirror size", 1, MAX_ARCHIVE_BYTES)
    sha256_text(mirror["sha256"], "mirror sha256")
    if mirror["size"] != archive_size(entry["size"] for entry in item["files"]):
        raise DistributionError("mirror.size differs from the canonical size of its files")
    expected_name = archive_file_name(model["modelId"], code, mirror["sha256"])
    if mirror["fileName"] != expected_name:
        raise DistributionError("mirror.fileName must be content addressed")
    text(mirror["url"], "mirror url", 2048)
    prefix = f"https://github.com/{repository}/releases/download/"
    tag = mirror["url"][len(prefix):].split("/", 1)[0] if mirror["url"].startswith(prefix) else ""
    if not RELEASE_TAG_PATTERN.fullmatch(tag) or mirror["url"] != release_url(repository, tag, expected_name):
        raise DistributionError("mirror.url must name this repository's release asset")
    if _release_number(tag) > catalog_version:
        raise DistributionError("mirror.url cannot use a later release than the catalog")
    if item["sourceUrl"] != source_url(repository, tag, model["modelId"], code):
        raise DistributionError("sourceUrl must use the release tag that introduced the mirror archive")
    return code, expected_name


def _versions(catalog):
    return {(model["modelId"], version["versionCode"]): version for model in catalog["models"] for version in model["versions"]}


def _immutable(version):
    return {key: value for key, value in version.items() if key not in FLAG_FIELDS}


def validate_catalog(catalog, minimum_catalog_version=1, *, previous_catalog=None, expected_repository=None):
    fields(catalog, CATALOG_FIELDS, name="catalog")
    if type(catalog["schemaVersion"]) is not int or catalog["schemaVersion"] != 1:
        raise DistributionError("Unsupported catalog schemaVersion")
    integer(minimum_catalog_version, "minimum catalog version")
    version = integer(catalog["catalogVersion"], "catalogVersion", minimum_catalog_version)
    if catalog["releaseTag"] != f"speech-models-v{version}":
        raise DistributionError("releaseTag must match catalogVersion")
    generated = timestamp(catalog["generatedAt"], "generatedAt")
    repository = repository_name(catalog["repository"])
    if expected_repository is not None and repository != expected_repository:
        raise DistributionError("Catalog repository differs from the expected repository")
    models = catalog["models"]
    if not isinstance(models, list) or len(models) > MAX_MODELS:
        raise DistributionError("models must be a bounded array")
    model_ids, artifacts = [], set()
    for model in models:
        fields(model, MODEL_FIELDS, name="model")
        model_id = model["modelId"]
        if not isinstance(model_id, str) or MODEL_ID_PATTERN.fullmatch(model_id) is None:
            raise DistributionError("Invalid modelId")
        if model["kind"] not in KINDS or not model_id.startswith(model["kind"] + "."):
            raise DistributionError("modelId must start with its kind")
        model_ids.append(model_id)
        language_map(model["displayName"], "displayName")
        language_map(model["summary"], "summary", 1024)
        boolean(model["recommended"], "recommended")
        if not isinstance(model["versions"], list) or not 1 <= len(model["versions"]) <= MAX_VERSIONS:
            raise DistributionError("Model versions must be a nonempty bounded array")
        codes, eligible = [], []
        for item in model["versions"]:
            code, artifact = _validate_catalog_version(item, model, repository, version, generated)
            if artifact is not None:
                if artifact in artifacts:
                    raise DistributionError("Duplicate mirror archive")
                artifacts.add(artifact)
            codes.append(code)
            if not item.get("deprecated", False) and not item.get("revoked", False):
                eligible.append(code)
        if codes != sorted(set(codes)):
            raise DistributionError("Versions must use ascending unique versionCode order")
        recommended = model["recommendedVersionCode"]
        if recommended is not None:
            integer(recommended, "recommendedVersionCode")
        if recommended != (max(eligible) if eligible else None):
            raise DistributionError("recommendedVersionCode must be the latest active version or null")
    if model_ids != sorted(set(model_ids)):
        raise DistributionError("Models must use ascending unique modelId order")
    if len(canonical_json_bytes(catalog)) > MAX_CATALOG_BYTES:
        raise DistributionError("Catalog exceeds its byte-size limit")
    if previous_catalog is not None:
        validate_catalog(previous_catalog, expected_repository=repository)
        previous_version = previous_catalog["catalogVersion"]
        if version < previous_version:
            raise DistributionError("Catalog rollback is forbidden")
        if version == previous_version and canonical_json_bytes(catalog) != canonical_json_bytes(previous_catalog):
            raise DistributionError("Same catalogVersion has different content")
        if generated < timestamp(previous_catalog["generatedAt"], "previous generatedAt"):
            raise DistributionError("Catalog generatedAt moved backwards")
        kinds = {model["modelId"]: model["kind"] for model in models}
        for model in previous_catalog["models"]:
            if kinds.get(model["modelId"], model["kind"]) != model["kind"]:
                raise DistributionError("A model cannot change its kind")
        current, previous = _versions(catalog), _versions(previous_catalog)
        for key, old in previous.items():
            if key not in current or _immutable(current[key]) != _immutable(old):
                raise DistributionError("Historical model version content changed or disappeared")
            for flag in FLAG_FIELDS:
                if old.get(flag, False) and not current[key].get(flag, False):
                    raise DistributionError("Historical " + flag + " status cannot be reversed")
        for key in current.keys() - previous.keys():
            earlier = [code for model_id, code in previous if model_id == key[0]]
            if earlier and key[1] <= max(earlier):
                raise DistributionError("New versions must exceed every previously recorded versionCode")
    return catalog


# Sources and catalog preparation -------------------------------------------------------------

def _source_text(path):
    try:
        if path.is_symlink() or not path.is_file():
            raise DistributionError("Source entries must be ordinary files: " + str(path))
        data = path.read_bytes()
    except OSError as error:
        raise DistributionError("Cannot read source file: " + str(path)) from error
    limit = MAX_SOURCE_JSON_BYTES if path.name == "source.json" else MAX_SOURCE_TEXT_BYTES
    if not data or len(data) > limit or b"\0" in data:
        raise DistributionError("Source files must be bounded nonempty text: " + str(path))
    try:
        data.decode("utf-8")
    except UnicodeError as error:
        raise DistributionError("Source files must be UTF-8 text: " + str(path)) from error
    return data


def load_sources(source_root, *, require_measured=True):
    """Return [(folder, source)] ordered by modelId and versionCode; binaries are refused."""
    source_root = Path(source_root)
    if not source_root.is_dir():
        raise DistributionError("Speech model source root is missing")
    root = source_root.resolve()
    result = []
    for model_dir in sorted(source_root.iterdir(), key=lambda item: item.name):
        if model_dir.is_symlink() or not model_dir.is_dir() or MODEL_ID_PATTERN.fullmatch(model_dir.name) is None:
            raise DistributionError("Unexpected entry in the source root: " + model_dir.name)
        version_dirs = sorted(model_dir.iterdir(), key=lambda item: item.name)
        if not version_dirs:
            raise DistributionError("Model source directory is empty: " + model_dir.name)
        codes = []
        for folder in version_dirs:
            if folder.is_symlink() or not folder.is_dir() or VERSION_DIRECTORY_PATTERN.fullmatch(folder.name) is None:
                raise DistributionError("Unexpected entry in a model source directory: " + str(folder))
            if not folder.resolve().is_relative_to(root):
                raise DistributionError("Source path escapes its root")
            names = {entry.name for entry in folder.iterdir()}
            licenses = {name for name in names if LICENSE_FILE_PATTERN.fullmatch(name)}
            unexpected = names - {"source.json", "MODEL_CARD.md"} - licenses
            if unexpected or "source.json" not in names or "MODEL_CARD.md" not in names or not licenses:
                raise DistributionError(f"{folder} must contain only source.json, MODEL_CARD.md and LICENSE files")
            for name in names:
                _source_text(folder / name)
            source = validate_source(read_json(folder / "source.json", MAX_SOURCE_JSON_BYTES), require_measured=require_measured)
            if source["modelId"] != model_dir.name or str(source["versionCode"]) != folder.name:
                raise DistributionError("source.json identity differs from its directory: " + str(folder))
            codes.append(source["versionCode"])
            result.append((folder, source))
        if len({result[-index - 1][1]["kind"] for index in range(len(codes))}) != 1:
            raise DistributionError("All versions of a model must share one kind")
    result.sort(key=lambda pair: (pair[1]["modelId"], pair[1]["versionCode"]))
    return result


def catalog_version_entry(source, repository, release_tag):
    mirror = None
    if source["mirror"]:
        file_name = archive_file_name(source["modelId"], source["versionCode"], source["archive"]["sha256"])
        mirror = {"fileName": file_name, "format": "tar", "size": source["archive"]["size"],
                  "sha256": source["archive"]["sha256"], "url": release_url(repository, release_tag, file_name)}
    entry = {
        "versionCode": source["versionCode"],
        "modelType": source["modelType"],
        "languages": deepcopy(source["languages"]),
        "sampleRate": source["sampleRate"],
        "releasedAt": source["releasedAt"],
        "license": deepcopy(source["license"]),
        "runtime": deepcopy(source["runtime"]),
        "sourceUrl": source_url(repository, release_tag, source["modelId"], source["versionCode"]),
        "mirror": mirror,
        "upstream": deepcopy(source["upstream"]),
        "files": deepcopy(source["files"]),
    }
    for optional in SOURCE_OPTIONAL:
        if optional in source:
            entry[optional] = source[optional]
    return entry


def _without_release_location(version):
    value = _immutable(version)
    value.pop("sourceUrl", None)
    if value["mirror"] is not None:
        value["mirror"] = {key: item for key, item in value["mirror"].items() if key != "url"}
    return value


def build_catalog(source_root, repository, catalog_version, generated_at, *, previous_catalog=None):
    """Return (catalog, newly introduced archive names); no network, no archive bytes needed."""
    repository = repository_name(repository)
    integer(catalog_version, "catalogVersion")
    timestamp(generated_at, "generatedAt")
    if previous_catalog is not None:
        validate_catalog(previous_catalog, expected_repository=repository)
        if catalog_version != previous_catalog["catalogVersion"] + 1:
            raise DistributionError("A new catalog must advance exactly one version beyond the previous catalog")
    elif catalog_version != 1:
        raise DistributionError("Catalog versions after v1 require the previous catalog")
    release_tag = f"speech-models-v{catalog_version}"
    old_versions = {} if previous_catalog is None else _versions(previous_catalog)
    models, new_assets, seen = {}, [], set()
    for _folder, source in load_sources(source_root):
        key = (source["modelId"], source["versionCode"])
        seen.add(key)
        entry = catalog_version_entry(source, repository, release_tag)
        if key in old_versions:
            old = old_versions[key]
            if _without_release_location(entry) != _without_release_location(old):
                raise DistributionError("A source attempts to change an immutable published version: " + "/".join(map(str, key)))
            carried = deepcopy(old)
            for flag in FLAG_FIELDS:
                if flag in source:
                    carried[flag] = source[flag]
            entry = carried
        elif entry["mirror"] is not None:
            new_assets.append(entry["mirror"]["fileName"])
        model = models.setdefault(source["modelId"], {"modelId": source["modelId"], "kind": source["kind"], "versions": []})
        model["versions"].append(entry)
        model.update(displayName=deepcopy(source["displayName"]), summary=deepcopy(source["summary"]),
                     recommended=source["recommended"])
    missing = set(old_versions) - seen
    if missing:
        raise DistributionError("Published versions lost their sources: " + ", ".join(f"{a}/{b}" for a, b in sorted(missing)))
    for model in models.values():
        active = [item["versionCode"] for item in model["versions"] if not item.get("deprecated") and not item.get("revoked")]
        model["recommendedVersionCode"] = max(active) if active else None
    if not models:
        raise DistributionError("No speech model sources were found")
    catalog = {"schemaVersion": 1, "catalogVersion": catalog_version, "releaseTag": release_tag, "generatedAt": generated_at,
               "repository": repository, "models": [models[key] for key in sorted(models)]}
    validate_catalog(catalog, previous_catalog=previous_catalog, expected_repository=repository)
    return catalog, sorted(new_assets)


def expected_release_assets(catalog, *, all_artifacts=False):
    """Map archive file names to (model, version) for the catalog's own release, or for every release.

    Upstream-only versions (mirror null) have no archive and are never listed.
    """
    result = {}
    for model in catalog["models"]:
        for version in model["versions"]:
            mirror = version["mirror"]
            if mirror is None:
                continue
            if all_artifacts or mirror["url"].split("/")[-2] == catalog["releaseTag"]:
                result[mirror["fileName"]] = (model, version)
    return result


def upstream_only_versions(catalog):
    """Return [(modelId, versionCode)] of the versions that are installed from upstream[] alone."""
    return [(model["modelId"], version["versionCode"]) for model in catalog["models"] for version in model["versions"]
            if version["mirror"] is None]
