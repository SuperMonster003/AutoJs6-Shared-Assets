# Code-generation model distribution tools

These Python 3.12 tools prepare and verify the independent `codegen-models/` asset family.
They need only the standard library and OpenSSL for P-256 operations. They do not need an
AutoJs6 checkout, CatBoost, an Android SDK or the training dataset. The GitHub workflow also
uses the runner's `gh` CLI. Run commands from this repository's root.

Signing and workflow dispatch are maintainer operations. The workflow receives a public
key and already signed bytes; it never receives the private key. The pending production v1
catalog contains no models and has now been signed by the maintainer for APK-only bootstrap
use. The model public key ID is `p256-f1a540e052cf0865`; the complete SPKI fingerprint is in
`codegen-models/README.md`. The bootstrap is not promoted to a remote current catalog or
Release, so the first official model still uses `codegen-models-v1`.

## Source inputs and catalog policy

Each `codegen-models/sources/<modelId>/<versionCode>/` directory contains exactly one
`.ajcgm`, its exact `MODEL_CARD.md`, a reviewed aggregate `dataset-manifest.json`, and:

```json
{
  "format": 1,
  "summary": {"en": "Reviewed description", "zh-CN": "已审核的模型说明"},
  "releasedAt": "2026-10-03T00:00:00Z"
}
```

This `source.json` may additionally set `deprecated` or `revoked` to true. Status changes
are one-way. Versions remain in the catalog, keep their original immutable artifact URL
and metadata, and are excluded from recommendations when disabled. If all versions are
disabled, `recommendedVersionCode` is null. Only the model-level display name and summary
may change independently of immutable version metadata.

The dataset manifest must match the package's dataset ID, creation time and usable training
group count. Public copies may remove device serials and retain `sourceManifestSha256` for
the original manifest. Do not copy layouts, raw selectors or unreviewed private data here.

Every new production package needs `gate.json`, produced by the host's P8.1 publication
gate, containing `format: 1`, `passed: true`, and `packageSha256` equal to the full package
digest. These tools consume that result; they do not invent passing evaluation results.
`LicenseRef-LocalEvaluation` packages cannot be published. A maintainer must establish the
actual model/data license before adding the first production source.

The only gate exception is `autojs6.codegen.tiny-test`, with explicit `--allow-test-models`
in a separate fork/private repository. That flag is rejected for the canonical repository,
including differently cased spellings. Production source scans exclude the checked-in
tiny fixture and report the exclusion in `preparation.json`; all other sources remain
subject to the gate. An empty result requires explicit `--empty-bootstrap`.

## Offline key and reviewed pending catalog

Generate a **new** model key on the maintainer's offline machine. The tools reject Ace's
existing signing keys, private-key paths inside Git worktrees, and existing output files.
An explicit `--openssl` executable path is accepted if OpenSSL is not discoverable.

```powershell
python tools/codegen-model-distribution/generate_keys.py --private-key D:/offline-keys/codegen.private.pem --public-key-pem codegen-models/keys/catalog-signing-public.pem --public-key-der D:/offline-keys/codegen-public.der
```

Record the printed `p256-<first 16 hex characters of SPKI SHA-256>` key ID and full public
key fingerprint independently. Keep the private key offline; provide only the public
material and signed catalog to the host maintainer.

For a first **real release**, prepare a fresh directory from the approved production
sources. Choose the review timestamp explicitly and keep it for reproduction:

```powershell
python tools/codegen-model-distribution/prepare_catalog.py --source-root codegen-models/sources --output build/codegen-reviewed-v1 --repository SuperMonster003/AutoJs6-Shared-Assets --catalog-version 1 --generated-at 2026-10-03T11:12:51Z
python tools/codegen-model-distribution/validate_catalog.py build/codegen-reviewed-v1/catalog-v1.json --expected-repository SuperMonster003/AutoJs6-Shared-Assets
```

Replace that example timestamp with the actual review time. For vN after v1, pass
`--previous-catalog codegen-models/catalogs/history/v<N-1>/catalog-v1.json`. Preparation
requires exactly one catalog-version increment. Old model assets retain their original
URLs, so the new `assets/` and `release-assets.txt` contain only newly introduced packages.
Existing output directories are never overwritten; use a new review directory.

The checked-in `catalogs/pending/v1/` is an **empty bootstrap proposal**, prepared with:

```powershell
python tools/codegen-model-distribution/prepare_catalog.py --source-root codegen-models/sources --output build/codegen-empty-bootstrap-v1 --repository SuperMonster003/AutoJs6-Shared-Assets --catalog-version 1 --generated-at 2026-10-03T11:12:51Z --empty-bootstrap
```

It can be signed for APK-only offline bootstrap use. Do not promote or dispatch this empty
proposal as a remote release: the roadmap reserves `codegen-models-v1` for the first approved
official model. Host bootstrap is display-only and does not establish a remote catalog
version watermark. Once a remote v1 is accepted, different remote v1 bytes are rejected.

Sign exactly the reviewed bytes; substituting the actual printed key ID is required:

```powershell
$modelKeyId = '<recorded model key ID>'
python tools/codegen-model-distribution/sign_catalog.py build/codegen-reviewed-v1/catalog-v1.json --private-key D:/offline-keys/codegen.private.pem --output build/codegen-reviewed-v1/catalog-v1.sig.json --key-id $modelKeyId --expected-repository SuperMonster003/AutoJs6-Shared-Assets
python tools/codegen-model-distribution/verify_catalog.py build/codegen-reviewed-v1/catalog-v1.json --signature build/codegen-reviewed-v1/catalog-v1.sig.json --public-key codegen-models/keys/catalog-signing-public.pem --expected-key-id $modelKeyId --expected-repository SuperMonster003/AutoJs6-Shared-Assets
python tools/codegen-model-distribution/verify_release.py build/codegen-reviewed-v1/catalog-v1.json --assets-dir build/codegen-reviewed-v1/assets --asset-list build/codegen-reviewed-v1/release-assets.txt --expected-repository SuperMonster003/AutoJs6-Shared-Assets
```

For the empty bootstrap, use `codegen-models/catalogs/pending/v1` as the catalog/signature
directory instead. Whitespace, newline and field ordering are signed bytes: do not format
or reserialize a catalog after signing. The envelope uses Ace's existing four-field format:
`algorithm`, `catalog`, `keyId`, `signature` (Base64 DER signature).

## Promote and dispatch a reviewed release

Before a release, preserve the previous current catalog/signature under `catalogs/history/vN/`.
Copy the newly verified pair without modification to `catalogs/catalog-v1.json` and
`catalogs/catalog-v1.sig.json`; put the same reviewed pair under the matching pending version.
For the first real v1, replace the unsigned empty proposal with that reviewed real v1 pair.
Commit the public key, source inputs and reviewed catalogs together with the required tool
changes. Verify the staged diff contains no private key. Do not put prepared `assets/` copies
into Git: their source package is already versioned, and the workflow reproduces them.

After reviewing the commit, the maintainer configures the `codegen-models-release` GitHub
environment and dispatches `publish-codegen-models.yml` from the default branch with
`release_tag` and `key_id`. Production uses `allow_test_models=false`. The workflow verifies
all historical signatures, reproduces the exact catalog, validates new assets, confirms
authenticated absence of both tag and Release, creates an immutable draft release, uploads,
publishes and downloads every asset for byte/hash/package/signature verification. It refuses
to overwrite an existing tag or Release. A failure after tag creation requires maintainer
inspection; blindly repeating dispatch cannot replace a partial release.

For P5.4 acceptance, first use a fork/private test repository and tiny-test with a disposable
test key. Prepare/sign/verify with `--repository <owner/test-repository>` and
`--allow-test-models`, promote only inside that repository, then dispatch with
`allow_test_models=true`. Save the resulting workflow run URL and asset hashes. Local tests
and simulated readback do not substitute for this remote E2 evidence.

## Prepare the host bootstrap pair

Verify the supplied public key fingerprint with the maintainer, then stage the two files:

```powershell
python tools/codegen-model-distribution/prepare_bootstrap.py --catalog codegen-models/catalogs/pending/v1/catalog-v1.json --signature codegen-models/catalogs/pending/v1/catalog-v1.sig.json --public-key codegen-models/keys/catalog-signing-public.pem --expected-key-id $modelKeyId --expected-repository SuperMonster003/AutoJs6-Shared-Assets --out-dir build/codegen-host-bootstrap
```

The output is `codegen_model_catalog_public_key_v1.der` and `codegen_model_catalog_v1.json`.
The latter is `{format: 1, catalogBase64: <exact signed bytes>, signature: <envelope object>}`.
The host decodes and verifies the original bytes; it must not reserialize the signed catalog.
After inspecting these files, rerun with `--host-root D:/idea-projects/AutoJs6` to install only
that pair into `app/src/main/res/raw/`. Verification precedes installation. A failed second
replacement rolls back the first; blocked rollback retains recovery files. A process crash
between the two renames can leave a mismatched pair, which host signature checking rejects.

Test-repository bootstraps may be staged with `--allow-test-models`, but cannot be installed
into main host resources. Keep test fixtures in `src/test/` or the eventual debug source set.
Directly staging into host main resources is rejected to preserve this installation check.

## Local checks and present acceptance status

```powershell
python -m unittest discover tools/codegen-model-distribution -v
```

Tests cover package bounds and malformed ZIP/model data, catalog/history invariants, gates,
deterministic preparation, real OpenSSL signing, exact-byte tampering, wrong keys, bootstrap
rollback, actual tiny-package release verification, authentication failures and workflow
ordering. Tests create private keys in temporary directories and remove them afterward.

On 2026-10-03, 63 tests passed. An additional local CLI round trip prepared the checked-in
tiny source twice with identical catalog bytes, signed with a disposable key, verified and
staged the bootstrap, rejected appended-byte tampering, and verified copied release assets
and signatures. It performed no network publication. The maintainer subsequently supplied
the production public key and signed empty bootstrap. Both OpenSSL and the host Kotlin
verifier accepted the signature, and the verified two-file resource pair was installed
locally in the host for P5.5.

On 2026-10-04 (Asia/Shanghai), the maintainer completed
[workflow run 37138706446](https://github.com/SuperMonster003/AutoJs6-Codegen-Distribution-Test/actions/runs/37138706446)
with all 63 CI tests and the final release readback passing. The
[test release](https://github.com/SuperMonster003/AutoJs6-Codegen-Distribution-Test/releases/tag/codegen-models-v1)
was independently downloaded and verified on the desktop. Anonymous catalog and package
downloads matched the reviewed bytes; a read-only preflight correctly refused the existing
release. P5.4's remote E2 evidence is complete. Production publication remains a separate
P8.3 maintainer operation after the model passes its evaluation gate.
