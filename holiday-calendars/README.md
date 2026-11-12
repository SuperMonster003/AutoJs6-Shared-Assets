# AutoJs6 holiday calendars

This asset family distributes public holiday calendars for the AutoJs6 plugin 3-Chime Alarm
(`AutoJs6-Plugin-Three-Chime-Alarm`, roadmap phase P8, decisions D16 and D17, appendix B Q8). The
data is generated at build time from the Python package
[python-holidays](https://github.com/vacanza/holidays) (`holidays` on PyPI, MIT license), pinned to
one exact release. The plugin bundles a snapshot of the signed catalog and the calendar files, then
checks this family weekly for a newer signed catalog and downloads only the files that changed.

The family has its own directory, schemas, tools (`tools/holiday-calendar-distribution/`), workflow
(`.github/workflows/publish-holiday-calendars.yml`), release-tag prefix (`holiday-calendars-vN`) and
ECDSA P-256 signing key. It follows the speech model family's catalog, signing and release
conventions; the keys, catalogs and releases of the other families stay separate.

## Source and license

- Upstream: python-holidays 0.108 (released 2026-11-02), wheel `holidays-0.108-py3-none-any.whl`,
  SHA-256 `5a08fdccd0b8737093d483ba0d0d9696560396d99d3fa6ef9264fd2ac48749c7`. Its dependencies
  python-dateutil 2.9.0.post0 and six 1.17.0 are pinned by hash in
  [requirements.txt](../tools/holiday-calendar-distribution/requirements.txt); they are only used to
  compute the dates and none of their content is redistributed.
- License: MIT. The full text is [LICENSE-python-holidays.txt](LICENSE-python-holidays.txt) and the
  contributor list that its copyright line refers to is
  [CONTRIBUTORS-python-holidays.txt](CONTRIBUTORS-python-holidays.txt), both copied unchanged from
  the wheel's `holidays-0.108.dist-info/licenses/`. Redistribution of the generated data must keep
  both files (the plugin lists them in `THIRD_PARTY_NOTICES.md`).
- Sources per region are those python-holidays documents for that country (official gazettes,
  government announcements and the references in its source code). This family adds no data of its
  own and does no manual review (decision D17): the accuracy of holidays and makeup workdays
  depends entirely on upstream.
- Generation settings: [sources/generator.json](sources/generator.json) (package version, wheel hash,
  year range, holiday categories, languages and `confirmedThrough`).
- Spot checks of published dates: [sources/known-dates.json](sources/known-dates.json) (mainland
  China 2025 and 2026 transfer arrangements, United States, California, Japan, and the changing
  weekends of the United Arab Emirates and Malaysia), checked by `verify_calendars.py`.

## Layout

```text
holiday-calendars/
  data/<CC>.json                    # one calendar file per region (the release assets, content-addressed)
  data/generation.json              # generation summary (source, years, counts)
  catalogs/catalog-v1.json          # current signed catalog, with catalog-v1.sig.json
  catalogs/history/vN/              # exact catalog and signature of release N
  catalogs/pending/vN/              # reviewed candidate awaiting offline signing
  sources/generator.json            # generation settings
  sources/known-dates.json          # spot checks of published dates
  keys/catalog-signing-public.pem   # public key only
  schemas/                          # calendar, catalog and signature schemas
```

Schemas: [calendar file v1](schemas/calendar-v1.schema.json), [catalog v1](schemas/catalog-v1.schema.json),
[signature v1](schemas/signature-v1.schema.json). Cross-field rules are enforced by
`tools/holiday-calendar-distribution/calendar_format.py` and listed in each schema's `$comment`.

## What a client requests

1. The catalog and its detached signature, from the default branch:
   - `https://raw.githubusercontent.com/SuperMonster003/AutoJs6-Shared-Assets/main/holiday-calendars/catalogs/catalog-v1.json`
   - `https://raw.githubusercontent.com/SuperMonster003/AutoJs6-Shared-Assets/main/holiday-calendars/catalogs/catalog-v1.sig.json`
2. For each region whose `file.sha256` differs from the local copy, `regions[].file.url`, which is
   always `https://github.com/SuperMonster003/AutoJs6-Shared-Assets/releases/download/<file.releaseTag>/<file.name>`
   (GitHub answers with a redirect to its release asset host).

Nothing else is needed: the catalog carries every region's summary, so a client can list regions and
subdivisions without downloading a calendar file. Both hosts use the Let's Encrypt chain, so a client
on Android 7.0 needs the ISRG Root X1 certificate in its network security configuration (as 3-Macaw
Speech does).

A client must, in this order:

1. Parse the signature envelope and verify the ECDSA P-256 SHA-256 signature over the exact catalog
   bytes with the bundled public key (see Signing key); reject a `keyId` other than the bundled one.
2. Parse and validate the catalog; reject `schemaVersion` other than 1, `family` other than
   `holiday-calendars`, and a `repository` other than `SuperMonster003/AutoJs6-Shared-Assets`.
3. Reject rollback: accept a catalog only when its `catalogVersion` is greater than the stored one
   (equal means no update).
4. Download changed files, then check each file's byte size and SHA-256 against `regions[].file`
   before parsing it, and validate it (`region` must equal the catalog code).
5. Switch to the new catalog and files only after every changed file passed, so a failed refresh
   leaves the previous complete set in use.

## Encoding

- Every file is UTF-8 JSON without a byte order mark, not compressed. Whitespace carries no meaning;
  clients parse JSON and never compare text, but digests are computed over the exact bytes.
- Object keys are unique; there are no `NaN` or infinite numbers. Arrays described as sorted are
  sorted ascending and contain no duplicates.
- Dates inside a year are `MM-DD` strings (`02-14`); years used as object keys are four-digit
  strings (`"2026"`); weekdays are ISO numbers, `1` = Monday through `7` = Sunday.
- Size limits: catalog and each calendar file at most 4 MiB, signature envelope at most 4 KiB.

## Catalog (schema 1)

```json
{
  "catalogVersion": 1,
  "family": "holiday-calendars",
  "generatedAt": "2026-11-12T00:00:00Z",
  "regions": [
    {
      "code": "CN",
      "estimatedFrom": 2027,
      "file": {
        "name": "holiday-calendar-CN-<first 8 hex of sha256>.json",
        "releaseTag": "holiday-calendars-v1",
        "sha256": "<64 hex>",
        "size": 12345,
        "url": "https://github.com/SuperMonster003/AutoJs6-Shared-Assets/releases/download/holiday-calendars-v1/holiday-calendar-CN-<8 hex>.json"
      },
      "hasMakeupWorkdays": true,
      "name": "China",
      "subdivisions": [],
      "years": [2020, 2035]
    }
  ],
  "releaseTag": "holiday-calendars-v1",
  "repository": "SuperMonster003/AutoJs6-Shared-Assets",
  "schemaVersion": 1,
  "source": {"homepage": "https://github.com/vacanza/holidays", "license": "MIT", "name": "python-holidays", "package": "holidays", "version": "0.108"},
  "years": [2020, 2035]
}
```

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Wire schema, `1`. The file name follows it: schema S is `catalog-vS.json`. A future incompatible schema gets a new file name, and `catalog-v1.json` then stays frozen for old clients. |
| `catalogVersion` | Release number N, increases by exactly one per release. |
| `releaseTag` | `holiday-calendars-vN` for this catalog. |
| `generatedAt` | UTC time of the build, `YYYY-MM-DDTHH:MM:SSZ`. |
| `repository` | `SuperMonster003/AutoJs6-Shared-Assets`; a signed catalog binds it. |
| `source` | Upstream name, PyPI package, exact version, license and homepage. |
| `years` | `[first, last]` range requested at generation (2020-2035); a region may cover less. |
| `regions[]` | Sorted by `code`. The fields `code`, `name`, `years`, `estimatedFrom`, `hasMakeupWorkdays` and `subdivisions` equal the calendar file's `region`, `name`, `years`, `estimatedFrom`, `hasMakeupWorkdays` and its subdivision codes and names. |
| `regions[].code` | ISO 3166-1 alpha-2 code as used upstream (for example `CN`, `US`, `TW`, `HK`). |
| `regions[].name` | Upstream English name (for example `United States of America (the)`); display names should come from the platform (`Locale.getDisplayCountry`) and fall back to this. |
| `regions[].subdivisions[]` | `{code, name}` sorted by `code`; codes are upstream codes taken verbatim (mostly ISO 3166-2 suffixes such as `CA`, sometimes numbers or names that contain spaces or non-ASCII letters), names are upstream English names. |
| `regions[].file` | The calendar file: content-addressed `name` (`holiday-calendar-<code>-<first 8 hex of sha256>.json`), the `releaseTag` of the release that first published it, `sha256`, `size` in bytes, and the download `url`. A region whose data did not change keeps the entry of an earlier release unchanged. |

## Calendar file (schema 1)

One file per region, the same bytes in `data/<code>.json` and in the release asset.

| Field | Meaning |
| --- | --- |
| `schemaVersion` | `1`. |
| `region` | Region code, equals the catalog `code`. |
| `name` | Upstream English name. |
| `source` | `{name, package, version}` of the generator input. |
| `years` | `[first, last]`, both inclusive; `calendar` has exactly one entry per year in this range. A year outside it has no data. |
| `estimatedFrom` | First year whose transfer arrangement upstream computes by rule because the government has not announced it yet, or `null`. Only regions with makeup workdays have a value (see Data notes). |
| `weekend` | Default weekend, sorted ISO weekdays (for most regions `[6, 7]`). A year or subdivision may override it. |
| `hasMakeupWorkdays` | `true` exactly when some year has at least one makeup workday. |
| `defaultLanguage` | BCP 47 tag of the language every name has (upstream's default language, `en` when upstream has none). |
| `languages` | Sorted BCP 47 tags of all languages present in `names`, including `defaultLanguage`. |
| `names` | Array of holiday names; each item is an object from language tag to text and always has `defaultLanguage`. Calendar entries refer to names by array index. |
| `calendar` | Object from year (`"2026"`) to the national entry of that year. |
| `subdivisions` | Object from subdivision code to `{name, calendar}`, where `calendar` maps years to overlays on the national entry. Years without differences are absent; the object is empty for regions without subdivisions. |

National entry of a year:

| Field | Meaning |
| --- | --- |
| `holidays` | Object from `MM-DD` to a non-empty array of indexes into `names` (several holidays can fall on one day; the order is upstream's). Every listed date is a day off. Observed days (substitute days off when a holiday falls on a weekend) are listed under their own names. |
| `workdays` | Sorted `MM-DD` makeup workdays: weekend days that are working days because of a transfer arrangement (for example mainland China's adjusted working Saturdays and Sundays). Each one falls on that year's weekend and is not in `holidays`. Usually empty. |
| `weekend` | Optional. Present only in a year whose weekend differs from the file's `weekend`. |

Subdivision overlay of a year:

| Field | Meaning |
| --- | --- |
| `holidays` | Optional, non-empty. Dates whose holiday list differs in this subdivision, each with the subdivision's complete list for that date (it replaces the national list for that date). |
| `removed` | Optional, non-empty, sorted. National holidays that are not days off in this subdivision. |
| `weekend` | Optional. The subdivision's weekend in this year when it differs from the national weekend of that year. |

Subdivisions never have their own makeup workdays: the national `workdays` apply to every
subdivision (the generator asserts this).

### Resolving a day

For region R, optional subdivision S and date D in year Y:

1. If Y is outside `years`, there is no data for that year.
2. Take the national entry E of Y. `holidays` = copy of `E.holidays`; `workdays` = `E.workdays`;
   `weekend` = `E.weekend` if present, else the file's `weekend`.
3. With a subdivision S whose `calendar` has Y: delete each date in `removed` from `holidays`, then
   put every date of the overlay's `holidays` into `holidays` (replacing the national list for that
   date), then use the overlay's `weekend` if present.
4. D is a holiday when its `MM-DD` is in `holidays`. D is a makeup workday when it is in `workdays`.
5. D is a day off when it is a holiday, or when its ISO weekday is in `weekend` and it is not a makeup
   workday. Otherwise it is a working day.

`calendar_format.resolve_year()` and `is_day_off()` are the reference implementation.

### Choosing a name language

Names are upstream's texts verbatim (some contain full-width punctuation in Chinese, and a few carry
upstream's own `(estimated)` suffix). Upstream languages are kept when they are the region's default
language or when their primary language is one of the plugin's interface languages (`zh`, `en`,
`fr`, `es`, `ja`, `ko`, `ru`, `ar`). Upstream locales become BCP 47 tags (`zh_CN` becomes `zh-CN`).
Suggested lookup for an interface locale:

1. Map script tags to the region tags used here: `zh-Hans` to `zh-CN`; `zh-Hant-TW` to `zh-TW`;
   `zh-Hant-HK` to `zh-HK`, then `zh-TW`; `zh-Hant-MO` to `zh-MO`, then `zh-HK`, then `zh-TW`.
2. Use an exact tag match (case-insensitive) if the name has it.
3. Otherwise a tag with the same primary language: `<lang>-<region code>` first, then the bare
   `<lang>`, then the first such tag in sorted order.
4. Otherwise `defaultLanguage`, which every name has.

## Data notes

- Category: upstream's `public` category only, which includes the observed days off. Bank, school,
  optional and similar categories are not exported.
- Years: 2020 through 2035 for every region, except where upstream's data is narrower: Guinea-Bissau
  (`GW`) starts in 2023 and Sri Lanka (`LK`) ends in 2026.
- Makeup workdays: 14 regions have them (`AM`, `AZ`, `BY`, `CN`, `HU`, `KG`, `KZ`, `LV`, `MM`, `RU`,
  `TW`, `UA`, `UZ`, `VN`). Governments announce these arrangements year by year, usually in November
  or December for the next year. `estimatedFrom` marks the first year that is not announced in
  upstream: years up to `confirmedThrough` in `sources/generator.json` (2026 for this release) and
  every year that upstream already has a table of special days or makeup workdays for count as
  announced. In this release it is 2027 for 13 regions and 2028 for `RU`. Years from `estimatedFrom`
  on contain only the holidays that follow fixed rules and no makeup workdays; clients should present
  them as estimated.
- Holidays that a government declares ad hoc (one-off days off) appear only after upstream adds
  them, for every region. The family is rebuilt from a new upstream release each November and when
  a significant announcement lands.
- Weekends can change: the United Arab Emirates used Friday and Saturday through 2021, then Saturday
  and Sunday; in Malaysia, Johor (`01`) used Friday and Saturday through 2024, while Kedah (`02`),
  Kelantan (`03`) and Terengganu (`11`) use Friday and Saturday in every year.

Release 1 contains 250 regions and 629 subdivisions (36 regions have subdivisions; the regions carry
500 language tags in total, and no region's holiday dates differ between its languages). Sizes: 1,886,102 bytes raw in
total, 336,663 bytes when each file is compressed with gzip -9; per region and year 69 / 331 / 5,164
bytes raw (minimum / median / maximum) and 20 / 67 / 662 bytes gzip; the largest file is `IT`
(82,621 bytes: 114 provinces and cities, each with its patron saint day); the catalog is 193,762 bytes.

## Version and integrity rules

- `catalogVersion` increases by exactly one per release, the tag is `holiday-calendars-vN`, and a
  signed catalog binds its repository.
- Calendar file names are content-addressed, and a published file never changes. A region whose
  bytes changed gets a new name in the new release; an unchanged region keeps its earlier entry
  (`releaseTag`, `url` and all), so each release uploads only the files it introduces
  (`release-assets.txt`). A release with no changed file is refused.
- Every entry that is not new in a release equals the previous catalog's entry for that region.
- Clients verify the detached signature over the exact catalog bytes, refuse catalog rollback, and
  check each file's size and SHA-256 before using it.
- Generation is reproducible: with the pinned packages, `generate_calendars.py --check-dir` rebuilds
  `data/` byte for byte (checked with Python 3.12 and 3.13 and different hash seeds), and the release
  workflow repeats that check before publishing.

## Current state

Release 1 is prepared and not signed: `catalogs/pending/v1/` holds the reviewed `catalog-v1.json`
(`catalogVersion` 1, generated at 2026-11-12T00:00:00Z), `release-assets.txt` (all 250 files) and
`preparation.json`. `holiday-calendars-v1` has neither a tag nor a Release yet.

## Signing key

- Family key generated on 2026-11-12 with `crypto.generate_key_pair()` of
  `tools/holiday-calendar-distribution/` (ECDSA P-256, OpenSSL 3.2.1). The private key stays outside
  every Git working tree, at `D:/offline-keys/holiday-calendars.private.pem` on the maintainer's
  machine; the keys of the other families are not reused and the tools refuse them.
- Key ID: `p256-35ac0585129625d2`.
- SPKI DER SHA-256: `35ac0585129625d2090af2dc54cbe559b9c272015bde7a1e5ace44e922b02563`.
- Public key: `keys/catalog-signing-public.pem`. The key ID is `p256-` plus the first 16 hex digits
  of the SHA-256 of the public key's SPKI DER bytes.

Signature envelope (`catalog-v1.sig.json`, canonical JSON with sorted keys):

```json
{
  "algorithm": "ECDSA_P256_SHA256",
  "catalog": "catalog-v1.json",
  "keyId": "p256-35ac0585129625d2",
  "signature": "<base64 of one DER ECDSA-Sig-Value>"
}
```

The signature is ECDSA over SHA-256 of the exact `catalog-v1.json` bytes, encoded as an ASN.1 DER
`SEQUENCE` of two `INTEGER`s and then as canonical base64 (at most 128 characters). On Android it
verifies with `Signature.getInstance("SHA256withECDSA")` and the public key from
`X509EncodedKeySpec`.

Verify the checked-in public key:

```text
openssl pkey -pubin -in holiday-calendars/keys/catalog-signing-public.pem -outform DER | openssl dgst -sha256
```

## Maintainer signing and publication

Run from the repository root on the machine that holds the offline key. The tools need Python 3.12
or newer and OpenSSL; signing refuses a private key inside any Git working tree and a catalog that
fails validation. Sign from a normal PowerShell window, not an elevated Administrator one. The steps
publish release 1; a later release N uses `vN` paths and passes
`--previous-catalog holiday-calendars/catalogs/history/v<N-1>/catalog-v1.json` instead of
`--first-release`.

1. Re-check the reviewed candidate, then sign the exact bytes:

   ```powershell
   $keyId = 'p256-35ac0585129625d2'
   $repo = 'SuperMonster003/AutoJs6-Shared-Assets'
   $pending = 'holiday-calendars/catalogs/pending/v1'
   python tools/holiday-calendar-distribution/verify_calendars.py $pending/catalog-v1.json --data-dir holiday-calendars/data --first-release --release-assets $pending/release-assets.txt --known-dates holiday-calendars/sources/known-dates.json
   python tools/holiday-calendar-distribution/sign_catalog.py $pending/catalog-v1.json --private-key D:/offline-keys/holiday-calendars.private.pem --output $pending/catalog-v1.sig.json --key-id $keyId --expected-repository $repo
   ```

2. Promote the identical bytes (never reformat a signed catalog) and verify the promoted pair. From
   release 2 on, first copy the current `catalogs/catalog-v1.json` and `catalog-v1.sig.json` into
   `catalogs/history/v<N-1>/`.

   ```powershell
   Copy-Item $pending/catalog-v1.json holiday-calendars/catalogs/catalog-v1.json
   Copy-Item $pending/catalog-v1.sig.json holiday-calendars/catalogs/catalog-v1.sig.json
   python tools/holiday-calendar-distribution/verify_calendars.py holiday-calendars/catalogs/catalog-v1.json --data-dir holiday-calendars/data --first-release --signature holiday-calendars/catalogs/catalog-v1.sig.json --public-key holiday-calendars/keys/catalog-signing-public.pem --expected-key-id $keyId --known-dates holiday-calendars/sources/known-dates.json
   ```

3. Commit the signature and the promoted pair, confirm that the diff contains no private key, and
   push. Before the first release create the GitHub environment `holiday-calendars-release` (the same
   protection as `speech-models-release`) and keep Immutable Releases enabled.

4. Dispatch the workflow from `main` with the exact tag and key ID:

   ```powershell
   gh workflow run publish-holiday-calendars.yml --repo SuperMonster003/AutoJs6-Shared-Assets --ref main -f release_tag=holiday-calendars-v1 -f key_id=p256-35ac0585129625d2
   ```

   The workflow installs the pinned packages by hash, runs the tool tests, regenerates `data/` and
   compares bytes, verifies the current and historical signatures and the spot checks, rebuilds the
   catalog against the previous release and compares it with the promoted and pending files, stages
   and verifies the new files, confirms that neither the tag nor the Release exists, publishes the
   files with the catalog and signature, then downloads everything again and verifies it. It never
   overwrites an existing tag or Release; a failure after tag creation needs manual inspection.

5. Record the Release URL, the file count and total size, and the key ID in the plugin roadmap
   (P8.1), and bundle the exact signed catalog, signature and files in the plugin (P8.2).

The yearly rebuild (new upstream release, `confirmedThrough` + 1) is described in the
[tool README](../tools/holiday-calendar-distribution/README.md).
