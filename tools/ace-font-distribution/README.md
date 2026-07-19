# AutoJs6 Ace font distribution kit

This kit prepares and publishes the `ace-fonts` namespace in
`SuperMonster003/AutoJs6-Shared-Assets`. AutoJs6 downloads signed catalog
entries from immutable GitHub Release Assets. Regular Iosevka remains bundled.
The v4 manifest contains 60 artifact variants in 43 visible groups: eight retain
v1 artifacts, 28 retain v2 artifacts, and 24 introduce v4 artifacts.

Release generation and validation use the Python standard library. OpenSSL
performs ECDSA P-256 signing/verification and is discovered from PATH or Git for
Windows. Only the optional cmap audit generator requires `fonttools[woff]`;
release CI validates its SHA-bound report without importing fontTools.

## What is durable

`SuperMonster003/AutoJs6-Shared-Assets` is the canonical source and distribution
repository. It tracks `ace-fonts/sources/` (reviewed WOFF2 and notice bytes), the
manifest, schemas, catalogs, signatures, public key, tools, and workflow. The
application downloads Release Assets, while maintainers reproduce those assets
from the shared repository's tracked sources.

AutoJs6's `build/` directory is disposable. This kit intentionally does not
mirror font bytes under `tools/ace-font-distribution/sources/`; deleting or
recreating an AutoJs6 checkout therefore cannot remove the canonical font
sources.

The ignored `keys/catalog-v1.private.pem` is not durable and is never copied by
`prepare_repository.py`. Move it to encrypted offline custody before cleaning or
recloning this workspace.

## Canonical sources and recovery

Normal generation and publication run from the Shared Assets checkout, using
its `ace-fonts/sources/` directory. The initial v1 source bytes can still be
reconstructed from the exact pre-migration AutoJs6 commit. That commit and the
frozen eight-entry v1 manifest are independent recovery inputs: the source
commit belongs to an AutoJs6 checkout, while the manifest is tracked here at
`ace-fonts/manifests/history/v1/font-sources.json`. This is an emergency
recovery/audit path, not a normal publishing input:

```powershell
$autoJs6Root = Resolve-Path ../AutoJs6
$v1Manifest = Resolve-Path `
  ace-fonts/manifests/history/v1/font-sources.json
python tools/ace-font-distribution/export_sources.py `
  --repository-root $autoJs6Root `
  --source-ref 2937ad1dc5d5d779fa3aeadf14d9c152d90b81a0 `
  --manifest $v1Manifest `
  --output build/exported-ace-font-sources
```

The frozen manifest has `catalogVersion: 1`, exactly eight entries, and omits
the later `features` field. The tools interpret that historical omission as an
empty array and reproduce signed catalog v1 byte-for-byte. The current 60-entry
v4 manifest cannot be exported from the old AutoJs6 commit.

Path-adapted recovery manifests for v2 and v3 are stored under
`ace-fonts/manifests/history/v2/` and `v3/`. They reference the consolidated
Maple/Monaspace directories and the retired Sarasa Term source, yet reproduce
the signed historical catalogs byte-for-byte. `sources/retired/` is never part
of the current manifest, audit, catalog, or v4 release asset list.

`prepare_repository.py` can create a disposable standalone recovery tree from
the same exact commit. It has no implicit local source snapshot:

```powershell
python tools/ace-font-distribution/prepare_repository.py `
  --source-repository-root $autoJs6Root `
  --source-ref 2937ad1dc5d5d779fa3aeadf14d9c152d90b81a0 `
  --manifest $v1Manifest `
  --destination ../AutoJs6-Shared-Assets-recovery `
  --repository SuperMonster003/AutoJs6-Shared-Assets
```

The destination must not exist. The preparation command validates every WOFF2,
rejects Git LFS pointer content, writes an unsigned catalog, and never copies a
private key or detached signature.

Both tools replace only directories carrying their own marker when
`--overwrite` is explicitly supplied.

## Generate and verify a release

Run inside the standalone repository:

```powershell
python tools/ace-font-distribution/distribution.py `
  --source-root ace-fonts/sources `
  --output build/ace-fonts-current `
  --repository SuperMonster003/AutoJs6-Shared-Assets `
  --previous-catalog ace-fonts/catalogs/history/v3/catalog-v1.json

python tools/ace-font-distribution/verify_release.py `
  build/ace-fonts-current/catalog-v1.json `
  --assets-dir build/ace-fonts-current/assets
```

`catalog-v1.json` denotes wire schema v1 (`schemaVersion: 1`); its internal
`catalogVersion` advances independently. The current manifest has
`catalogVersion: 4`, `releaseTag: ace-fonts-v4`, and 60 artifact entries in 43
groups. The output also contains an identical `bootstrap-catalog-v1.json` and
`release-assets.txt`. V4 emits 50 assets: 24 WOFF2 files and 26 notices.

Generation checks paths, IDs, ordering, WOFF2 structure, sizes, hashes, source
notices, immutable URL construction, explicit font features, variant-group
invariants, and reserved IDs (`system_monospace` and bundled `iosevka`). Feature
arrays use canonical order and accept `mono`, `nerd`, `variable`, `cn`, and
`jp`. Historical v1/v2 manifests may
omit this field and retain their original catalog byte format; manifests from
catalog v3 onward must declare it explicitly. Asset tags are `ace-fonts-vN`;
names begin `autojs6-ace-font-`.

## Incremental catalog releases

Every manifest font records the immutable release that owns its bytes, for
example:

```json
"artifactVersion": 1,
"artifactReleaseTag": "ace-fonts-v1"
```

For catalog v4, the global `catalogVersion` is `4` and the `releaseTag` is
`ace-fonts-v4`. Eight entries remain on artifact v1, 28 remain on artifact v2,
and 24 use artifact v4. The exact signed v1, v2, and v3 catalogs/signatures are
preserved at:

```text
ace-fonts/catalogs/history/v1/catalog-v1.json
ace-fonts/catalogs/history/v1/catalog-v1.sig.json
ace-fonts/catalogs/history/v2/catalog-v1.json
ace-fonts/catalogs/history/v2/catalog-v1.sig.json
ace-fonts/catalogs/history/v3/catalog-v1.json
ace-fonts/catalogs/history/v3/catalog-v1.sig.json
ace-fonts/manifests/history/v2/font-sources.json
ace-fonts/manifests/history/v3/font-sources.json
```

Then generate with:

```powershell
python tools/ace-font-distribution/distribution.py `
  --source-root ace-fonts/sources `
  --output build/ace-fonts-current `
  --repository SuperMonster003/AutoJs6-Shared-Assets `
  --previous-catalog ace-fonts/catalogs/history/v3/catalog-v1.json
```

The generator compares carried artifacts and notice files byte-for-byte through
their catalog metadata. It refuses a changed source under an old release.
Metadata such as display name, order, `features`, and variant grouping may
change without republishing
bytes. `autoJs6SourceCommit` is optional for fonts that never lived in AutoJs6
Assets.

Every current manifest entry explicitly contains `features`. Use `mono` for
monospaced or dual-width coding faces, `nerd` only for a Nerd Fonts-patched
face, `variable` only when OpenType variation axes exist, and `cn`/`jp` only
when the reviewed cmap thresholds pass. `[]` is the client-side `other`
category. `groupId`, `variantName`, `variantOrder`, and `isDefaultVariant`
describe same-family alternatives; each group has exactly one highest-order
default. Clients consume this metadata directly and never infer it from names.

Regenerate and validate the SHA-bound cmap audit with:

```powershell
py -3.12 -m pip install -r tools/ace-font-distribution/requirements-audit.txt
py -3.12 tools/ace-font-distribution/audit_font_metadata.py `
  --manifest tools/ace-font-distribution/font-sources.json `
  --source-root ace-fonts/sources `
  --output ace-fonts/audits/font-audit-v4.json --check
python tools/ace-font-distribution/validate_font_audit.py `
  ace-fonts/audits/font-audit-v4.json `
  --manifest tools/ace-font-distribution/font-sources.json `
  --source-root ace-fonts/sources
```

CN requires all seven reviewed Simplified Chinese probes and at least 6,000
unified CJK codepoints. JP requires all five reviewed Japanese probes, at least
2,000 CJK codepoints, 80 Hiragana, and 80 Katakana codepoints. Unmarked fonts
are not reverse-inferred.

To add a font: review redistribution rights; add the WOFF2 and complete notices
under `ace-fonts/sources/<id>/`; add a unique lower_snake_case manifest entry;
set its explicit `features`; increment `expectedFontCount` and global catalog
version; assign the current artifact version/tag; generate, review, sign, verify,
and publish. Normal 400 WOFF2 is the only schema-v1 descriptor. The client does
not select variation axes, so a variable WOFF2 is suitable only when its default
instance is the intended monospaced face. Otherwise derive a deterministic
static instance and track its exact input hash, tool version, parameters, and
output hash alongside the font, as
`ace-fonts/sources/recursive/TRANSFORM.md` does.

## Offline signing

Generate/retain the key on an offline controlled machine. Never commit it:

```powershell
python tools/ace-font-distribution/generate_keys.py `
  --private-key E:/offline-autojs6-keys/ace-font-catalog.private.pem `
  --public-key-pem build/keys/catalog-signing-public.pem `
  --public-key-der build/keys/catalog-signing-public.spki.der
```

The reviewed unsigned candidate is
`ace-fonts/catalogs/pending/v4/catalog-v1.json` and must equal the generated
catalog byte-for-byte. Copy those exact bytes to
`ace-fonts/catalogs/catalog-v1.json`, sign them, and verify:

```powershell
python tools/ace-font-distribution/sign_catalog.py `
  ace-fonts/catalogs/catalog-v1.json `
  --private-key E:/offline-autojs6-keys/ace-font-catalog.private.pem `
  --key-id p256-fc433f8ba81333f7 `
  --output ace-fonts/catalogs/catalog-v1.sig.json

python tools/ace-font-distribution/verify_catalog.py `
  ace-fonts/catalogs/catalog-v1.json `
  --signature ace-fonts/catalogs/catalog-v1.sig.json `
  --public-key ace-fonts/keys/catalog-signing-public.pem `
  --expected-key-id p256-fc433f8ba81333f7
```

Do not parse/re-serialize a signed catalog. The signature covers exact UTF-8
bytes. Repository/tag/URL changes alter those bytes and require re-signing.

## Publish on GitHub

1. Work on `main` in `SuperMonster003/AutoJs6-Shared-Assets`, and confirm all
   reviewed source inputs are tracked there.
2. Generate, review, offline-sign, and verify the new catalog and release assets.
3. Commit and push the source, manifest, signed catalog/signature, and public
   material; confirm no private key is tracked.
4. Keep GitHub Immutable Releases enabled and configure an
   `ace-fonts-release` GitHub Environment; when available, add a
   required reviewer for the publication job.
5. Dispatch `.github/workflows/publish-ace-fonts.yml` with the exact catalog tag
   (`ace-fonts-v4`) and expected key ID, from the default branch. This is the
   operation that publishes v4; preparing or pushing the files alone does not.
6. CI regenerates the catalog/current assets, compares exact catalog bytes,
   verifies the current and previous signatures, rejects an existing release or
   tag, atomically creates the tag on the verified workflow commit, and uploads
   only current assets plus catalog/signature.
7. Confirm raw catalog/signature and every Release Asset return successfully
   before updating the AutoJs6 bootstrap and URLs.

Never use `latest`, branch URLs for binary artifacts, mutable upstream assets,
or replacement uploads. A new catalog always has a monotonically increasing
version.

The repository already exists. After the reviewed, signed v4 commit is on `main`, and
only when publication is intended, dispatch the release workflow with the exact
catalog tag:

```powershell
gh auth status
Set-Location ../AutoJs6-Shared-Assets
gh workflow run publish-ace-fonts.yml `
  -f release_tag=ace-fonts-v4 `
  -f key_id=p256-fc433f8ba81333f7
gh run watch
gh release verify ace-fonts-v4
```

These commands require an authenticated GitHub CLI. The repository remains
public because AutoJs6 downloads catalogs and Release Assets without a GitHub
account or access token.

The workflow must already be on the default branch before dispatch. Inspect
`git status --ignored` and `git ls-files` before pushing; no private key may
appear in either the commit or GitHub Actions secrets.

If asset upload fails before a draft is published, inspect the draft and tag in
GitHub before retrying. Only after confirming that they came from the failed run,
delete that draft/tag and dispatch again; never delete or replace a published
immutable release.

## Tests and formats

```powershell
python -m unittest discover -s tools/ace-font-distribution/tests -v
```

Host-consistency tests run when the AutoJs6 Android tree is present; standalone
generation/export/signature tests run in the shared-assets repository.
`catalog-v1.schema.json` and `signature-v1.schema.json` document the wire format;
`validate_catalog.py` enforces additional cross-field invariants.
