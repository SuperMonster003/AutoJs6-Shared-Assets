# AutoJs6 Shared Assets

This repository is the reviewed distribution source for large or independently
released AutoJs6 assets. Runtime consumers download immutable GitHub Release
Assets; tracked source inputs, manifests, catalogs, schemas, and public keys make
every release reproducible. It is not a general-purpose CDN and never stores
signing private keys.

## Components

- [`ace-fonts/`](ace-fonts/README.md): optional WOFF2 fonts for the AutoJs6 Ace
  editor. Regular Iosevka remains bundled in AutoJs6 and is not distributed here.
- Additional asset families must use their own directory, manifest, release-tag
  prefix, workflow, integrity policy, and signing key where appropriate.

Assets required to build or render the installed app (for example its primary
logo or bundled CSS) normally stay in the AutoJs6 source repository. This shared
repository is for independently released/downloaded or cross-project assets.
Remote CSS is active content, so it must never be added to `ace-fonts`; give it
a separate namespace and a stricter signing/review policy.

## Trust and release policy

Ace font catalogs are signed offline with ECDSA P-256/SHA-256. AutoJs6 pins the
public key, rejects catalog rollback/equivocation, and verifies each WOFF2 by
size, SHA-256, and file structure. Release tags are `ace-fonts-vN`; release
assets are content-addressed and are never replaced. Enable GitHub Immutable
Releases before publishing.

The `main` branch contains the current signed catalog. Branch URLs are mutable,
so clients trust its detached signature rather than GitHub transport alone.

## Repository layout

```text
.github/workflows/publish-ace-fonts.yml
ace-fonts/
  sources/                         # reviewed WOFF2/license source inputs
  catalogs/catalog-v1.json         # current schema-v1 catalog
  catalogs/catalog-v1.sig.json     # detached offline signature
  catalogs/history/vN/             # prior signed catalogs after v1
  keys/catalog-signing-public.pem  # public key only
  schemas/
tools/ace-font-distribution/
```

Generated bundles live under ignored `build/`. Source WOFF2 files are tracked
normally because the initial set is small; Git LFS is intentionally unnecessary.

## Publishing

Read [`tools/ace-font-distribution/README.md`](tools/ace-font-distribution/README.md)
before publishing. In summary: update reviewed sources and the manifest,
generate the catalog, preserve the previous signed catalog when carrying old
assets forward, sign offline, commit only the signed catalog/public material,
and dispatch `publish-ace-fonts.yml` with the exact tag and key ID.

## Contributions and licensing

Every binary contribution must include its upstream repository, an exact
version or commit when available, redistributable license/notice files, and a
reviewed WOFF2 Normal 400 artifact. This repository does not claim ownership of
third-party fonts; copyright and license details accompany each release.

Never submit executable content, secrets, private keys, or an unreviewed binary.
