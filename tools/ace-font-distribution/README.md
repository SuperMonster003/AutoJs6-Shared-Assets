# AutoJs6 Ace font distribution kit

This kit prepares and publishes the `ace-fonts` namespace in
`SuperMonster003/AutoJs6-Shared-Assets`. AutoJs6 downloads signed catalog
entries from immutable GitHub Release Assets. Regular Iosevka remains bundled;
the manifest now contains 37 optional downloads. Eight retain their published
v1 artifacts, while 29 are prepared for the prospective v2 release.

The scripts use the Python standard library. OpenSSL performs ECDSA P-256
signing/verification and is discovered from PATH or Git for Windows.

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
eight-entry v1 manifest belong to an AutoJs6 checkout, not this Shared Assets
repository. This is an emergency recovery/audit path, not a normal publishing
input:

```powershell
$autoJs6Root = Resolve-Path ../AutoJs6
$v1Manifest = Join-Path $autoJs6Root `
  tools/ace-font-distribution/font-sources.json
python tools/ace-font-distribution/export_sources.py `
  --repository-root $autoJs6Root `
  --source-ref 2937ad1dc5d5d779fa3aeadf14d9c152d90b81a0 `
  --manifest $v1Manifest `
  --output build/exported-ace-font-sources
```

Before using this recovery recipe, confirm that `$v1Manifest` has
`catalogVersion: 1` and exactly eight entries. A current 37-entry v2 manifest
cannot be exported from the old AutoJs6 commit.

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
  --previous-catalog ace-fonts/catalogs/history/v1/catalog-v1.json

python tools/ace-font-distribution/verify_release.py `
  build/ace-fonts-current/catalog-v1.json `
  --assets-dir build/ace-fonts-current/assets
```

`catalog-v1.json` denotes wire schema v1 (`schemaVersion: 1`); its internal
`catalogVersion` advances independently. The current manifest has
`catalogVersion: 2`, `releaseTag: ace-fonts-v2`, and 37 fonts. The output also
contains an identical `bootstrap-catalog-v1.json`, `release-assets.txt`, and
only the assets belonging to the manifest's current global `releaseTag`.

Generation checks paths, IDs, ordering, WOFF2 structure, sizes, hashes, source
notices, immutable URL construction, and reserved IDs (`system_monospace` and
bundled `iosevka`). Asset tags are `ace-fonts-vN`; names begin
`autojs6-ace-font-`.

## Incremental catalog releases

Every manifest font records the immutable release that owns its bytes, for
example:

```json
"artifactVersion": 1,
"artifactReleaseTag": "ace-fonts-v1"
```

For the prepared catalog v2, the global `catalogVersion` is `2` and the
`releaseTag` is `ace-fonts-v2`. Its eight unchanged fonts remain on artifact v1;
29 new fonts use artifact v2. The exact previously published v1 catalog and
signature are preserved at:

```text
ace-fonts/catalogs/history/v1/catalog-v1.json
ace-fonts/catalogs/history/v1/catalog-v1.sig.json
```

Then generate with:

```powershell
python tools/ace-font-distribution/distribution.py `
  --source-root ace-fonts/sources `
  --output build/ace-fonts-current `
  --repository SuperMonster003/AutoJs6-Shared-Assets `
  --previous-catalog ace-fonts/catalogs/history/v1/catalog-v1.json
```

The generator compares carried artifacts and notice files byte-for-byte through
their catalog metadata. It refuses a changed source under an old release and
outputs only the 29 v2 fonts and their v2 notice assets. Metadata such as display
name/order may change without republishing bytes. `autoJs6SourceCommit` is
optional for fonts that never lived in AutoJs6 Assets.

To add a font: review redistribution rights; add the WOFF2 and complete notices
under `ace-fonts/sources/<id>/`; add a unique lower_snake_case manifest entry;
increment `expectedFontCount` and global catalog version; assign the current
artifact version/tag; generate, review, sign, verify, and publish. Normal 400
WOFF2 is the only schema-v1 descriptor. The client does not select variation
axes, so a variable WOFF2 is suitable only when its default instance is the
intended monospaced face. Otherwise derive a deterministic static instance and
track its exact input hash, tool version, parameters, and output hash alongside
the font, as `ace-fonts/sources/recursive/TRANSFORM.md` does.

## Offline signing

Generate/retain the key on an offline controlled machine. Never commit it:

```powershell
python tools/ace-font-distribution/generate_keys.py `
  --private-key E:/offline-autojs6-keys/ace-font-catalog.private.pem `
  --public-key-pem build/keys/catalog-signing-public.pem `
  --public-key-der build/keys/catalog-signing-public.spki.der
```

After reviewing `build/ace-fonts-current/catalog-v1.json`, copy its exact bytes
to `ace-fonts/catalogs/catalog-v1.json`, sign those bytes, and verify:

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
   (`ace-fonts-v2`) and expected key ID, from the default branch. This is the
   operation that publishes v2; preparing or pushing the files alone does not.
6. CI regenerates the catalog/current assets, compares exact catalog bytes,
   verifies the current and previous signatures, rejects an existing release or
   tag, atomically creates the tag on the verified workflow commit, and uploads
   only current assets plus catalog/signature.
7. Confirm raw catalog/signature and every Release Asset return successfully
   before updating the AutoJs6 bootstrap and URLs.

Never use `latest`, branch URLs for binary artifacts, mutable upstream assets,
or replacement uploads. A new catalog always has a monotonically increasing
version.

The repository already exists. After the reviewed v2 commit is on `main`, and
only when publication is intended, dispatch the release workflow with the exact
catalog tag:

```powershell
gh auth status
Set-Location ../AutoJs6-Shared-Assets
gh workflow run publish-ace-fonts.yml `
  -f release_tag=ace-fonts-v2 `
  -f key_id=p256-fc433f8ba81333f7
gh run watch
gh release verify ace-fonts-v2
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
