# AutoJs6 speech models

This asset family distributes reviewed sherpa-onnx speech models (speech recognition, keyword
spotting and text-to-speech) for the AutoJs6 plugin 3-Macaw Speech
(`AutoJs6-Plugin-Three-Macaw-Speech`, roadmap phase P2, decisions D9, D24 and D25). The plugin
bundles the sherpa-onnx runtime and the silero VAD model; every other model is downloaded on demand
from an immutable `speech-models-vN` GitHub Release of this repository, with the upstream sherpa-onnx
release asset as a fallback. Both paths end with the same file-level SHA-256 checks. A version can also
be upstream-only (`mirror` is null): the maintainer decided not to redistribute its weights, so no
archive is published and clients install it from the pinned sherpa-onnx asset alone.

The family has its own directory, catalog schemas, tools (`tools/speech-model-distribution/`),
workflow (`.github/workflows/publish-speech-models.yml`), release-tag prefix and ECDSA P-256 signing
key. Ace font and codegen model keys, catalogs and releases remain separate.

## Difference from codegen-models: no model binaries in Git

`codegen-models/` versions each reviewed package in Git. Speech models are 8-406 MB each, beyond the
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
  catalogs/catalog-v1.json          # current signed catalog (after the first promotion)
  catalogs/catalog-v1.sig.json      # detached offline signature
  catalogs/history/vN/              # exact earlier catalogs and signatures
  catalogs/pending/vN/              # reviewed candidates awaiting offline signing
  audits/license-audit-vN.json      # license evidence and commercialUse conclusions
  keys/catalog-signing-public.pem   # public key only
  schemas/                          # catalog, signature and model-source schemas
```

Schemas: [catalog](schemas/catalog-v1.schema.json), [signature](schemas/signature-v1.schema.json)
(the codegen envelope), [model source](schemas/model-source-v1.schema.json). Cross-field rules are
enforced by `tools/speech-model-distribution/distribution.py`.

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

Each model has stable `modelId` (prefixed by its kind: `asr.`, `kws.` or `tts.`), `kind`, localized
`displayName` and `summary` (at least `en` and `zh-CN`), `recommended`, `versions[]` and
`recommendedVersionCode`. Each immutable version records:

- `modelType`: `online-transducer`, `sense-voice`, `kws-transducer`, `vits`, `matcha` or `kokoro`, and
  `runtime.config` with the sherpa-onnx 1.13.8 file roles (for example `encoder`, `tokens`,
  `lexicon[]`, `ruleFsts[]`, `dataDir`) plus `modelType` `zipformer` or `zipformer2` for transducers.
- `languages`, `sampleRate`, and `speakers` for TTS models.
- `license`: `spdx` (license IDs or `LicenseRef-*`), `commercialUse` (`true`, `false` or `"unknown"`)
  and `noticeKey`, the plugin string shown before download (decision D11).
- `mirror`: the content-addressed Release archive (`fileName`, `format`, `size`, `sha256`, `url`), or
  `null` for an upstream-only version. Such a version has no Release archive at all: clients skip the
  mirror path and install from `upstream[]`, which must still cover exactly `files[]`.
- `upstream[]`: the sherpa-onnx release assets, each a `tar.bz2` with a `members` map from archive
  member to installed path, or a single `file`. Together they install exactly `files[]`.
- `files[]`: installed path, size and SHA-256 of every file, the final verification basis.
- `sourceUrl`: this version's source directory at the release tag that introduced it.

`LicenseRef-NoLicenseDeclared` marks weights whose publisher declares no license. The policy behind
`commercialUse` and every model's evidence links are in
[the license audit](audits/license-audit-v1.json).

## Version and integrity rules

- Catalog wire schema v1; `catalogVersion` increases by exactly one per release, the tag is
  `speech-models-vN`, and a signed catalog binds its repository.
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

`catalogs/pending/v1/` holds the reviewed, unsigned v1 candidate regenerated on 2026-10-16 from the
ten sources below (appendix A of the plugin roadmap). It is not signed or promoted yet, and no
`speech-models-v1` Release exists. Archive sizes are measured, and a second offline rebuild
reproduced all nine archives byte for byte. Two maintainer decisions of 2026-10-16 shaped this
candidate:

- The Chinese streaming model of 2025 stays in the catalog but is upstream-only (`mirror` null):
  no license is declared for its weights and the original repository is gated, so this repository
  does not redistribute it.
- The SenseVoice entry is the official FunAudioLLM export of 2024-07-17 (FunASR Model Open Source
  License Agreement 1.1, commercial use permitted, punctuation supported). It replaced the Cantonese
  fine-tune export `asr.sense-voice.zh-en-ja-ko-yue.2025-09-09.int8` (WenetSpeech-Yue, CC BY-NC 4.0);
  the pending catalog was unsigned, so that source directory was removed rather than revoked.

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

## Maintainer signing and publication (roadmap P2.5)

Run from the repository root on the machine that holds the offline key
`D:/offline-keys/speech-models.private.pem`. The tools need Python 3.12 or newer and OpenSSL; signing
refuses a private key inside any Git working tree and a catalog that fails validation.

1. Re-check the reviewed candidate against its sources, then sign the exact bytes:

   ```powershell
   $keyId = 'p256-bf5f0f579c7fbef1'
   $repo = 'SuperMonster003/AutoJs6-Shared-Assets'
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v1/catalog-v1.json --expected-repository $repo --source-root speech-models/sources
   python tools/speech-model-distribution/sign_catalog.py speech-models/catalogs/pending/v1/catalog-v1.json --private-key D:/offline-keys/speech-models.private.pem --output speech-models/catalogs/pending/v1/catalog-v1.sig.json --key-id $keyId --expected-repository $repo
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/pending/v1/catalog-v1.json --signature speech-models/catalogs/pending/v1/catalog-v1.sig.json --public-key speech-models/keys/catalog-signing-public.pem --expected-key-id $keyId --expected-repository $repo --source-root speech-models/sources
   ```

2. Promote the identical bytes (never reformat a signed catalog) and verify the promoted pair:

   ```powershell
   Copy-Item speech-models/catalogs/pending/v1/catalog-v1.json speech-models/catalogs/catalog-v1.json
   Copy-Item speech-models/catalogs/pending/v1/catalog-v1.sig.json speech-models/catalogs/catalog-v1.sig.json
   python tools/speech-model-distribution/verify_catalog.py speech-models/catalogs/catalog-v1.json --signature speech-models/catalogs/catalog-v1.sig.json --public-key speech-models/keys/catalog-signing-public.pem --expected-key-id $keyId --expected-repository $repo --source-root speech-models/sources
   ```

3. Optionally reproduce and verify the release archives locally (about 2 GB of upstream downloads,
   cached in `build/speech-models/upstream/`):

   ```powershell
   python tools/speech-model-distribution/prepare_sources.py --catalog speech-models/catalogs/catalog-v1.json --output-dir build/speech-models/release-v1
   python tools/speech-model-distribution/verify_release.py speech-models/catalogs/catalog-v1.json --assets-dir build/speech-models/release-v1 --asset-list speech-models/catalogs/pending/v1/release-assets.txt --expected-repository $repo
   ```

4. Commit the signature and the promoted pair, confirm that the diff contains no private key, and push.
   Create the GitHub environment `speech-models-release` and keep Immutable Releases enabled.

5. Dispatch the workflow from `main` with the exact tag and key ID:

   ```powershell
   gh workflow run publish-speech-models.yml --repo SuperMonster003/AutoJs6-Shared-Assets --ref main -f release_tag=speech-models-v1 -f key_id=p256-bf5f0f579c7fbef1
   ```

   The workflow runs the tool tests, verifies the signature and history, rebuilds the catalog from the
   sources and compares bytes, re-downloads the pinned upstream assets and rebuilds the nine archives
   named in `release-assets.txt` (upstream-only versions are skipped), confirms that neither the tag
   nor the Release exists, publishes the archives with the catalog and signature, then downloads
   everything again and verifies it. It never overwrites an existing tag or Release; a failure after
   tag creation needs manual inspection.

6. Record the Release URL, the archive count (9, plus 1 upstream-only version), the total size and the
   key ID in the plugin roadmap (P2.5), and copy the exact signed catalog, signature and public key
   into the plugin (P2.4).

Tool details, adding a model version and local checks: [tools README](../tools/speech-model-distribution/README.md).
