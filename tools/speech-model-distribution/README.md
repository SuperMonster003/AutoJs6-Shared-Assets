# Speech model distribution tools

These Python 3.12 tools prepare and verify the independent `speech-models/` asset family. They use
only the standard library, plus OpenSSL for P-256 signing and verification and the `gh` CLI for the
release preflight. Run every command from the repository root. Policy, layout and the maintainer's
signing and publication steps are in [the family README](../../speech-models/README.md).

| Script | Purpose |
| --- | --- |
| `prepare_sources.py` | Download the pinned upstream sherpa-onnx assets into `build/`, verify them, repack the archives and compare or record the measured digests. Upstream-only sources (`mirror` false) are measured but not archived. |
| `build_catalog.py` | Build an unsigned catalog from the sources (no network), plus `release-assets.txt` and `preparation.json`. |
| `verify_catalog.py` | Validate schema rules, canonical bytes, history and immutability, optionally the rebuild from sources and the detached signature. |
| `sign_catalog.py` | Maintainer-only offline signing with the speech key. |
| `verify_release.py` | Verify release archives by name, size, SHA-256 and USTAR content (a downloaded release also with its catalogs, `--companion` for a same-release catalog of an older schema), or confirm remote tag and Release absence. |
| `check_docs.py` | ASCII punctuation, relative links and the recorded key fingerprint of the speech documents (run by `markdown.yml`). |

`distribution.py` holds the validators, the canonical archive writer and reader and catalog building;
`preparation.py` holds the downloader and repacker; `crypto.py` adapts the codegen signature code and
refuses the Ace and codegen keys.

On Windows, since the CVE-2024-4030 fix (Python 3.12.4 and 3.13), `tempfile.mkdtemp()` gives new
directories a DACL that allows only SYSTEM, Administrators and the owner, and a rename keeps it;
`distribution.inherit_parent_acl()` therefore resets every staging directory and each promoted
archive to the rights inherited from the destination, so Git and other accounts can read the output,
including a signature later written into it.

## Upstream cache and repacking

`prepare_sources.py` stores each upstream asset as `build/speech-models/upstream/<tag>/<asset>`,
downloading with HTTP range resume and only from `github.com` release URLs of `k2-fsa/sherpa-onnx`
(redirects are limited to GitHub's release asset hosts). A cached file is used only after its size
and SHA-256 match `source.json`; a mismatching cache file must be deleted by hand. `--offline` never
touches the network.

Archives are read with Python's `tarfile` in sequential `r:bz2` mode. Selected members must be
regular files that appear exactly once; they are streamed into numbered blobs, so member names never
reach the file system. Unselected members (test recordings, float32 duplicates and so on) are
skipped. The writer then emits the canonical USTAR archive described in the family README and
re-reads it strictly before naming it by its SHA-256.

Without `--update-sources` every rebuilt archive and file list must equal `source.json`, which turns
the run into a reproducibility check. `--catalog <catalog>` limits the run to the archives that the
catalog's own release introduces (used by the workflow); `--model <modelId>/<versionCode>` selects
single versions.

A source with `"mirror": false` is upstream-only: the maintainer decided not to redistribute its
weights. Its selected members are still staged and measured so that `files[]` is recorded and
re-checked, but no archive is written, `archive` stays null, the catalog records `mirror` as null,
and `release-assets.txt`, `--catalog` runs and `verify_release.py` leave it out. Clients install such a
version from `upstream[]` alone.

## Adding or changing a model version

A published `(modelId, versionCode)` is immutable. A different member selection, a new upstream
asset or a replaced upstream file requires a new `versionCode`.

1. Create `speech-models/sources/<modelId>/<versionCode>/` with `source.json` (format in
   [model-source-v1.schema.json](../../speech-models/schemas/model-source-v1.schema.json)), `MODEL_CARD.md`
   and the license files. Set `archive` and `files` to null, and `mirror` to true unless the maintainer
   decided not to redistribute the weights (then `mirror` is false and `archive` stays null for good).
2. Measure and record the archive and installed files:

   ```powershell
   python tools/speech-model-distribution/prepare_sources.py --update-sources --model <modelId>/<versionCode>
   ```

3. Review the recorded `files[]`, add the license evidence to a new or updated
   `speech-models/audits/license-audit-vN.json`, and reproduce once more without `--update-sources`.
4. Copy the previous current catalog and signature unchanged into `catalogs/history/v<N-1>/`, then
   build the next candidate. Catalog files are named by wire schema (`catalog-v<S>.json`, `S` = 3
   today; `distribution.CATALOG_FILE`), so the previous release may use an older name:

   ```powershell
   python tools/speech-model-distribution/build_catalog.py --source-root speech-models/sources --output speech-models/catalogs/pending/v<N> --catalog-version <N> --generated-at <review time, UTC> --previous-catalog speech-models/catalogs/history/v<N-1>/catalog-v<S'>.json
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v<N>/catalog-v<S>.json --previous-catalog speech-models/catalogs/history/v<N-1>/catalog-v<S'>.json --minimum-catalog-version <N> --expected-repository SuperMonster003/AutoJs6-Shared-Assets --source-root speech-models/sources
   ```

   A new wire schema gets its own `catalog-v<S>.schema.json` and `signature-v<S>.schema.json`; the
   older catalog file stays frozen in `catalogs/` next to its identical history copy. When a release
   also serves plugins that read an older schema (decision D127), build that catalog with
   `--schema <S>` into a second new directory and move its `catalog-v<S>.json` next to the newest
   one; it leaves out the versions that need a newer schema, and the newest catalog's
   `release-assets.txt` and `preparation.json` cover both.

5. Sign, promote and publish as in the family README, using tag `speech-models-v<N>`.

`build_catalog.py` never overwrites an output directory. Model-level `displayName`, `summary` and
`recommended` follow the newest source of each model; version-level data is carried unchanged from the
previous catalog and must still match its source.

## Local checks

```powershell
python -m unittest discover -s tools/speech-model-distribution/tests -v
python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v3/catalog-v3.json --previous-catalog speech-models/catalogs/history/v2/catalog-v2.json --minimum-catalog-version 3 --expected-repository SuperMonster003/AutoJs6-Shared-Assets --source-root speech-models/sources
python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v3/catalog-v2.json --previous-catalog speech-models/catalogs/history/v2/catalog-v2.json --minimum-catalog-version 3 --expected-repository SuperMonster003/AutoJs6-Shared-Assets --source-root speech-models/sources
python tools/speech-model-distribution/check_docs.py
```

The tests use synthetic upstream archives, fake HTTP responses and disposable OpenSSL keys in
temporary directories; they need no network and no real model. They cover the archive format, source
and catalog validation, schema 1, 2 and 3 rules, history rules, repacking, the downloader, signatures,
release verification, the remote preflight, the workflow contract and the checked-in data (the
frozen v1 catalog, the signed v2 catalog, their history copies and the pending v3 candidates).

## Measured v1 preparation (2026-10-16)

The eleven pinned upstream assets of the current sources (1,855,051,280 bytes) were downloaded once
into the ignored cache; the SenseVoice 2024-07-17 asset was added on 2026-10-16 when it replaced the
2025-09-09 export, and its GitHub API digest matched the measured SHA-256.
`prepare_sources.py --update-sources --offline` built the archives in about 8.5 minutes on the
maintainer's Windows workstation, and a second `prepare_sources.py --offline` run into a new output
directory reproduced all nine archives with identical SHA-256 digests while re-measuring the
upstream-only Chinese streaming model (five files, 167,361,237 bytes, no archive). `verify_release.py`
accepted the reproduced set against the pending v1 catalog and its `release-assets.txt`. No network
publication took place.

## Measured v2 preparation (2026-10-23)

The nine pinned upstream assets of the new sources (1,020,254,475 bytes) were downloaded once into a
local cache. `prepare_sources.py --update-sources` measured the eight new archives (388,244,480 bytes)
and the files of the upstream-only Korean model (four files, 140,919,603 bytes, no archive); a second
offline run reproduced all eight archives with identical SHA-256 digests. `build_catalog.py` then
built `pending/v2` against `history/v1/catalog-v1.json`, and `verify_catalog.py` accepted it with the
rebuild from sources. No network publication took place.

## Measured v3 preparation (2026-10-25)

The six pinned upstream assets of the new sources (609,262,404 bytes) were downloaded once into a
local cache outside the repository and checked against the GitHub release digests.
`prepare_sources.py --update-sources` measured the five new archives (762,554,368 bytes) and the files
of the upstream-only Arabic miro V2 voice (358 files, 36,566,185 bytes, no archive); a second
`--offline` run into a new output directory reproduced all five archives with identical SHA-256
digests. `build_catalog.py` then built `pending/v3` (`catalog-v2.json`, `catalogVersion` 3) against
`history/v2/catalog-v2.json`, and `verify_catalog.py` accepted it with the rebuild from sources. No
network publication took place.

## Measured v3 speaker model (2026-10-29)

The pinned upstream asset of the speaker model (one ONNX file, 26,485,263 bytes, SHA-256 matching the
sherpa-onnx `checksum.txt` of the `speaker-recongition-models` release) was downloaded once into a
local cache outside the repository. `prepare_sources.py --update-sources --offline` measured its
archive (26,487,296 bytes) and a second `--offline` run into a new output directory reproduced it with
an identical SHA-256 digest. `build_catalog.py` (schema 3) then built `catalog-v3.json` against
`history/v2/catalog-v2.json` in a temporary directory; the file, `release-assets.txt` and
`preparation.json` were moved into `pending/v3`, and `verify_catalog.py` accepted both pending
catalogs with the rebuild from sources (`catalog-v2.json` unchanged). No network publication took
place.

## Measured v3 analysis models (2026-10-29)

The four pinned upstream assets of the analysis models (378,379,086 bytes: the pyannote segmentation,
Whisper tiny and base and CED-mini archives) were downloaded once into a local cache outside the
repository; the three that the sherpa-onnx `checksum.txt` files list matched it, and the pyannote
archive, which has none, matched the release's size. `prepare_sources.py --update-sources --offline`
measured the four archives (279,054,336 bytes) and a second `--offline` run into a new output
directory reproduced them with identical SHA-256 digests. `build_catalog.py` (schema 3) then built
`catalog-v3.json` (30 models) against `history/v2/catalog-v2.json` in a temporary directory; the
file, `release-assets.txt` and `preparation.json` were moved into `pending/v3`, the schema 2 build
with the same sources reproduced `catalog-v2.json` byte for byte, and `verify_catalog.py` accepted both
pending catalogs with the rebuild from sources. No network publication took place.

## Measured v3 re-pin (2026-10-30)

Before release 3 was signed, three pinned upstream assets no longer matched GitHub: k2-fsa had replaced
`kokoro-int8-multi-lang-v1_0.tar.bz2` and `kokoro-multi-lang-v1_1.tar.bz2` on 2026-10-26 and
`matcha-icefall-zh-baker.tar.bz2` on 2026-10-29, while the other 28 pins still matched (plugin roadmap
Q118, Q119). The unpublished Kokoro v1.0 int8 version 1 was re-pinned in place; the published Kokoro v1.1
and Matcha zh-baker got version 2 (`sources/<modelId>/2/`) and keep version 1 unchanged.
`prepare_sources.py --update-sources --offline` measured the three archives (656,161,280 bytes);
`build_catalog.py` rebuilt both pending catalogs (`generatedAt` 2026-10-30) against
`history/v2/catalog-v2.json`, and `verify_catalog.py` accepted them with the rebuild from sources. A second
run from the pinned upstream assets reproduced all twelve release 3 archives (1,555,015,680 bytes) with
identical SHA-256 digests, and `verify_release.py` accepted them against `pending/v3/release-assets.txt`.

The publication workflow now handles a release with a companion catalog (an older schema's catalog with the
same `catalogVersion`, decision D127) and history directories that hold one catalog per schema. A local dry
run on a copy of the repository, with a disposable P-256 key standing in for the offline key, signed and
promoted both release 3 catalogs as in the family README, passed the tool tests, the workflow's input,
signature and reproduction steps, the archive check and the read-back with both catalogs. No network
publication took place.
