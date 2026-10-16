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
| `verify_release.py` | Verify release archives by name, size, SHA-256 and USTAR content, or confirm remote tag and Release absence. |
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
   build the next candidate:

   ```powershell
   python tools/speech-model-distribution/build_catalog.py --source-root speech-models/sources --output speech-models/catalogs/pending/v<N> --catalog-version <N> --generated-at <review time, UTC> --previous-catalog speech-models/catalogs/history/v<N-1>/catalog-v1.json
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v<N>/catalog-v1.json --previous-catalog speech-models/catalogs/history/v<N-1>/catalog-v1.json --expected-repository SuperMonster003/AutoJs6-Shared-Assets --source-root speech-models/sources
   ```

5. Sign, promote and publish as in the family README, using tag `speech-models-v<N>`.

`build_catalog.py` never overwrites an output directory. Model-level `displayName`, `summary` and
`recommended` follow the newest source of each model; version-level data is carried unchanged from the
previous catalog and must still match its source.

## Local checks

```powershell
python -m unittest discover -s tools/speech-model-distribution/tests -v
python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v1/catalog-v1.json --expected-repository SuperMonster003/AutoJs6-Shared-Assets --source-root speech-models/sources
python tools/speech-model-distribution/check_docs.py
```

The tests use synthetic upstream archives, fake HTTP responses and disposable OpenSSL keys in
temporary directories; they need no network and no real model. They cover the archive format, source
and catalog validation, history rules, repacking, the downloader, signatures, release verification,
the remote preflight, the workflow contract and the checked-in v1 data.

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
