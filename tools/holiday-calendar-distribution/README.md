# Holiday calendar distribution tools

These Python tools generate, prepare and verify the independent `holiday-calendars/` asset family.
Apart from `generate_calendars.py`, which needs the pinned python-holidays release, they use only
the standard library, plus OpenSSL for P-256 signing and verification and the `gh` CLI for the
release preflight. Run every command from the repository root. Format, policy, layout and the
maintainer's signing and publication steps are in [the family README](../../holiday-calendars/README.md).

| Script | Purpose |
| --- | --- |
| `generate_calendars.py` | Generate `holiday-calendars/data/` from the pinned python-holidays release (`--output-dir` into an empty directory), or regenerate and compare byte for byte (`--check-dir`). |
| `build_catalog.py` | Build an unsigned catalog from `data/` (no network), plus `release-assets.txt` and `preparation.json`; `--previous-catalog` keeps unchanged regions on their earlier release, `--stage-assets` copies the new files under their release names. |
| `verify_calendars.py` | Check the catalog, history rules, `release-assets.txt`, the detached signature, every data file (format, size, SHA-256, catalog summary) and the spot checks in `sources/known-dates.json`; `--sizes` prints size statistics. Prints one PASS or FAIL line per check. |
| `sign_catalog.py` | Maintainer-only offline signing with the holiday calendar key. |
| `verify_release.py` | Verify staged or downloaded release files by name, size and SHA-256 (a downloaded release also with the catalog and signature bytes), verify a single signature (`--verify-signature`, for history catalogs), or confirm remote tag and Release absence. |
| `check_docs.py` | ASCII punctuation, relative links and the recorded key fingerprint of the holiday calendar documents (run by `markdown.yml`). |

`calendar_format.py` holds the strict JSON reader, the byte-exact writers, the calendar and catalog
validators, `resolve_year()` / `is_day_off()` (the reference for clients) and the history rules.
`crypto.py` adapts the speech model signature code and refuses the keys of the other families.
Tests: `python -m unittest discover -s tools/holiday-calendar-distribution/tests -t tools/holiday-calendar-distribution`
(the generator test runs only when the pinned `holidays` is installed, the signature tests only when
OpenSSL is found).

## Installing the generator

Install the pinned packages into a virtual environment outside the repository, never into the global
Python:

```text
python -m venv <somewhere outside the repository>/holiday-venv
<venv python> -m pip install --require-hashes --only-binary=:all: -r tools/holiday-calendar-distribution/requirements.txt
<venv python> tools/holiday-calendar-distribution/generate_calendars.py --config holiday-calendars/sources/generator.json --check-dir holiday-calendars/data
```

`generate_calendars.py` refuses to run when the installed `holidays` version differs from
`sources/generator.json`. A full generation takes about 15 seconds.

## How the generator reads python-holidays

- Regions: `holidays.list_supported_countries(include_aliases=False)`; each `holidays.<CODE>` is a
  lazy loader, so the real class is `type(loader(years=...))`. The English region name is the first
  line of the class docstring (`"<Name> holidays."`, looked up along the class hierarchy). The year
  range is `[2020, 2035]` narrowed to the class's `start_year` and `end_year`.
- Holidays: category `public` only, names from `get_list(date)` in each selected language
  (`language=`). Languages are aligned by position per date; any disagreement in dates between
  languages fails the run.
- Makeup workdays: `weekend_workdays`, filtered to the year. Weekend: `is_weekend(date)` for every day
  of the year; a weekend that changes within a year fails the run.
- Subdivisions: `subdivisions` and `subdivisions_aliases` (the English name is the first alias that
  contains a lowercase letter). Each subdivision instance is compared with the national one per year;
  the differences become the overlay, and a subdivision with different makeup workdays fails the run.
- `estimatedFrom`: see the family README; the inputs are `confirmedThrough`, the years of
  `special_public_holidays` and `special_workday_holidays`, and the years of `weekend_workdays`.

## Yearly rebuild

Each November, after the transfer arrangements for the next year are announced and a python-holidays
release contains them (it usually follows within two weeks):

1. Check the new upstream release notes and license (the MIT text and CONTRIBUTORS file must still
   match the copies in `holiday-calendars/`; replace both when they changed).
2. Update `sources/generator.json` (`version`, `wheel`, `wheelSha256`, `confirmedThrough` + 1) and
   `requirements.txt` (new hashes, also for changed dependencies), then regenerate into an empty
   directory and replace `holiday-calendars/data/` with it.
3. Add the next year's published arrangement to `sources/known-dates.json` (for example the mainland
   China State Council notice) and run `verify_calendars.py` until it passes.
4. Build the next pending catalog against the current one:

   ```text
   python tools/holiday-calendar-distribution/build_catalog.py --data-dir holiday-calendars/data --output-dir holiday-calendars/catalogs/pending/v<N> --catalog-version <N> --generated-at <YYYY-MM-DD>T00:00:00Z --previous-catalog holiday-calendars/catalogs/catalog-v1.json
   ```

5. Commit, then follow the maintainer signing and publication steps in the family README.

Extending the year range or adding categories changes many files at once but keeps schema 1; a new
field or meaning needs schema 2 and a new catalog file name.
