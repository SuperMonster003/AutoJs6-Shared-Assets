# AutoJs6 Ace font distribution kit

This kit prepares and publishes the `ace-fonts` namespace in
`SuperMonster003/AutoJs6-Shared-Assets`. AutoJs6 downloads signed catalog
entries from immutable GitHub Release Assets. Regular Iosevka remains bundled;
the eight manifest entries, including Iosevka Slab, are optional downloads.

The scripts use the Python standard library. OpenSSL performs ECDSA P-256
signing/verification and is discovered from PATH or Git for Windows.

## What is durable

`build/` is disposable output. The standalone repository must track
`ace-fonts/sources/` (reviewed WOFF2 and notice bytes), the manifest, schemas,
catalogs, signatures, public key, tools, and workflow. The application downloads
Release Assets, while maintainers reproduce those assets from tracked sources.

The ignored `keys/catalog-v1.private.pem` is not durable and is never copied by
`prepare_repository.py`. Move it to encrypted offline custody before cleaning or
recloning this workspace.

## Prepare the independent repository

The reviewed v1 source bytes are tracked under this kit's `sources/ace-fonts/`,
so a clean clone does not depend on `build/` or an upstream font repository.
They become durable only after this change set is committed; until then, do not
run `git clean` or discard the untracked distribution-kit directory.
From the AutoJs6 root:

```powershell
python tools/ace-font-distribution/prepare_repository.py `
  --destination ../AutoJs6-Shared-Assets `
  --repository SuperMonster003/AutoJs6-Shared-Assets
```

The destination must not exist. The command:

- copies only the reviewed, Git-tracked source snapshot;
- validates every exported WOFF2 and rejects symlinks/LFS pointer content;
- copies the kit, tests, schemas, public key, and publishing workflow;
- writes the self-contained source tree and an unsigned reviewed catalog;
- never copies a private key or silently reuses a detached signature.

For the unmodified initial v1 data, the prepared catalog must be byte-identical
to the signed bootstrap already reviewed in AutoJs6. Verify that equality before
copying its public signature into the prepared repository:

```powershell
$preparedCatalog = Resolve-Path `
  ../AutoJs6-Shared-Assets/ace-fonts/catalogs/catalog-v1.json
$bootstrapCatalog = Resolve-Path `
  app/src/main/res/raw/ace_font_catalog_v1.json
$preparedHash = (Get-FileHash -Algorithm SHA256 $preparedCatalog).Hash
$bootstrapHash = (Get-FileHash -Algorithm SHA256 $bootstrapCatalog).Hash
if ($preparedHash -ne $bootstrapHash) {
  throw "Prepared catalog differs from the signed AutoJs6 bootstrap"
}
Copy-Item tools/ace-font-distribution/catalog-v1.sig.json `
  ../AutoJs6-Shared-Assets/ace-fonts/catalogs/catalog-v1.sig.json
python tools/ace-font-distribution/verify_catalog.py $preparedCatalog `
  --signature ../AutoJs6-Shared-Assets/ace-fonts/catalogs/catalog-v1.sig.json `
  --public-key ../AutoJs6-Shared-Assets/ace-fonts/keys/catalog-signing-public.pem `
  --expected-key-id p256-fc433f8ba81333f7
```

If either catalog changed, do not reuse the signature; review and sign the new
exact bytes with the offline procedure below.

The initial source bytes can also be reconstructed from the exact pre-migration
AutoJs6 commit. This is a recovery/audit path, not the normal publishing input:

```powershell
python tools/ace-font-distribution/export_sources.py `
  --repository-root . `
  --source-ref 2937ad1dc5d5d779fa3aeadf14d9c152d90b81a0 `
  --output build/exported-ace-font-sources
```

To prepare directly from that historical commit, add
`--source-repository-root . --source-ref 2937ad1d...` to
`prepare_repository.py` instead of using its tracked-source default.

Both tools replace only directories carrying their own marker when
`--overwrite` is explicitly supplied.

## Generate and verify a release

Run inside the standalone repository:

```powershell
python tools/ace-font-distribution/distribution.py `
  --source-root ace-fonts/sources `
  --output build/ace-fonts-current `
  --repository SuperMonster003/AutoJs6-Shared-Assets

python tools/ace-font-distribution/verify_release.py `
  build/ace-fonts-current/catalog-v1.json `
  --assets-dir build/ace-fonts-current/assets
```

`catalog-v1.json` denotes wire schema v1; its internal `catalogVersion` advances.
The output also contains an identical `bootstrap-catalog-v1.json`,
`release-assets.txt`, and only the assets belonging to the manifest's current
global `releaseTag`.

Generation checks paths, IDs, ordering, WOFF2 structure, sizes, hashes, source
notices, immutable URL construction, and reserved IDs (`system_monospace` and
bundled `iosevka`). Asset tags are `ace-fonts-vN`; names begin
`autojs6-ace-font-`.

## Incremental catalog releases

Every manifest font has:

```json
"artifactVersion": 1,
"artifactReleaseTag": "ace-fonts-v1"
```

For catalog v2, set the global `catalogVersion` to `2` and `releaseTag` to
`ace-fonts-v2`. Leave unchanged fonts on artifact v1; assign v2 only to new or
changed font/notice bytes. Preserve the current signed catalog first:

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
outputs only v2 assets. Metadata such as display name/order may change without
republishing bytes. `autoJs6SourceCommit` is optional for fonts that never lived
in AutoJs6 Assets.

To add a font: review redistribution rights; add the WOFF2 and complete notices
under `ace-fonts/sources/<id>/`; add a unique lower_snake_case manifest entry;
increment `expectedFontCount` and global catalog version; assign the current
artifact version/tag; generate, review, sign, verify, and publish. Normal 400
WOFF2 is the only schema-v1 style.

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

1. Create `SuperMonster003/AutoJs6-Shared-Assets` with default branch `main`.
2. Commit the prepared tree, signed catalog/signature, and public key; confirm no
   private key is tracked.
3. Enable GitHub Immutable Releases.
4. Create an `ace-fonts-release` GitHub Environment and, when available, add a
   required reviewer for the publication job.
5. Dispatch `.github/workflows/publish-ace-fonts.yml` with the exact catalog tag
   (`ace-fonts-v1`) and expected key ID, from the default branch.
6. CI regenerates the catalog/current assets, compares exact catalog bytes,
   verifies the current and previous signatures, rejects an existing release or
   tag, atomically creates the tag on the verified workflow commit, and uploads
   only current assets plus catalog/signature.
7. Confirm raw catalog/signature and every Release Asset return successfully
   before updating the AutoJs6 bootstrap and URLs.

Never use `latest`, branch URLs for binary artifacts, mutable upstream assets,
or replacement uploads. A new catalog always has a monotonically increasing
version.

For a new public repository, the concrete first-publish commands are:

```powershell
gh auth status
Set-Location ../AutoJs6-Shared-Assets
git init -b main
git add .
git diff --cached --check
git commit -m "chore: initialize shared asset distribution"
gh repo create SuperMonster003/AutoJs6-Shared-Assets `
  --public --source . --remote origin --push

gh workflow run publish-ace-fonts.yml `
  -f release_tag=ace-fonts-v1 `
  -f key_id=p256-fc433f8ba81333f7
gh run watch
gh release verify ace-fonts-v1
```

These commands require an authenticated GitHub CLI. The repository must be
public because AutoJs6 downloads catalogs and Release Assets without a GitHub
account or access token.

The workflow must already be on the default branch before dispatch. Enable
Immutable Releases and configure the `ace-fonts-release` Environment in
repository settings before the first dispatch. Also
inspect `git status --ignored` and `git ls-files` before pushing; no private key
may appear in either the commit or GitHub Actions secrets.

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
