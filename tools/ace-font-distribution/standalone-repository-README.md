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

The Ace catalog wire schema remains v1 (`schemaVersion: 1`) while
`catalogVersion` advances independently. Current manifests declare explicit
`mono`, `nerd`, `variable`, `cn`, and `jp` features. Catalog v4 and later also
declare stable font-group and variant metadata; an empty feature array is the
client-side `other` category.

## Repository layout

```text
.github/workflows/publish-ace-fonts.yml
ace-fonts/
  sources/                         # reviewed WOFF2/license source inputs
  catalogs/catalog-v1.json         # current schema-v1 catalog
  catalogs/catalog-v1.sig.json     # detached offline signature
  catalogs/history/vN/             # exact prior catalog/signature snapshots
  catalogs/pending/vN/             # reviewed catalog awaiting offline signature
  audits/font-audit-vN.json         # SHA-bound cmap/metadata evidence
  manifests/history/vN/            # frozen source manifests for recovery
  keys/catalog-signing-public.pem  # public key only
  schemas/
tools/ace-font-distribution/
```

Generated bundles live under ignored `build/`. Canonical source WOFF2 and notice
files are tracked directly so a clean clone can reproduce releases without an
AutoJs6 `build/` directory or a legacy `tools/.../sources` snapshot. Git LFS is
intentionally not used.

## Publishing

Read [`tools/ace-font-distribution/README.md`](tools/ace-font-distribution/README.md)
before publishing. In summary: update reviewed sources and the manifest,
preserve the exact previous catalog and signature under `catalogs/history/vN/`,
generate incrementally, sign offline, commit only public material, and dispatch
`publish-ace-fonts.yml` with the exact tag and key ID. The workflow publishes
only assets introduced by that catalog; unchanged entries keep their older
immutable Release URLs.

## Contributions and licensing

Every binary contribution must include its upstream repository, an exact
version or commit when available, redistributable license/notice files, and a
reviewed WOFF2 Normal 400 artifact. This repository does not claim ownership of
third-party fonts; copyright and license details accompany each release.

Never submit executable content, secrets, private keys, or an unreviewed binary.
