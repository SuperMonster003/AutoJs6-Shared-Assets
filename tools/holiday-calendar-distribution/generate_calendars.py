"""Generate holiday-calendars data files from python-holidays.

Usage:
    python generate_calendars.py --config holiday-calendars/sources/generator.json --output-dir DIR
    python generate_calendars.py --config ... --check-dir holiday-calendars/data

The installed `holidays` package must be the exact version recorded in the
config (install it from requirements.txt with --require-hashes). The output
is a directory with one `<REGION>.json` per country and a `generation.json`
summary; it is byte-identical for the same config and package version.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.metadata
import inspect
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calendar_format import (  # noqa: E402
    MAX_CALENDAR_BYTES,
    SCHEMA_VERSION,
    FormatError,
    calendar_bytes,
    canonical_json_bytes,
    read_json,
    validate_calendar,
)

DOC_NAME = re.compile(r"^(?P<name>.+?) holidays\.?$")


def language_tag(upstream: str | None) -> str:
    """Map an upstream gettext locale (en_US, zh_CN, uk) to a BCP 47 tag."""
    if upstream is None:
        return "en"
    return upstream.replace("_", "-")


def load_config(path: Path) -> dict:
    config, _ = read_json(path, 64 * 1024)
    if config.get("schemaVersion") != 1:
        raise FormatError("unsupported generator config")
    first, last = config["years"]
    if not (isinstance(first, int) and isinstance(last, int) and first <= last):
        raise FormatError("bad years in generator config")
    if not isinstance(config.get("confirmedThrough"), int) or not first <= config["confirmedThrough"] <= last:
        raise FormatError("bad confirmedThrough in generator config")
    if config["categories"] != ["public"]:
        raise FormatError("only the public category is supported")
    if config["languages"].get("include") != "default-and-primary":
        raise FormatError("unsupported language policy")
    return config


def region_name(cls) -> str:
    """English name from the first docstring line "<Name> holidays." along the MRO."""
    for klass in cls.__mro__:
        doc = inspect.cleandoc(klass.__dict__.get("__doc__") or "")
        match = DOC_NAME.match(doc.splitlines()[0]) if doc else None
        if match:
            return match.group("name").strip()
    raise FormatError(f"{cls.__name__}: cannot derive a name from the docstrings")


def subdivision_names(cls) -> dict[str, str]:
    """First upstream alias that reads as a name (has a lower-case letter), else the first alias."""
    aliases: dict[str, list[str]] = {}
    for alias, code in (getattr(cls, "subdivisions_aliases", None) or {}).items():
        aliases.setdefault(code, []).append(alias)
    names = {}
    for code, values in aliases.items():
        readable = [value for value in values if any(char.islower() for char in value)]
        names[code] = (readable or values)[0]
    return names


def selected_languages(cls, primary: set[str]) -> tuple[str | None, list[str | None]]:
    default = cls.default_language
    upstream = list(getattr(cls, "supported_languages", ()) or ())
    chosen = [default]
    for tag in sorted(upstream):
        if tag != default and tag.split("_")[0] in primary:
            chosen.append(tag)
    return default, chosen


def collect(cls, years: range, language: str | None, subdivision: str | None):
    """Return ({year: {MM-DD: [names]}}, {year: [MM-DD]} workdays, instance)."""
    kwargs = {"years": years, "categories": ("public",)}
    if language is not None:
        kwargs["language"] = language
    if subdivision is not None:
        kwargs["subdiv"] = subdivision
    instance = cls(**kwargs)
    holidays_by_year: dict[int, dict[str, list[str]]] = {year: {} for year in years}
    for date in sorted(instance.keys()):
        if date.year in holidays_by_year:
            names = [name.strip() for name in instance.get_list(date)]
            if not names or any(not name for name in names):
                raise FormatError(f"{cls.__name__} {date}: empty holiday name")
            holidays_by_year[date.year][date.strftime("%m-%d")] = names
    workdays_by_year: dict[int, list[str]] = {year: [] for year in years}
    for date in sorted(instance.weekend_workdays):
        if date.year in workdays_by_year:
            workdays_by_year[date.year].append(date.strftime("%m-%d"))
    return holidays_by_year, workdays_by_year, instance


class NameTable:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []
        self.index: dict[tuple, int] = {}

    def add(self, name: dict[str, str]) -> int:
        key = tuple(sorted(name.items()))
        if key not in self.index:
            self.index[key] = len(self.entries)
            self.entries.append(dict(sorted(name.items())))
        return self.index[key]


def merge_languages(per_language: dict[str, dict[int, dict[str, list[str]]]], default: str, stats: dict):
    """Combine per-language name lists into {year: {MM-DD: [{lang: text}]}}."""
    base = per_language[default]
    merged: dict[int, dict[str, list[dict[str, str]]]] = {}
    for year, days in base.items():
        merged[year] = {}
        for month_day, names in days.items():
            slots = [{default: name} for name in names]
            for tag, other in per_language.items():
                if tag == default:
                    continue
                translated = other[year].get(month_day)
                if translated is None or len(translated) != len(names):
                    stats["languageMismatches"] += 1
                    continue
                for slot, text in zip(slots, translated):
                    slot[tag] = text
            merged[year][month_day] = slots
        for tag, other in per_language.items():
            if set(other[year]) != set(days):
                raise FormatError(f"{tag} {year}: the holiday dates differ from the default language")
    return merged


def year_weekends(instance, years: range) -> dict[int, list[int]]:
    """ISO weekdays (1 = Monday) that upstream treats as weekend, per year."""
    result = {}
    for year in years:
        flags: dict[int, set[bool]] = {}
        date = _dt.date(year, 1, 1)
        while date.year == year:
            flags.setdefault(date.isoweekday(), set()).add(bool(instance.is_weekend(date)))
            date += _dt.timedelta(days=1)
        if any(len(values) > 1 for values in flags.values()):
            raise FormatError(f"{type(instance).__name__} {year}: the weekend changes within the year")
        result[year] = sorted(day for day, values in flags.items() if values == {True})
    return result


def estimated_from(instance, years: range, has_workdays: bool, confirmed_through: int) -> int | None:
    """First year whose transfer arrangement is not announced yet, for regions that announce one yearly.

    Years up to `confirmed_through` (the year the pinned package was released) count as
    announced; later years count as announced only when upstream already has a table of
    special days or makeup workdays for them.
    """
    if not has_workdays:
        return None
    announced = {confirmed_through}
    for attribute in ("special_public_holidays", "special_workday_holidays"):
        table = getattr(instance, attribute, None) or {}
        announced.update(year for year in table if isinstance(year, int))
    announced.update(date.year for date in instance.weekend_workdays)
    first_estimated = max(announced) + 1
    if first_estimated > years[-1]:
        return None
    return max(first_estimated, years[0])


def build_region(code: str, loader, config: dict, stats: dict) -> dict:
    first, last = config["years"]
    # holidays.<CODE> is a lazy loader; the instance type is the real class.
    cls = type(loader(years=first))
    start = max(first, int(getattr(cls, "start_year", first)))
    end = min(last, int(getattr(cls, "end_year", last)))
    if start > end:
        raise FormatError(f"{code}: no year in range {first}-{last}")
    years = range(start, end + 1)
    primary = set(config["languages"]["primaryLanguages"])
    default, chosen = selected_languages(cls, primary)
    default_tag = language_tag(default)

    national_lists = {}
    workdays = None
    instance = None
    for language in chosen:
        days, workday_map, inst = collect(cls, years, language, None)
        national_lists[language_tag(language)] = days
        if language == default:
            workdays, instance = workday_map, inst
    weekends = year_weekends(instance, years)
    weekend = weekends[years[-1]]
    has_workdays = any(workdays[year] for year in years)
    national = merge_languages(national_lists, default_tag, stats)

    table = NameTable()
    calendar = {}
    for year in years:
        calendar[str(year)] = {
            "holidays": {md: [table.add(slot) for slot in slots] for md, slots in sorted(national[year].items())},
            "workdays": workdays[year],
        }
        if weekends[year] != weekend:
            calendar[str(year)]["weekend"] = weekends[year]

    sub_names = subdivision_names(cls)
    subdivisions = {}
    for subdivision in sorted(cls.subdivisions):
        sub_lists = {}
        sub_workdays = None
        sub_weekends = None
        for language in chosen:
            days, workday_map, inst = collect(cls, years, language, subdivision)
            sub_lists[language_tag(language)] = days
            if language == default:
                sub_workdays = workday_map
                sub_weekends = year_weekends(inst, years)
        if sub_workdays != workdays:
            raise FormatError(f"{code}-{subdivision}: makeup workdays differ from the national ones")
        merged = merge_languages(sub_lists, default_tag, stats)
        sub_calendar = {}
        for year in years:
            national_days = calendar[str(year)]["holidays"]
            own = {md: [table.add(slot) for slot in slots] for md, slots in merged[year].items()}
            entry = {}
            changed = {md: indexes for md, indexes in sorted(own.items()) if national_days.get(md) != indexes}
            removed = sorted(md for md in national_days if md not in own)
            if changed:
                entry["holidays"] = changed
            if removed:
                entry["removed"] = removed
            if sub_weekends[year] != calendar[str(year)].get("weekend", weekend):
                entry["weekend"] = sub_weekends[year]
            if entry:
                sub_calendar[str(year)] = entry
        subdivisions[subdivision] = {"name": sub_names.get(subdivision, subdivision), "calendar": sub_calendar}

    used_languages = sorted({tag for name in table.entries for tag in name} | {default_tag})
    document = {
        "schemaVersion": SCHEMA_VERSION,
        "region": code,
        "name": region_name(cls),
        "source": {
            "name": config["source"]["name"],
            "package": config["source"]["package"],
            "version": config["source"]["version"],
        },
        "years": [start, end],
        "estimatedFrom": estimated_from(instance, years, has_workdays, config["confirmedThrough"]),
        "weekend": weekend,
        "hasMakeupWorkdays": has_workdays,
        "defaultLanguage": default_tag,
        "languages": used_languages,
        "names": table.entries,
        "calendar": calendar,
        "subdivisions": subdivisions,
    }
    validate_calendar(document)
    return document


def generate(config: dict, output_dir: Path) -> dict:
    import holidays  # noqa: PLC0415 - optional dependency, only needed here

    installed = importlib.metadata.version("holidays")
    if installed != config["source"]["version"]:
        raise SystemExit(f"holidays {installed} is installed, the config pins {config['source']['version']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = {"languageMismatches": 0}
    regions = []
    countries = holidays.list_supported_countries(include_aliases=False)
    for code in sorted(countries):
        cls = getattr(holidays, code)
        document = build_region(code, cls, config, stats)
        data = calendar_bytes(document)
        if len(data) > MAX_CALENDAR_BYTES:
            raise FormatError(f"{code}: calendar is larger than {MAX_CALENDAR_BYTES} bytes")
        (output_dir / f"{code}.json").write_bytes(data)
        regions.append(code)
    summary = {
        "languageMismatches": stats["languageMismatches"],
        "regions": len(regions),
        "source": config["source"],
        "subdivisions": sum(len(countries[code]) for code in regions),
        "years": config["years"],
    }
    (output_dir / "generation.json").write_bytes(canonical_json_bytes(summary))
    return summary


def compare_dirs(expected: Path, actual: Path) -> list[str]:
    problems = []
    expected_files = {path.name for path in expected.glob("*.json")}
    actual_files = {path.name for path in actual.glob("*.json")}
    for name in sorted(expected_files - actual_files):
        problems.append(f"missing in the committed data: {name}")
    for name in sorted(actual_files - expected_files):
        problems.append(f"not produced by the generator: {name}")
    for name in sorted(expected_files & actual_files):
        if (expected / name).read_bytes() != (actual / name).read_bytes():
            problems.append(f"differs: {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--output-dir", type=Path, help="write the generated files here (the directory must be empty)")
    target.add_argument("--check-dir", type=Path, help="regenerate and compare byte for byte with this directory")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.output_dir is not None:
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            parser.error(f"{args.output_dir} is not empty")
        summary = generate(config, args.output_dir)
        print(f"generated {summary['regions']} regions, {summary['subdivisions']} subdivisions "
              f"(holidays {config['source']['version']}, years {config['years'][0]}-{config['years'][1]})")
        return 0
    work = Path(tempfile.mkdtemp(prefix="holiday-calendars-check-"))
    try:
        generate(config, work)
        problems = compare_dirs(work, args.check_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for problem in problems:
        print(problem)
    print("check: OK" if not problems else f"check: {len(problems)} problem(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
