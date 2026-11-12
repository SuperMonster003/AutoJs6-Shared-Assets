#!/usr/bin/env python3
"""Verify a holiday-calendars catalog against the data files.

Checks, each reported as PASS or FAIL:
  catalog      catalog structure, release tag, asset names and URLs
  history      rules against the previous catalog (with --previous-catalog)
  release      release-assets.txt equals the assets this catalog introduces (with --release-assets)
  signature    detached signature with the family public key (with --signature)
  data         every data file is valid, its size and SHA-256 match the catalog, summaries agree
  known-dates  spot checks of published dates from holiday-calendars/sources/known-dates.json
  sizes        size statistics (with --sizes; informational)

Exit status 0 only when every requested check passes.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calendar_format import (  # noqa: E402
    DEFAULT_REPOSITORY,
    MAX_CALENDAR_BYTES,
    MAX_CATALOG_BYTES,
    FormatError,
    check_catalog_history,
    is_day_off,
    new_assets,
    read_json,
    resolve_year,
    summary_of,
    validate_calendar,
    validate_catalog,
)


class CheckFailed(Exception):
    pass


def _dates(year: int, values: list[str]) -> list[_dt.date]:
    result = []
    for value in values:
        first, _, last = value.partition("/")
        start = _dt.date(year, int(first[:2]), int(first[3:]))
        end = _dt.date(year, int(last[:2]), int(last[3:])) if last else start
        if end < start:
            raise FormatError(f"bad range {value}")
        while start <= end:
            result.append(start)
            start += _dt.timedelta(days=1)
    return result


def load_documents(catalog: dict, data_dir: Path) -> dict[str, tuple[dict, bytes]]:
    documents = {}
    for region in catalog["regions"]:
        documents[region["code"]] = read_json(data_dir / f"{region['code']}.json", MAX_CALENDAR_BYTES)
    return documents


def check_data(catalog: dict, data_dir: Path, documents: dict[str, tuple[dict, bytes]]) -> str:
    present = {path.stem for path in data_dir.glob("*.json") if path.name != "generation.json"}
    expected = {region["code"] for region in catalog["regions"]}
    if present != expected:
        raise CheckFailed(f"data files and catalog regions differ: extra {sorted(present - expected)}, "
                          f"missing {sorted(expected - present)}")
    generation, _ = read_json(data_dir / "generation.json", 64 * 1024)
    if generation["source"]["version"] != catalog["source"]["version"] or generation["years"] != catalog["years"]:
        raise CheckFailed("generation.json does not match the catalog source or years")
    for region in catalog["regions"]:
        document, data = documents[region["code"]]
        validate_calendar(document)
        entry = region["file"]
        if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise CheckFailed(f"{region['code']}: size or SHA-256 differs from the catalog")
        expected_summary = dict(region)
        expected_summary.pop("file")
        if summary_of(document) != expected_summary:
            raise CheckFailed(f"{region['code']}: catalog summary differs from the data file")
        if document["source"]["version"] != catalog["source"]["version"]:
            raise CheckFailed(f"{region['code']}: generated from another package version")
    return f"{len(documents)} files, {sum(len(item[1]) for item in documents.values())} bytes"


def check_known_dates(path: Path, documents: dict[str, tuple[dict, bytes]]) -> str:
    known, _ = read_json(path, 256 * 1024)
    if known.get("schemaVersion") != 1:
        raise FormatError("unsupported known-dates file")
    failures = []
    count = 0
    for check in known["checks"]:
        region, _, subdivision = check["region"].partition("-")
        subdivision = subdivision or None
        year = check["year"]
        label = f"{check['region']} {year}"
        document = documents[region][0]
        holidays, workdays, _ = resolve_year(document, year, subdivision)
        for date in _dates(year, check.get("off", [])):
            count += 1
            if not is_day_off(document, date, subdivision):
                failures.append(f"{label}: {date} should be a day off")
        for date in _dates(year, check.get("on", [])):
            count += 1
            if is_day_off(document, date, subdivision):
                failures.append(f"{label}: {date} should be a working day")
        if "workdays" in check:
            count += 1
            if workdays != check["workdays"]:
                failures.append(f"{label}: makeup workdays {workdays} != {check['workdays']}")
        for month_day in check.get("holidays", []):
            count += 1
            if month_day not in holidays:
                failures.append(f"{label}: {month_day} should be a listed holiday")
        if check.get("exactHolidays"):
            count += 1
            extra = sorted(set(holidays) - set(check["holidays"]))
            if extra:
                failures.append(f"{label}: unexpected listed holidays {extra}")
        for month_day in check.get("notHolidays", []):
            count += 1
            if month_day in holidays:
                failures.append(f"{label}: {month_day} should not be a listed holiday")
    if failures:
        raise CheckFailed("; ".join(failures))
    return f"{len(known['checks'])} groups, {count} assertions"


def size_report(documents: dict[str, tuple[dict, bytes]]) -> list[str]:
    raw, packed = [], []
    total_raw = total_packed = 0
    for document, data in documents.values():
        years = document["years"][1] - document["years"][0] + 1
        compressed = len(gzip.compress(data, compresslevel=9, mtime=0))
        total_raw += len(data)
        total_packed += compressed
        raw.append(len(data) / years)
        packed.append(compressed / years)

    def triple(values):
        return f"{round(min(values))} / {round(statistics.median(values))} / {round(max(values))}"

    largest = max(documents.items(), key=lambda item: len(item[1][1]))
    return [
        f"total: {total_raw} bytes raw, {total_packed} bytes gzip -9 (per file)",
        f"per region and year, min / median / max: raw {triple(raw)} bytes, gzip {triple(packed)} bytes",
        f"largest file: {largest[0]} {len(largest[1][1])} bytes",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--release-assets", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--expected-key-id")
    parser.add_argument("--known-dates", type=Path)
    parser.add_argument("--expected-repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--first-release", action="store_true", help="assert there is no previous catalog (release 1)")
    parser.add_argument("--sizes", action="store_true")
    parser.add_argument("--openssl")
    args = parser.parse_args(argv)
    if args.signature is not None and (args.public_key is None or args.expected_key_id is None):
        parser.error("--signature needs --public-key and --expected-key-id")

    failed = False

    def run(name, action):
        nonlocal failed
        try:
            detail = action()
            print(f"PASS {name}" + (f": {detail}" if detail else ""))
            return True
        except (CheckFailed, FormatError, OSError, KeyError, ValueError) as error:
            print(f"FAIL {name}: {error}")
            failed = True
            return False

    state = {}

    def catalog_check():
        catalog, _ = read_json(args.catalog, MAX_CATALOG_BYTES)
        validate_catalog(catalog, expected_repository=args.expected_repository)
        state["catalog"] = catalog
        return (f"catalogVersion {catalog['catalogVersion']}, {len(catalog['regions'])} regions, "
                f"{catalog['source']['name']} {catalog['source']['version']}")

    if not run("catalog", catalog_check):
        return 1
    catalog = state["catalog"]
    if args.previous_catalog is not None or args.first_release:
        def history_check():
            previous = None
            if args.previous_catalog is not None:
                previous, _ = read_json(args.previous_catalog, MAX_CATALOG_BYTES)
                validate_catalog(previous, expected_repository=args.expected_repository)
            check_catalog_history(catalog, previous)
            return f"{len(new_assets(catalog))} new assets"
        run("history", history_check)
    if args.release_assets is not None:
        def release_check():
            listed = args.release_assets.read_text(encoding="ascii").splitlines()
            if listed != new_assets(catalog):
                raise CheckFailed("release-assets.txt differs from the assets this catalog introduces")
            return f"{len(listed)} assets"
        run("release", release_check)
    if args.signature is not None:
        def signature_check():
            import crypto  # noqa: PLC0415 - needs OpenSSL only when a signature is checked
            verified = crypto.verify_catalog_material(args.catalog, args.signature, args.public_key, args.expected_key_id,
                                                      1, args.openssl, expected_repository=args.expected_repository)
            return f"key {verified.signature['keyId']}"
        run("signature", signature_check)
    documents = {}

    def data_check():
        documents.update(load_documents(catalog, args.data_dir))
        return check_data(catalog, args.data_dir, documents)

    if run("data", data_check) and args.known_dates is not None:
        run("known-dates", lambda: check_known_dates(args.known_dates, documents))
    if args.sizes and documents:
        for line in size_report(documents):
            print(f"INFO sizes: {line}")
    print("result: " + ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
