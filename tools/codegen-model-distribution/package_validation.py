"""Bounded model package checks, independent of the AutoJs6 host checkout."""

import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib
from datetime import datetime


MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_SCHEMA_BYTES = 256 * 1024
MAX_MODEL_BYTES = 32 + 4096 * (1 + 8 * 6 + 256 * 4)
ENTRY_NAMES = {"manifest.json", "model.bin", "features.json", "MODEL_CARD.md", "LICENSE"}
MODEL_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{1,63}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
NAME_HASH_PATTERN = re.compile(r"[0-9a-f]{16}")
TIMESTAMP_PATTERN = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9])"
    r"(?:\.([0-9]{1,9}))?(Z|[+-](?:0[0-9]|1[0-8]):[0-5][0-9])"
)


class PackageValidationError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageValidationError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise PackageValidationError("Non-finite JSON number")
    return number


def _constant(value):
    raise PackageValidationError("Non-finite JSON constant: " + value)


def parse_json(data):
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_float=_float, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise PackageValidationError("Invalid UTF-8 JSON: " + str(error)) from error
    if not isinstance(value, dict):
        raise PackageValidationError("JSON root must be an object")
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(required) - value.keys() or value.keys() - set(required) - set(optional):
        raise PackageValidationError("Missing or unknown object fields")


def integer(value, name, minimum=1, maximum=2**31 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PackageValidationError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def text(value, name, maximum=1024):
    try:
        valid = (isinstance(value, str) and value.strip() and len(value.encode("utf-16-le")) // 2 <= maximum
                 and not any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value))
    except UnicodeError:
        valid = False
    if not valid:
        raise PackageValidationError("Invalid bounded text: " + name)
    return value


def timestamp(value, name):
    text(value, name)
    matched = TIMESTAMP_PATTERN.fullmatch(value)
    if matched is None:
        raise PackageValidationError("Invalid calendar timestamp/precision: " + name)
    try:
        parsed = datetime.fromisoformat(matched[1] + matched[3].replace("Z", "+00:00"))
        offset = int(parsed.utcoffset().total_seconds())
        if abs(offset) > 18 * 3600:
            raise ValueError("offset exceeds 18 hours")
    except ValueError as error:
        raise PackageValidationError("Invalid offset timestamp: " + name) from error
    # Python datetime retains only microseconds; compare all nine digits without
    # rounding/truncation, including timestamps near a UTC year boundary.
    seconds = parsed.toordinal() * 86400 + parsed.hour * 3600 + parsed.minute * 60 + parsed.second - offset
    nanos = int((matched[2] or "").ljust(9, "0"))
    return seconds, nanos


def language_map(value, name, maximum=256):
    if not isinstance(value, dict) or "en" not in value or not 1 <= len(value) <= 64:
        raise PackageValidationError(name + " must contain an English translation")
    for language, content in value.items():
        if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language):
            raise PackageValidationError("Invalid language tag")
        text(content, name, maximum)


def metrics_summary(value):
    fields(value, ("test", "realTest"))
    for summary in value.values():
        fields(summary, ("groups", "top1Survival", "ruleTop1Survival", "regret"))
        groups = integer(summary["groups"], "metric groups", 0)
        for key in ("top1Survival", "ruleTop1Survival", "regret"):
            score = summary[key]
            if groups == 0:
                if score is not None:
                    raise PackageValidationError("Empty metric buckets must contain null scores")
            elif type(score) not in (int, float) or not 0 <= score <= 1 or not math.isfinite(score):
                raise PackageValidationError("Metric scores must be finite and within [0,1]")


def validate_manifest(manifest):
    fields(manifest, ("format", "modelId", "displayName", "versionCode", "versionName", "kind", "algorithm",
                      "featureSchemaVersion", "featureNamesHash", "model", "dataset", "metrics", "training",
                      "minHostVersionCode", "license", "publisher"))
    if type(manifest["format"]) is not int or manifest["format"] != 1:
        raise PackageValidationError("Unsupported model manifest format")
    if not MODEL_ID_PATTERN.fullmatch(text(manifest["modelId"], "modelId", 64)):
        raise PackageValidationError("Invalid modelId")
    language_map(manifest["displayName"], "displayName")
    for key in ("versionCode", "featureSchemaVersion", "minHostVersionCode"):
        integer(manifest[key], key)
    for key in ("versionName", "license", "publisher"):
        text(manifest[key], key, 256)
    if manifest["kind"] != "ranker" or manifest["algorithm"] != "catboost-oblivious":
        raise PackageValidationError("Unsupported model kind/algorithm")
    if not isinstance(manifest["featureNamesHash"], str) or not NAME_HASH_PATTERN.fullmatch(manifest["featureNamesHash"]):
        raise PackageValidationError("Invalid featureNamesHash")
    model = manifest["model"]
    fields(model, ("file", "size", "sha256", "trees", "depth", "features"))
    if model["file"] != "model.bin" or not isinstance(model["sha256"], str) or not SHA256_PATTERN.fullmatch(model["sha256"]):
        raise PackageValidationError("Invalid model file/hash")
    integer(model["size"], "model size", 32, MAX_MODEL_BYTES)
    integer(model["trees"], "trees", 1, 4096)
    integer(model["depth"], "depth", 1, 8)
    integer(model["features"], "features", 1, 65535)
    fields(manifest["dataset"], ("datasetId", "groups", "createdAt"))
    text(manifest["dataset"]["datasetId"], "datasetId")
    integer(manifest["dataset"]["groups"], "training groups")
    timestamp(manifest["dataset"]["createdAt"], "dataset.createdAt")
    metrics_summary(manifest["metrics"])
    fields(manifest["training"], ("catboostVersion", "pythonVersion", "hostCommit", "trainedAt"))
    text(manifest["training"]["catboostVersion"], "catboostVersion")
    text(manifest["training"]["pythonVersion"], "pythonVersion")
    if not re.fullmatch(r"[0-9a-f]{40}", text(manifest["training"]["hostCommit"], "hostCommit", 40)):
        raise PackageValidationError("Invalid hostCommit")
    timestamp(manifest["training"]["trainedAt"], "training.trainedAt")
    return manifest


def _binary(data):
    if not 32 <= len(data) <= MAX_MODEL_BYTES:
        raise PackageValidationError("Invalid binary size")
    magic, version, features, trees, bias, scale = struct.unpack_from("<4sHHIdd", data)
    if magic != b"AJCG" or version != 1:
        raise PackageValidationError("Invalid binary magic/version")
    integer(features, "binary features", 1, 65535)
    integer(trees, "binary trees", 1, 4096)
    if not math.isfinite(bias) or not math.isfinite(scale):
        raise PackageValidationError("Non-finite binary scale/bias")
    if struct.unpack_from("<I", data, len(data) - 4)[0] != zlib.crc32(data[:-4]) & 0xFFFFFFFF:
        raise PackageValidationError("Binary CRC32 mismatch")
    offset, maximum_depth = 28, 0
    for _ in range(trees):
        if offset >= len(data) - 4:
            raise PackageValidationError("Truncated binary tree")
        depth = integer(data[offset], "binary depth", 1, 8)
        offset += 1
        maximum_depth = max(maximum_depth, depth)
        if offset + depth * 6 + (1 << depth) * 4 > len(data) - 4:
            raise PackageValidationError("Truncated binary split/leaf array")
        for _ in range(depth):
            feature, border = struct.unpack_from("<Hf", data, offset)
            offset += 6
            if feature >= features or not math.isfinite(border):
                raise PackageValidationError("Invalid binary feature index/border")
        leaves = struct.unpack_from("<" + "f" * (1 << depth), data, offset)
        if any(not math.isfinite(leaf) for leaf in leaves):
            raise PackageValidationError("Non-finite binary leaf")
        offset += (1 << depth) * 4
    if offset != len(data) - 4:
        raise PackageValidationError("Binary length mismatch")
    return features, trees, maximum_depth


def _zip_slice(package, offset, count, end=None):
    boundary = len(package) if end is None else end
    if offset < 0 or count < 0 or offset + count > boundary:
        raise PackageValidationError("Truncated ZIP structure")
    return package[offset:offset + count]


def _zip_extra(extra):
    offset = 0
    while offset < len(extra):
        if offset + 4 > len(extra):
            raise PackageValidationError("Truncated ZIP extra field")
        tag, size = struct.unpack_from("<HH", extra, offset)
        if tag == 1:
            raise PackageValidationError("ZIP64 extra field is unsupported")
        offset += 4 + size
        if offset > len(extra):
            raise PackageValidationError("Truncated ZIP extra field value")


def _zip_directory(package):
    """Mirror the host's bounded directory/local-header checks, without recovery.

    zipfile deliberately adjusts central offsets to accept self-extracting ZIPs
    and trailing bytes. Packages use a narrower format: every byte before the
    central directory belongs to exactly one listed ordinary-file entry.
    """
    if len(package) < 22:
        raise PackageValidationError("Missing ZIP end record")
    end = None
    for offset in range(len(package) - 22, max(-1, len(package) - 65558), -1):
        if package[offset:offset + 4] == b"PK\x05\x06":
            comment_size = struct.unpack_from("<H", package, offset + 20)[0]
            if offset + 22 + comment_size == len(package):
                end = offset
                break
    if end is None:
        raise PackageValidationError("Missing or truncated ZIP end record; trailing bytes are forbidden")
    _, disk, directory_disk, disk_count, count, directory_size, directory_offset, _ = struct.unpack_from("<4sHHHHIIH", package, end)
    if disk != 0 or directory_disk != 0 or disk_count != count or count == 0xFFFF:
        raise PackageValidationError("Multi-disk ZIP and ZIP64 are unsupported")
    if count != len(ENTRY_NAMES):
        raise PackageValidationError("Package requires exactly the five allowed entry names")
    if directory_offset + directory_size != end:
        raise PackageValidationError("ZIP directory boundary mismatch")
    offset, names, entries = directory_offset, set(), []
    for _ in range(count):
        header = _zip_slice(package, offset, 46, end)
        if header[:4] != b"PK\x01\x02":
            raise PackageValidationError("Invalid ZIP central header")
        needed, flags, method = struct.unpack_from("<HHH", header, 6)
        crc, compressed, size = struct.unpack_from("<III", header, 16)
        name_size, extra_size, comment_size, entry_disk = struct.unpack_from("<HHHH", header, 28)
        attributes, local_offset = struct.unpack_from("<II", header, 38)
        if needed > 20 or flags & 0xF7F1 or method not in (0, 8) or entry_disk != 0:
            raise PackageValidationError("Encrypted, multi-disk, ZIP64, or unsupported ZIP entry")
        if 0xFFFFFFFF in (compressed, size, local_offset):
            raise PackageValidationError("ZIP64 is unsupported")
        offset += 46
        name_bytes = _zip_slice(package, offset, name_size, end)
        if any(value > 127 for value in name_bytes):
            raise PackageValidationError("ZIP entry names must use fixed ASCII names")
        name = name_bytes.decode("ascii")
        if name not in ENTRY_NAMES or name in names:
            raise PackageValidationError("Package requires exactly the five allowed entry names")
        names.add(name)
        kind = (attributes >> 16) & 0xF000
        if attributes & 0x10 or kind not in (0, 0x8000):
            raise PackageValidationError("ZIP directory, symbolic link, or non-regular entry is forbidden")
        limit = MAX_MODEL_BYTES if name == "model.bin" else MAX_SCHEMA_BYTES if name == "features.json" else MAX_TEXT_BYTES
        if not 0 < size <= limit or size > 200 * compressed:
            raise PackageValidationError("Invalid ZIP entry size or compression ratio")
        offset += name_size
        _zip_extra(_zip_slice(package, offset, extra_size, end))
        offset += extra_size
        _zip_slice(package, offset, comment_size, end)
        offset += comment_size
        entries.append({"name": name, "flags": flags, "method": method, "crc": crc,
                        "compressed": compressed, "size": size, "offset": local_offset})
    if offset != end or names != ENTRY_NAMES:
        raise PackageValidationError("Extra or missing ZIP central directory bytes")
    if sum(entry["size"] for entry in entries) > MAX_PACKAGE_BYTES:
        raise PackageValidationError("ZIP total uncompressed size exceeds 100 MiB")
    entries.sort(key=lambda entry: entry["offset"])
    expected = 0
    for entry in entries:
        if entry["offset"] != expected:
            raise PackageValidationError("ZIP local entry gap, overlap, prefix, or unlisted data")
        header = _zip_slice(package, expected, 30, directory_offset)
        magic, needed, flags, method, _, _, crc, compressed, size, name_size, extra_size = struct.unpack("<4sHHHHHIIIHH", header)
        if magic != b"PK\x03\x04" or needed > 20 or flags != entry["flags"] or method != entry["method"]:
            raise PackageValidationError("ZIP local header differs from directory")
        offset = expected + 30
        name_bytes = _zip_slice(package, offset, name_size, directory_offset)
        if name_bytes != entry["name"].encode("ascii"):
            raise PackageValidationError("ZIP local entry name differs from directory")
        offset += name_size
        _zip_extra(_zip_slice(package, offset, extra_size, directory_offset))
        offset += extra_size
        descriptor = flags & 8 != 0
        for actual, wanted in ((crc, entry["crc"]), (compressed, entry["compressed"]), (size, entry["size"])):
            if actual != wanted and not (descriptor and actual == 0):
                raise PackageValidationError("ZIP local sizes or CRC differ from directory")
        entry["dataOffset"] = offset
        expected = offset + entry["compressed"]
        if expected > directory_offset:
            raise PackageValidationError("ZIP entry data exceeds local area")
        if method == 0 and entry["compressed"] != entry["size"]:
            raise PackageValidationError("ZIP stored entry sizes disagree")
        if descriptor:
            first = struct.unpack("<I", _zip_slice(package, expected, 4, directory_offset))[0]
            expected += 4
            if first == 0x08074B50:
                first = struct.unpack("<I", _zip_slice(package, expected, 4, directory_offset))[0]
                expected += 4
            compressed, size = struct.unpack("<II", _zip_slice(package, expected, 8, directory_offset))
            expected += 8
            if (first, compressed, size) != (entry["crc"], entry["compressed"], entry["size"]):
                raise PackageValidationError("Invalid ZIP data descriptor")
    if expected != directory_offset:
        raise PackageValidationError("Unlisted bytes before ZIP central directory")
    return entries


def _zip_contents(package):
    entries = {}
    for entry in _zip_directory(package):
        payload = _zip_slice(package, entry["dataOffset"], entry["compressed"])
        if entry["method"] == 0:
            content = payload
        else:
            try:
                inflater = zlib.decompressobj(-zlib.MAX_WBITS)
                content = inflater.decompress(payload, entry["size"] + 1)
            except zlib.error as error:
                raise PackageValidationError("Invalid ZIP deflate stream") from error
            if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
                raise PackageValidationError("ZIP deflate stream does not exactly fill the declared entry")
        if len(content) != entry["size"]:
            raise PackageValidationError("ZIP decompressed size mismatch")
        if zlib.crc32(content) & 0xFFFFFFFF != entry["crc"]:
            raise PackageValidationError("ZIP entry CRC mismatch")
        entries[entry["name"]] = content
    return entries


def inspect_package(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size < MAX_PACKAGE_BYTES:
        raise PackageValidationError("Package must be a file strictly smaller than 100 MiB")
    with path.open("rb") as source:
        package = source.read(MAX_PACKAGE_BYTES)
    if len(package) >= MAX_PACKAGE_BYTES:
        raise PackageValidationError("Package must be strictly smaller than 100 MiB")
    entries = _zip_contents(package)
    manifest = validate_manifest(parse_json(entries["manifest.json"]))
    schema = parse_json(entries["features.json"])
    fields(schema, ("format", "featureSchemaVersion", "names", "namesHash"))
    if type(schema["format"]) is not int or schema["format"] != 1:
        raise PackageValidationError("Unsupported feature schema format")
    integer(schema["featureSchemaVersion"], "feature schema version")
    names = schema["names"]
    if (not isinstance(names, list) or not names or len(names) > 65535
            or any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in names)
            or len(set(names)) != len(names)):
        raise PackageValidationError("Invalid ordered feature names")
    names_hash = hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]
    if schema["namesHash"] != names_hash or manifest["featureNamesHash"] != names_hash or schema["featureSchemaVersion"] != manifest["featureSchemaVersion"]:
        raise PackageValidationError("Feature schema hash/version mismatch")
    binary = entries["model.bin"]
    features, trees, depth = _binary(binary)
    expected = manifest["model"]
    if (features != len(names) or (features, trees, depth) != (expected["features"], expected["trees"], expected["depth"])
            or len(binary) != expected["size"] or hashlib.sha256(binary).hexdigest() != expected["sha256"]):
        raise PackageValidationError("Binary model differs from manifest/schema")
    try:
        if not entries["MODEL_CARD.md"].decode("utf-8").strip() or not entries["LICENSE"].decode("utf-8").strip():
            raise PackageValidationError("Model card/license cannot be empty")
    except UnicodeError as error:
        raise PackageValidationError("Model card/license must be UTF-8") from error
    return {"manifest": manifest, "features": schema, "entries": entries, "size": len(package),
            "sha256": hashlib.sha256(package).hexdigest()}


def validate_package(path):
    return inspect_package(path)["manifest"]


def compare_release_version(manifest, model, version):
    if manifest["modelId"] != model["modelId"]:
        raise PackageValidationError("Package modelId differs from catalog")
    for field in ("versionCode", "versionName", "featureSchemaVersion", "featureNamesHash", "minHostVersionCode", "metrics"):
        if manifest[field] != version[field]:
            raise PackageValidationError("Package/catalog field mismatch: " + field)
    if manifest["dataset"]["datasetId"] != version["datasetId"] or manifest["license"] != version["license"]["spdx"]:
        raise PackageValidationError("Package/catalog dataset or license mismatch")
