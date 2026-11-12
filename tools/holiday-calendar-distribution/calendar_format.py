"""Shared helpers for the holiday-calendars family.

This module has no third-party dependencies. It defines the byte-exact
serialization of calendar files and catalogs, strict JSON parsing and the
structural validation used by every tool in this directory.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
from pathlib import Path
from typing import Any

FAMILY = "holiday-calendars"
SCHEMA_VERSION = 1
CATALOG_NAME = f"catalog-v{SCHEMA_VERSION}.json"
SIGNATURE_NAME = f"catalog-v{SCHEMA_VERSION}.sig.json"
RELEASE_TAG_PREFIX = f"{FAMILY}-v"
DEFAULT_REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
ASSET_PREFIX = "holiday-calendar-"
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_CALENDAR_BYTES = 4 * 1024 * 1024
MAX_SIGNATURE_BYTES = 4096

REGION_PATTERN = re.compile(r"^[A-Z]{2}$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
MONTH_DAY_PATTERN = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RELEASE_TAG_PATTERN = re.compile(r"^holiday-calendars-v([1-9][0-9]*)$")
ASSET_NAME_PATTERN = re.compile(r"^holiday-calendar-([A-Z]{2})-([0-9a-f]{8})\.json$")
UPDATED_AT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FormatError(ValueError):
    """Raised when a calendar, catalog or signature violates the format."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FormatError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite(text):
    value = float(text)
    if not math.isfinite(value):
        raise FormatError("non-finite number")
    return value


def _constant(text):
    raise FormatError(f"invalid JSON constant: {text}")


def parse_json(data: bytes) -> dict:
    """Parse UTF-8 JSON strictly: no duplicate keys, no NaN, object root."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise FormatError("byte order mark is not allowed")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FormatError(f"not UTF-8: {error}") from None
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_float=_finite, parse_constant=_constant)
    except json.JSONDecodeError as error:
        raise FormatError(f"invalid JSON: {error}") from None
    if not isinstance(value, dict):
        raise FormatError("JSON root must be an object")
    return value


def read_json(path: Path, limit: int) -> tuple[dict, bytes]:
    data = Path(path).read_bytes()
    if len(data) > limit:
        raise FormatError(f"{path} is larger than {limit} bytes")
    return parse_json(data), data


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _layered(value: Any, depth: int, expand: int, indent: str = "  ") -> str:
    """Expand objects and arrays down to `expand` levels, compact below."""
    if depth >= expand or not isinstance(value, (dict, list)) or not value:
        return _compact(value)
    pad = indent * (depth + 1)
    if isinstance(value, dict):
        items = [f"{pad}{_compact(key)}: {_layered(value[key], depth + 1, expand, indent)}" for key in sorted(value)]
        return "{\n" + ",\n".join(items) + "\n" + indent * depth + "}"
    items = [f"{pad}{_layered(item, depth + 1, expand, indent)}" for item in value]
    return "[\n" + ",\n".join(items) + "\n" + indent * depth + "]"


def calendar_bytes(document: dict) -> bytes:
    """Serialize a calendar file: top level and its direct children one per line."""
    return (_layered(document, 0, 2) + "\n").encode("utf-8")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize catalogs, signatures and metadata (indent 2, sorted keys)."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FormatError(message)


def _require_keys(obj: Any, required: set[str], optional: set[str], where: str) -> None:
    _require(isinstance(obj, dict), f"{where} must be an object")
    keys = set(obj)
    missing = required - keys
    extra = keys - required - optional
    _require(not missing, f"{where} is missing {sorted(missing)}")
    _require(not extra, f"{where} has unknown keys {sorted(extra)}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_year_range(value: Any, where: str) -> tuple[int, int]:
    _require(isinstance(value, list) and len(value) == 2 and all(_is_int(item) for item in value),
             f"{where} must be [firstYear, lastYear]")
    first, last = value
    _require(1900 <= first <= last <= 2200, f"{where} is out of range: {value}")
    return first, last


def _require_date(year: int, month_day: Any, where: str) -> _dt.date:
    _require(isinstance(month_day, str) and MONTH_DAY_PATTERN.match(month_day) is not None,
             f"{where}: invalid MM-DD {month_day!r}")
    try:
        return _dt.date(year, int(month_day[:2]), int(month_day[3:]))
    except ValueError:
        raise FormatError(f"{where}: {year}-{month_day} is not a calendar date") from None


def _require_sorted_unique(values: list, where: str) -> None:
    _require(values == sorted(set(values)), f"{where} must be sorted and unique")


def _require_holiday_map(value: Any, year: int, name_count: int, where: str) -> None:
    _require(isinstance(value, dict), f"{where} must be an object")
    for month_day, indexes in value.items():
        _require_date(year, month_day, where)
        _require(isinstance(indexes, list) and indexes, f"{where}.{month_day} must be a non-empty array")
        for index in indexes:
            _require(_is_int(index) and 0 <= index < name_count, f"{where}.{month_day}: bad name index {index!r}")
        _require(len(set(indexes)) == len(indexes), f"{where}.{month_day}: repeated name index")


def validate_calendar(document: dict) -> None:
    """Validate a parsed calendar file (schema 1); raise FormatError on failure."""
    required = {"schemaVersion", "region", "name", "source", "years", "estimatedFrom", "weekend",
                "hasMakeupWorkdays", "defaultLanguage", "languages", "names", "calendar", "subdivisions"}
    _require_keys(document, required, set(), "calendar")
    _require(document["schemaVersion"] == SCHEMA_VERSION, "unsupported calendar schemaVersion")
    region = document["region"]
    _require(isinstance(region, str) and REGION_PATTERN.match(region) is not None, f"bad region {region!r}")
    _require(isinstance(document["name"], str) and document["name"].strip() == document["name"] != "",
             f"{region}: bad name")
    _require_keys(document["source"], {"name", "package", "version"}, set(), f"{region}.source")
    first, last = _require_year_range(document["years"], f"{region}.years")
    estimated = document["estimatedFrom"]
    _require(estimated is None or (_is_int(estimated) and first <= estimated <= last),
             f"{region}: bad estimatedFrom {estimated!r}")
    weekend = document["weekend"]
    _require(isinstance(weekend, list) and all(_is_int(day) and 1 <= day <= 7 for day in weekend),
             f"{region}: bad weekend")
    _require_sorted_unique(weekend, f"{region}.weekend")
    _require(len(weekend) < 7, f"{region}: weekend covers the whole week")
    _require(isinstance(document["hasMakeupWorkdays"], bool), f"{region}: bad hasMakeupWorkdays")
    languages = document["languages"]
    _require(isinstance(languages, list) and languages and
             all(isinstance(tag, str) and LANGUAGE_PATTERN.match(tag) for tag in languages),
             f"{region}: bad languages")
    _require_sorted_unique(languages, f"{region}.languages")
    _require(document["defaultLanguage"] in languages, f"{region}: defaultLanguage not in languages")
    names = document["names"]
    _require(isinstance(names, list), f"{region}.names must be an array")
    seen = set()
    for index, name in enumerate(names):
        where = f"{region}.names[{index}]"
        _require(isinstance(name, dict) and name, f"{where} must be a non-empty object")
        _require(document["defaultLanguage"] in name, f"{where} lacks the default language")
        for tag, text in name.items():
            _require(tag in languages, f"{where}: language {tag} not declared")
            _require(isinstance(text, str) and text.strip() == text != "", f"{where}.{tag}: bad text")
        key = tuple(sorted(name.items()))
        _require(key not in seen, f"{where} duplicates an earlier name")
        seen.add(key)
    calendar = document["calendar"]
    expected_years = [str(year) for year in range(first, last + 1)]
    _require(isinstance(calendar, dict) and sorted(calendar) == expected_years,
             f"{region}.calendar must contain exactly the years {first}-{last}")
    used = set()
    any_workday = False
    for year_text, entry in calendar.items():
        year = int(year_text)
        where = f"{region}.calendar.{year_text}"
        _require_keys(entry, {"holidays", "workdays"}, {"weekend"}, where)
        year_weekend = weekend
        if "weekend" in entry:
            year_weekend = entry["weekend"]
            _require(isinstance(year_weekend, list) and all(_is_int(day) and 1 <= day <= 7 for day in year_weekend),
                     f"{where}: bad weekend")
            _require_sorted_unique(year_weekend, f"{where}.weekend")
            _require(year_weekend != weekend and len(year_weekend) < 7, f"{where}: weekend must differ from the default")
        _require_holiday_map(entry["holidays"], year, len(names), f"{where}.holidays")
        for indexes in entry["holidays"].values():
            used.update(indexes)
        workdays = entry["workdays"]
        _require(isinstance(workdays, list), f"{where}.workdays must be an array")
        _require_sorted_unique(workdays, f"{where}.workdays")
        for month_day in workdays:
            date = _require_date(year, month_day, f"{where}.workdays")
            _require(date.isoweekday() in year_weekend, f"{where}: makeup workday {month_day} is not a weekend day")
            _require(month_day not in entry["holidays"], f"{where}: {month_day} is both holiday and workday")
        any_workday = any_workday or bool(workdays)
    _require(document["hasMakeupWorkdays"] == any_workday, f"{region}: hasMakeupWorkdays does not match data")
    subdivisions = document["subdivisions"]
    _require(isinstance(subdivisions, dict), f"{region}.subdivisions must be an object")
    for code, subdivision in subdivisions.items():
        where = f"{region}.subdivisions.{code}"
        _require(isinstance(code, str) and code.strip() == code != "" and "/" not in code, f"{where}: bad code")
        _require_keys(subdivision, {"name", "calendar"}, set(), where)
        _require(isinstance(subdivision["name"], str) and subdivision["name"].strip() == subdivision["name"] != "",
                 f"{where}: bad name")
        sub_calendar = subdivision["calendar"]
        _require(isinstance(sub_calendar, dict), f"{where}.calendar must be an object")
        for year_text, entry in sub_calendar.items():
            _require(year_text in calendar, f"{where}: year {year_text} outside the region range")
            year = int(year_text)
            entry_where = f"{where}.calendar.{year_text}"
            _require_keys(entry, set(), {"holidays", "removed", "weekend"}, entry_where)
            _require(entry, f"{entry_where} must not be empty")
            national = calendar[year_text]["holidays"]
            national_weekend = calendar[year_text].get("weekend", weekend)
            if "weekend" in entry:
                sub_weekend = entry["weekend"]
                _require(isinstance(sub_weekend, list) and all(_is_int(day) and 1 <= day <= 7 for day in sub_weekend),
                         f"{entry_where}: bad weekend")
                _require_sorted_unique(sub_weekend, f"{entry_where}.weekend")
                _require(sub_weekend != national_weekend and len(sub_weekend) < 7,
                         f"{entry_where}: weekend must differ from the national one")
                for month_day in calendar[year_text]["workdays"]:
                    _require(_require_date(year, month_day, entry_where).isoweekday() in sub_weekend,
                             f"{entry_where}: makeup workday {month_day} is not a weekend day here")
            if "holidays" in entry:
                _require(entry["holidays"], f"{entry_where}.holidays must not be empty")
                _require_holiday_map(entry["holidays"], year, len(names), f"{entry_where}.holidays")
                for month_day, indexes in entry["holidays"].items():
                    _require(national.get(month_day) != indexes, f"{entry_where}: {month_day} repeats the national entry")
                    used.update(indexes)
            if "removed" in entry:
                removed = entry["removed"]
                _require(isinstance(removed, list) and removed, f"{entry_where}.removed must be a non-empty array")
                _require_sorted_unique(removed, f"{entry_where}.removed")
                for month_day in removed:
                    _require(month_day in national, f"{entry_where}: removed {month_day} is not a national holiday")
                    _require(month_day not in entry.get("holidays", {}), f"{entry_where}: {month_day} removed and set")
    _require(used == set(range(len(names))), f"{region}: names table has unused entries")


def resolve_year(document: dict, year: int, subdivision: str | None = None) -> tuple[dict[str, list[int]], list[str], list[int]]:
    """Return (holidays, workdays, weekend) for a year, applying a subdivision overlay."""
    entry = document["calendar"].get(str(year))
    if entry is None:
        raise KeyError(year)
    holidays = dict(entry["holidays"])
    weekend = entry.get("weekend", document["weekend"])
    if subdivision is not None:
        overlay = document["subdivisions"][subdivision]["calendar"].get(str(year), {})
        for month_day in overlay.get("removed", []):
            del holidays[month_day]
        holidays.update(overlay.get("holidays", {}))
        weekend = overlay.get("weekend", weekend)
    return dict(sorted(holidays.items())), list(entry["workdays"]), list(weekend)


def is_day_off(document: dict, date: _dt.date, subdivision: str | None = None) -> bool:
    """A holiday, or a weekend day that is not a makeup workday."""
    holidays, workdays, weekend = resolve_year(document, date.year, subdivision)
    month_day = date.strftime("%m-%d")
    if month_day in holidays:
        return True
    return date.isoweekday() in weekend and month_day not in workdays


def asset_name(region: str, sha256: str) -> str:
    return f"{ASSET_PREFIX}{region}-{sha256[:8]}.json"


def release_tag(catalog_version: int) -> str:
    return f"{RELEASE_TAG_PREFIX}{catalog_version}"


def asset_url(repository: str, tag: str, name: str) -> str:
    return f"https://github.com/{repository}/releases/download/{tag}/{name}"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

DistributionError = FormatError
GENERATED_AT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CATALOG_KEYS = {"schemaVersion", "family", "catalogVersion", "generatedAt", "repository", "releaseTag",
                "source", "years", "regions"}
SOURCE_KEYS = {"name", "package", "version", "license", "homepage"}
REGION_KEYS = {"code", "name", "years", "estimatedFrom", "hasMakeupWorkdays", "subdivisions", "file"}
FILE_KEYS = {"name", "releaseTag", "sha256", "size", "url"}


def catalog_file(schema_version: Any) -> str:
    if schema_version != SCHEMA_VERSION:
        raise FormatError(f"unsupported catalog schemaVersion {schema_version!r}")
    return CATALOG_NAME


def tag_version(tag: Any) -> int:
    match = RELEASE_TAG_PATTERN.match(tag) if isinstance(tag, str) else None
    if match is None:
        raise FormatError(f"bad release tag {tag!r}")
    return int(match.group(1))


def validate_catalog(catalog: dict, minimum_version: int = 1, *, expected_repository: str | None = None) -> None:
    """Validate a parsed catalog on its own (history rules are in check_catalog_history)."""
    _require_keys(catalog, CATALOG_KEYS, set(), "catalog")
    _require(catalog["schemaVersion"] == SCHEMA_VERSION, "unsupported catalog schemaVersion")
    _require(catalog["family"] == FAMILY, "catalog family must be holiday-calendars")
    version = catalog["catalogVersion"]
    _require(_is_int(version) and version >= max(1, minimum_version),
             f"catalogVersion {version!r} is below the minimum {minimum_version}")
    _require(isinstance(catalog["generatedAt"], str) and GENERATED_AT_PATTERN.match(catalog["generatedAt"]) is not None,
             "generatedAt must look like 2026-11-12T00:00:00Z")
    repository = catalog["repository"]
    _require(isinstance(repository, str) and re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repository) is not None,
             "bad repository")
    if expected_repository is not None:
        _require(repository == expected_repository, f"catalog repository {repository} is not {expected_repository}")
    _require(catalog["releaseTag"] == release_tag(version), "releaseTag must be holiday-calendars-v<catalogVersion>")
    _require_keys(catalog["source"], SOURCE_KEYS, set(), "catalog.source")
    for key in SOURCE_KEYS:
        _require(isinstance(catalog["source"][key], str) and catalog["source"][key], f"catalog.source.{key} must be text")
    first, last = _require_year_range(catalog["years"], "catalog.years")
    regions = catalog["regions"]
    _require(isinstance(regions, list) and regions, "catalog.regions must be a non-empty array")
    codes = [region.get("code") if isinstance(region, dict) else None for region in regions]
    _require(all(isinstance(code, str) for code in codes) and codes == sorted(set(codes)),
             "catalog.regions must be sorted by unique code")
    names = set()
    for region in regions:
        code = region["code"]
        where = f"catalog.regions.{code}"
        _require_keys(region, REGION_KEYS, set(), where)
        _require(REGION_PATTERN.match(code) is not None, f"{where}: bad code")
        _require(isinstance(region["name"], str) and region["name"].strip() == region["name"] != "", f"{where}: bad name")
        region_first, region_last = _require_year_range(region["years"], f"{where}.years")
        _require(first <= region_first and region_last <= last, f"{where}: years outside the catalog range")
        estimated = region["estimatedFrom"]
        _require(estimated is None or (_is_int(estimated) and region_first <= estimated <= region_last),
                 f"{where}: bad estimatedFrom")
        _require(isinstance(region["hasMakeupWorkdays"], bool), f"{where}: bad hasMakeupWorkdays")
        subdivisions = region["subdivisions"]
        _require(isinstance(subdivisions, list), f"{where}.subdivisions must be an array")
        sub_codes = []
        for subdivision in subdivisions:
            _require_keys(subdivision, {"code", "name"}, set(), f"{where}.subdivisions[]")
            _require(all(isinstance(subdivision[key], str) and subdivision[key].strip() == subdivision[key] != ""
                         for key in ("code", "name")), f"{where}: bad subdivision")
            sub_codes.append(subdivision["code"])
        _require(sub_codes == sorted(set(sub_codes)), f"{where}.subdivisions must be sorted by unique code")
        entry = region["file"]
        _require_keys(entry, FILE_KEYS, set(), f"{where}.file")
        _require(isinstance(entry["sha256"], str) and SHA256_PATTERN.match(entry["sha256"]) is not None,
                 f"{where}.file: bad sha256")
        _require(_is_int(entry["size"]) and 0 < entry["size"] <= MAX_CALENDAR_BYTES, f"{where}.file: bad size")
        _require(entry["name"] == asset_name(code, entry["sha256"]), f"{where}.file: name must be {asset_name(code, entry['sha256'])}")
        _require(1 <= tag_version(entry["releaseTag"]) <= version, f"{where}.file: releaseTag is newer than the catalog")
        _require(entry["url"] == asset_url(repository, entry["releaseTag"], entry["name"]), f"{where}.file: bad url")
        _require(entry["name"] not in names, f"{where}.file: duplicate asset name")
        names.add(entry["name"])


def new_assets(catalog: dict) -> list[str]:
    """Asset names this catalog's release introduces (release-assets.txt order)."""
    return sorted(region["file"]["name"] for region in catalog["regions"] if region["file"]["releaseTag"] == catalog["releaseTag"])


def check_catalog_history(catalog: dict, previous: dict | None) -> None:
    """Rules between a catalog and the previously published one."""
    if previous is None:
        _require(catalog["catalogVersion"] == 1, "a catalog without a previous catalog must be version 1")
        _require(all(region["file"]["releaseTag"] == catalog["releaseTag"] for region in catalog["regions"]),
                 "the first catalog must introduce every file")
        return
    _require(catalog["catalogVersion"] == previous["catalogVersion"] + 1, "catalogVersion must increase by exactly one")
    _require(catalog["repository"] == previous["repository"], "repository changed")
    previous_files = {region["code"]: region["file"] for region in previous["regions"]}
    older_names = {entry["name"]: entry for entry in previous_files.values()}
    for region in catalog["regions"]:
        entry = region["file"]
        old = previous_files.get(region["code"])
        if entry["releaseTag"] == catalog["releaseTag"]:
            _require(old is None or old["sha256"] != entry["sha256"],
                     f"{region['code']}: unchanged data must keep the previous release asset")
            _require(entry["name"] not in older_names, f"{region['code']}: asset name already published")
        else:
            _require(old == entry, f"{region['code']}: an older asset entry must equal the previous catalog")


def summary_of(document: dict) -> dict:
    """The catalog fields that mirror a calendar file."""
    return {
        "code": document["region"],
        "name": document["name"],
        "years": document["years"],
        "estimatedFrom": document["estimatedFrom"],
        "hasMakeupWorkdays": document["hasMakeupWorkdays"],
        "subdivisions": [{"code": code, "name": value["name"]} for code, value in sorted(document["subdivisions"].items())],
    }
