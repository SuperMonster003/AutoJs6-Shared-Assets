# AutoJs6 speech models

This asset family distributes reviewed sherpa-onnx speech models (speech recognition, keyword
spotting, text-to-speech, since catalog v2 punctuation and since catalog schema 3 speaker embedding)
for the AutoJs6 plugin 3-Macaw Speech (`AutoJs6-Plugin-Three-Macaw-Speech`, roadmap phases P2, P7.7,
P8.2 and P8.3, decisions D9, D24, D25, D102-D109, D124, D127, D131 and D137). The plugin
bundles the sherpa-onnx runtime and the silero VAD model; every other model is downloaded on demand
from an immutable `speech-models-vN` GitHub Release of this repository, with the upstream sherpa-onnx
release asset as a fallback. Both paths end with the same file-level SHA-256 checks. A version can also
be upstream-only (`mirror` is null): the maintainer decided not to redistribute its weights, so no
archive is published and clients install it from the pinned sherpa-onnx asset alone.

The family has its own directory, catalog schemas, tools (`tools/speech-model-distribution/`),
workflow (`.github/workflows/publish-speech-models.yml`), release-tag prefix and ECDSA P-256 signing
key. Ace font and codegen model keys, catalogs and releases remain separate.

## Difference from codegen-models: no model binaries in Git

`codegen-models/` versions each reviewed package in Git. Speech models are 7-406 MB each, beyond the
GitHub 100 MB file limit, and this repository deliberately avoids Git LFS. Therefore
`sources/<modelId>/<versionCode>/` holds only reviewed text:

- `source.json`: catalog metadata, the pinned upstream release assets (URL, size, SHA-256), the
  archive members that are kept and their installed paths, the sherpa-onnx file roles, the license
  summary, whether the version is mirrored (`mirror`), and the measured mirror archive and
  installed-file digests (`archive` stays null for an upstream-only version; `files` is measured
  either way).
- `MODEL_CARD.md`: origin, training data, what was repacked or omitted, and known limits.
- `LICENSE` and `LICENSE-*`: the license texts for the weights and bundled components, or a notice
  when the publisher declares no license.

`prepare_sources.py` downloads the pinned upstream assets into the ignored `build/` directory,
verifies their SHA-256, and repacks the selected members into one content-addressed archive per model
version. The release workflow repeats that reproduction from the same pins before publishing, so the
Release bytes can always be traced to public upstream bytes plus the reviewed member list.

## Layout

```text
speech-models/
  sources/<modelId>/<versionCode>/  # source.json, MODEL_CARD.md, LICENSE files (text only)
  catalogs/catalog-vS.json          # newest signed catalog of wire schema S, with catalog-vS.sig.json
  catalogs/history/vN/              # exact catalog and signature of release N (catalog-vS.json)
  catalogs/pending/vN/              # reviewed candidates awaiting offline signing
  audits/license-audit-vN.json      # license evidence and commercialUse conclusions
  keys/catalog-signing-public.pem   # public key only
  schemas/                          # catalog, signature and model-source schemas
```

The catalog file name follows the wire schema, not the release: schema 1 is `catalog-v1.json`,
schema 2 is `catalog-v2.json`, schema 3 is `catalog-v3.json`. A plugin reads the newest file name it
understands, so `catalogs/catalog-v1.json` stays frozen at release 1 for plugins that know only
schema 1, and a copy of it in `catalogs/history/v1/` proves the frozen bytes are the signed ones.
Release N always keeps its catalog in `catalogs/history/vN/` once release N+1 is prepared. From
release 3 on a release may publish catalogs of two schemas (decision D127): the older one is built
from the same sources with `build_catalog.py --schema` and leaves out the versions that need the newer
schema, so `catalog-v2.json` keeps serving plugins 1.2.0 and older without the speaker kind.

Schemas: catalog [v3](schemas/catalog-v3.schema.json), the frozen [v2](schemas/catalog-v2.schema.json)
and [v1](schemas/catalog-v1.schema.json), signature [v3](schemas/signature-v3.schema.json),
[v2](schemas/signature-v2.schema.json) and [v1](schemas/signature-v1.schema.json) (the codegen
envelope, differing only in the catalog file name), [model source](schemas/model-source-v1.schema.json).
Cross-field rules are enforced by `tools/speech-model-distribution/distribution.py`.

## Mirror archive format

Roadmap appendix D Q3 is decided as an uncompressed tar (option a). Model weights barely compress,
an uncompressed tar unpacks in one sequential pass on Android, and a fixed USTAR layout can be written
byte for byte by a small standard-library writer, independent of zlib, bzip2 or Python versions.

- File name: `autojs6-speech-<modelId>-v<versionCode>-<first 8 hex of SHA-256>.tar`.
- Members: regular files only, sorted by path, no directory entries, mode 0644, uid and gid 0, mtime 0,
  empty owner names, POSIX `ustar` magic; paths longer than 100 bytes use the USTAR prefix field.
- Size: 512 bytes of header plus the file rounded up to 512 bytes for every file, then two zero blocks.
  Validators compute this size from `files[]` and reject any other archive.

## Catalog entries

Each model has stable `modelId` (prefixed by its kind: `asr.`, `kws.`, `punct.`, `speaker.` or
`tts.`), `kind`, localized `displayName` and `summary` (at least `en` and `zh-CN`), `recommended`,
`versions[]` and `recommendedVersionCode`. Each immutable version records:

- `modelType`: `online-transducer`, `sense-voice`, `kws-transducer`, `vits`, `matcha`, `kokoro`, and
  since schema 2 the punctuation types `ct-transformer` and `cnn-bilstm` and the offline recognizer
  type `offline-transducer`, with `runtime.config` holding the sherpa-onnx 1.13.8 file roles (for
  example `encoder`, `tokens`, `lexicon[]`, `ruleFsts[]`, `dataDir`, `bpeVocab`) plus `modelType`:
  `zipformer` or `zipformer2` for streaming transducers, `nemo_transducer` for `offline-transducer`.
  Since schema 3 the speaker kind has the type `speaker-embedding`, one `model` file that turns
  speech into a voiceprint vector (sherpa-onnx `SpeakerEmbeddingExtractorConfig`).
- `languages`, `sampleRate` (absent for punctuation models, which take text), and `speakers` for TTS
  models.
- `license`: `spdx` (license IDs or `LicenseRef-*`), `commercialUse` (`true`, `false` or `"unknown"`)
  and `noticeKey`, the plugin string shown before download (decision D11).
- `mirror`: the content-addressed Release archive (`fileName`, `format`, `size`, `sha256`, `url`), or
  `null` for an upstream-only version. Such a version has no Release archive at all: clients skip the
  mirror path and install from `upstream[]`, which must still cover exactly `files[]`.
- `upstream[]`: the sherpa-onnx release assets, each a `tar.bz2` with a `members` map from archive
  member to installed path, or a single `file`. Together they install exactly `files[]`. Since schema
  2 a member name may start with `./` (an archive packed from `.`); installed paths never do.
- `files[]`: installed path, size and SHA-256 of every file, the final verification basis.
- `sourceUrl`: this version's source directory at the release tag that introduced it.

`LicenseRef-NoLicenseDeclared` marks weights whose publisher declares no license. The policy behind
`commercialUse` and every model's evidence links are in the license audit of each release:
[v3](audits/license-audit-v3.json) (pending), [v2](audits/license-audit-v2.json) (current) and
[v1](audits/license-audit-v1.json).

## Version and integrity rules

- Catalog wire schema 3 (schema 2 for release 2, schema 1 for release 1); `catalogVersion` increases
  by exactly one per release, the tag is `speech-models-vN`, and a signed catalog binds its repository.
  A catalog may carry over versions of an older schema, but kinds, model types and member names
  introduced by a newer schema are refused in an older one; an older schema's catalog of the same
  release leaves those versions out.
- A published `(modelId, versionCode)` never changes. Only `deprecated` and `revoked` may be added,
  and only toward true; `recommendedVersionCode` is the newest active version or null.
- New versions of a model use a higher `versionCode`. Unchanged versions keep their original Release
  URL, so each release uploads only the archives it introduces (`release-assets.txt`).
- `mirror` is part of the immutable version: a published version can neither gain nor lose its
  archive. Upstream-only versions (`mirror` null) never appear in `release-assets.txt`; the rebuild
  and release checks skip them, while `prepare_sources.py` still measures their `files[]` from the
  upstream members so that the upstream install stays verifiable.
- Clients verify the detached signature over the exact catalog bytes, refuse catalog rollback, then
  check archive size and SHA-256 before unpacking and every installed file afterwards. For an
  upstream-only version they check the upstream asset's size and SHA-256 instead, then the files.

## Current state

Release 1 (`speech-models-v1`) is signed and published; its catalog is `catalogs/catalog-v1.json`
with an identical copy in `catalogs/history/v1/`. Release 2's reviewed catalog of 2026-10-23
(`catalog-v2.json`, schema 2, plugin roadmap P7.7) is signed with `p256-bf5f0f579c7fbef1` and
promoted to `catalogs/catalog-v2.json` with `catalogs/catalog-v2.sig.json`. Both are byte-identical
to the reviewed files in `catalogs/pending/v2/`; `preparation.json` retains the original unsigned
preparation record. The release workflow below publishes the eight new archives and the signed
catalog as `speech-models-v2`, then downloads and verifies every published asset.

Release 3 is being collected in `catalogs/pending/v3/` (plugin roadmap D127): the signed release 2
catalog is kept in `catalogs/history/v2/`, and the unsigned `pending/v3/catalog-v2.json`
(`catalogVersion` 3) adds the plugin's 1.3.0 language models, which use existing kinds only. The
schema 3 `pending/v3/catalog-v3.json` next to it lists the same versions plus the new kinds (P8.3:
`speaker`; later phases may add more); the maintainer signs both and publishes them together as
`speech-models-v3`. `release-assets.txt` and `preparation.json` describe `catalog-v3.json`, whose
archives include every archive of `catalog-v2.json`.

### Catalog v3 (pending)

The pending catalogs carry the 19 release 2 models unchanged. `catalog-v2.json` adds six versions
chosen by the maintainer on 2026-10-25 (plugin roadmap D131, Q79-Q85); `catalog-v3.json` also adds the
speaker embedding model chosen on 2026-10-26 (D137, Q93). The six archives were measured from the
pinned upstream assets and reproduced byte for byte by a second offline run.

- The Spanish recognizer is offline: sherpa-onnx `OfflineTransducerModelConfig` with model type
  `nemo_transducer`, added to schema 2 as `offline-transducer`. Plugins 1.2.0 and older skip this
  version as an unknown type (plugin decision D106).
- PengChengStarling names no training data, so it fails the catalog gate (D124); the maintainer took
  it as an exception with commercialUse `unknown` and the new notice key
  `speech_model_license_unknown_data`. Older plugins show their generic unknown-license notice.
- The Arabic miro V2 voice is upstream-only: the voice and its data are CC BY-NC-ND 4.0, and the
  sherpa-onnx export rewrites its ONNX metadata.
- The speaker model (3D-Speaker ERes2Net trained on VoxCeleb2) is the only version of the new kind
  `speaker` and appears in `catalog-v3.json` only. The more accurate CAM++ zh-en model was not taken
  because its training data is not named (D124).

| Model ID | Archive | License expression | commercialUse |
| --- | ---: | --- | --- |
| `asr.nemo-transducer.es.2026-05-03.int8` | 136.5 MB | `CC-BY-4.0` | true |
| `asr.zipformer-streaming.ar-en-id-ja-ru-th-vi-zh.2025-02-10.int8` | 338.9 MB | `Apache-2.0` | unknown |
| `tts.kokoro.multi-lang.v1_0.int8` | 169.2 MB | `Apache-2.0 AND GPL-3.0-or-later` | true |
| `tts.vits.mimic3.ko-ko-kss-low` | 81.1 MB | `CC0-1.0 AND GPL-3.0-or-later` | false |
| `tts.vits.piper.ar-jo-sa-dii-high.int8` | 36.9 MB | `CC-BY-NC-SA-4.0 AND GPL-3.0-or-later` | false |
| `tts.vits.piper.ar-jo-sa-miro-v2-high.int8` | upstream only (36.6 MB installed) | `CC-BY-NC-ND-4.0 AND GPL-3.0-or-later` | false |
| `speaker.eres2net.3dspeaker.en-voxceleb` | 26.5 MB (schema 3 only) | `Apache-2.0` | true |

The six new archives total 789,041,664 bytes (`pending/v3/release-assets.txt`; 762,554,368 bytes
without the speaker model). `catalog-v3.json` then lists 26 models and `catalog-v2.json` 25, three of
them upstream-only.

### Catalog v2

Release 2 carries the ten release 1 models unchanged (their archives stay on `speech-models-v1`) and
adds nine versions. Its archives were measured from the pinned upstream assets and reproduced byte
for byte by a second offline run. Maintainer decisions of 2026-10-22 (plugin roadmap D102-D109):

- New file name `catalog-v2.json` for schema 2, so that older plugins keep reading the frozen
  `catalog-v1.json` and never meet the `punct` kind.
- The four new Piper voices are fine-tuned from the lessac checkpoint, whose Lessac Blizzard 2013
  data is licensed for research only, so they are marked commercialUse false by lineage.
- The Korean streaming model is upstream-only: the KsponSpeech terms restrict use outside Korea, so
  this repository does not redistribute its weights.

| Model ID | Archive | License expression | commercialUse |
| --- | ---: | --- | --- |
| `asr.zipformer-streaming.fr.2023-04-14.int8` | 129.0 MB | `Apache-2.0` | true |
| `asr.zipformer-streaming.ko.2024-06-16.int8` | upstream only (140.9 MB installed) | `Apache-2.0` | false |
| `asr.zipformer-streaming.ru.2025-08-16.int8` | 28.6 MB | `Apache-2.0` | true |
| `punct.cnn-bilstm.en.2024-08-06.int8` | 7.6 MB | `Apache-2.0` | true |
| `punct.ct-transformer.zh-en.2024-04-12.int8` | 75.5 MB | `Apache-2.0` | true |
| `tts.vits.piper.de-de-thorsten-medium.int8` | 36.9 MB | `MIT AND GPL-3.0-or-later` | false |
| `tts.vits.piper.es-es-davefx-medium.int8` | 36.9 MB | `MIT AND GPL-3.0-or-later` | false |
| `tts.vits.piper.fr-fr-siwis-medium.int8` | 36.9 MB | `MIT AND GPL-3.0-or-later` | false |
| `tts.vits.piper.ru-ru-denis-medium.int8` | 36.9 MB | `MIT AND GPL-3.0-or-later` | false |

The eight new archives total 388,244,480 bytes (`pending/v2/release-assets.txt`); the Korean
upstream-only version adds no Release asset. The catalog then lists 19 models, two of them
upstream-only.

### Release 1 models

Release 1 was prepared from the ten sources below (appendix A of the plugin roadmap). Two maintainer
decisions of 2026-10-16 shaped it:

- The Chinese streaming model of 2025 stays in the catalog but is upstream-only (`mirror` null):
  no license is declared for its weights and the original repository is gated, so this repository
  does not redistribute it.
- The SenseVoice entry is the official FunAudioLLM export of 2024-07-17 (FunASR Model Open Source
  License Agreement 1.1, commercial use permitted, punctuation supported). It replaced the Cantonese
  fine-tune export `asr.sense-voice.zh-en-ja-ko-yue.2025-09-09.int8` (WenetSpeech-Yue, CC BY-NC 4.0);
  the candidate was still unsigned, so that source directory was removed rather than revoked.

| Model ID | Archive | License expression | commercialUse |
| --- | ---: | --- | --- |
| `asr.sense-voice.zh-en-ja-ko-yue.2024-07-17.int8` | 239.6 MB | `LicenseRef-FunASR-Model-License-1.1` | true |
| `asr.zipformer-streaming.en.2023-06-26.int8` | 70.3 MB | `Apache-2.0` | true |
| `asr.zipformer-streaming.zh-en.2023-02-20.int8` | 199.1 MB | `Apache-2.0` | true |
| `asr.zipformer-streaming.zh.2025-06-30.int8` | upstream only (167.4 MB installed) | `LicenseRef-NoLicenseDeclared` | false |
| `kws.zipformer.zh-en.2025-12-20` | 8.8 MB | `Apache-2.0` | true |
| `tts.kokoro.multi-lang.v1_1` | 406.0 MB | `Apache-2.0 AND GPL-3.0-or-later` | true |
| `tts.matcha.icefall.zh-baker` | 81.0 MB | `LicenseRef-NoLicenseDeclared AND MIT` | false |
| `tts.vits.icefall.zh-aishell3` | 32.8 MB | `LicenseRef-NoLicenseDeclared` | unknown |
| `tts.vits.melo.zh-en` | 177.4 MB | `MIT` | true |
| `tts.vits.piper.en-us-lessac-medium` | 81.4 MB | `MIT AND GPL-3.0-or-later` | false |

The nine archives total 1,296,362,496 bytes (`release-assets.txt`); the upstream-only version adds
no Release asset. `GPL-3.0-or-later` covers the compiled eSpeak NG data used by Kokoro and Piper for
phonemization.

## Signing key

- Family key generated on 2026-10-16 with `tools/codegen-model-distribution/generate_keys.py`
  (ECDSA P-256, OpenSSL 3.2.1). The private key stays outside every Git working tree; the
  Ace font and codegen model keys are not reused.
- Key ID: `p256-bf5f0f579c7fbef1`.
- SPKI DER SHA-256: `bf5f0f579c7fbef188e81a02257fc3336189020273b2c69c69092cc402214f68`.
- Public key: `keys/catalog-signing-public.pem`.

Verify the checked-in public key:

```text
openssl pkey -pubin -in speech-models/keys/catalog-signing-public.pem -outform DER | openssl dgst -sha256
```

## Maintainer signing and publication (roadmap P2.5, P7.7)

Run from the repository root on the machine that holds the offline key
`D:/offline-keys/speech-models.private.pem`. The tools need Python 3.12 or newer and OpenSSL; signing
refuses a private key inside any Git working tree and a catalog that fails validation. Sign from a
normal PowerShell window, not an elevated Administrator one: files written there belong to
Administrators, and in a directory with a restricted DACL neither Git nor the tests can read them.
The steps below publish release 2; release 1 used the same steps with `v1` paths and no previous
catalog.

1. Re-check the reviewed candidate against its sources and release 1, then sign the exact bytes:

   ```powershell
   $keyId = 'p256-bf5f0f579c7fbef1'
   $repo = 'SuperMonster003/AutoJs6-Shared-Assets'
   $previous = 'speech-models/catalogs/history/v1/catalog-v1.json'
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v2/catalog-v2.json --previous-catalog $previous --minimum-catalog-version 2 --expected-repository $repo --source-root speech-models/sources
   python tools/speech-model-distribution/sign_catalog.py speech-models/catalogs/pending/v2/catalog-v2.json --private-key D:/offline-keys/speech-models.private.pem --output speech-models/catalogs/pending/v2/catalog-v2.sig.json --key-id $keyId --expected-repository $repo
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v2/catalog-v2.json --signature speech-models/catalogs/pending/v2/catalog-v2.sig.json --public-key speech-models/keys/catalog-signing-public.pem --expected-key-id $keyId --previous-catalog $previous --minimum-catalog-version 2 --expected-repository $repo --source-root speech-models/sources
   ```

2. Promote the identical bytes (never reformat a signed catalog) and verify the promoted pair. Leave
   `catalogs/catalog-v1.json` and its signature untouched: they stay frozen at release 1.

   ```powershell
   Copy-Item speech-models/catalogs/pending/v2/catalog-v2.json speech-models/catalogs/catalog-v2.json
   Copy-Item speech-models/catalogs/pending/v2/catalog-v2.sig.json speech-models/catalogs/catalog-v2.sig.json
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/catalog-v2.json --signature speech-models/catalogs/catalog-v2.sig.json --public-key speech-models/keys/catalog-signing-public.pem --expected-key-id $keyId --previous-catalog $previous --minimum-catalog-version 2 --expected-repository $repo --source-root speech-models/sources
   ```

3. Optionally reproduce and verify the eight new archives locally (about 1 GB of upstream downloads,
   cached in `build/speech-models/upstream/`):

   ```powershell
   python tools/speech-model-distribution/prepare_sources.py --catalog speech-models/catalogs/catalog-v2.json --output-dir build/speech-models/release-v2
   python tools/speech-model-distribution/verify_release.py speech-models/catalogs/catalog-v2.json --assets-dir build/speech-models/release-v2 --asset-list speech-models/catalogs/pending/v2/release-assets.txt --expected-repository $repo
   ```

4. Commit the signature and the promoted pair, confirm that the diff contains no private key, and push.
   The GitHub environment `speech-models-release` exists since release 1; keep Immutable Releases
   enabled.

5. Dispatch the workflow from `main` with the exact tag and key ID:

   ```powershell
   gh workflow run publish-speech-models.yml --repo SuperMonster003/AutoJs6-Shared-Assets --ref main -f release_tag=speech-models-v2 -f key_id=p256-bf5f0f579c7fbef1
   ```

   The workflow runs the tool tests, checks that every frozen catalog equals its history copy, verifies
   the current and historical signatures, rebuilds the catalog from the sources against the previous
   release and compares bytes, re-downloads the pinned upstream assets and rebuilds the archives named
   in `release-assets.txt` (only the ones this release introduces; upstream-only versions are
   skipped), confirms that neither the tag nor the Release exists, publishes the archives with the
   catalog and signature, then downloads everything again and verifies it. It never overwrites an
   existing tag or Release; a failure after tag creation needs manual inspection.

6. Record the Release URL, the archive count (8 new, plus the Korean upstream-only version), the total
   size and the key ID in the plugin roadmap (P7.7), and replace the plugin's bundled pending catalog
   with the exact signed catalog and signature.

Release 3 differs: it publishes two catalogs (plugin roadmap D127), the schema 3 `catalog-v3.json`
and a re-signed `catalog-v2.json` with `catalogVersion` 3, while the workflow above still expects one
current catalog and requires every other `catalog-v*.json` to equal a history copy. Adapting the
workflow and these steps belongs to the plugin phase that adds `catalog-v3.json`; until then
`pending/v3/` is reviewed and tested but not signed.

Tool details, adding a model version and local checks: [tools README](../tools/speech-model-distribution/README.md).
