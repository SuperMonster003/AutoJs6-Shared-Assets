# AutoJs6 Ace fonts

This namespace contains optional fonts downloaded by the AutoJs6 Ace editor.
Regular Iosevka is bundled with the app and deliberately absent; Iosevka Slab
is an independent download.

`sources/` is the canonical Git-tracked input. Applications fetch
content-addressed `autojs6-ace-font-*` assets from immutable `ace-fonts-vN`
releases after accepting the signed catalog. Font variants from the same
visible family share one source directory while retaining independent stable
artifact IDs.

The manifest records provenance, licensing, source paths, artifact ownership,
and UI metadata:

- `artifactVersion` and `artifactReleaseTag` identify the immutable release
  that owns the exact WOFF2 and notice bytes.
- `features` uses canonical order `mono`, `nerd`, `variable`, `cn`, `jp`.
  An empty array is the client-side `other` category.
- `groupId` groups variants into one visible family. `variantName` and
  `variantOrder` define the feature list, and each group has exactly one
  `isDefaultVariant`. The default has the highest complexity order; Geist Pixel
  explicitly defaults to Triangle.

The wire schema remains v1. The published signed catalog remains v3 while the
reviewed unsigned v4 candidate is stored under `catalogs/pending/v4/`. V4 has
60 artifact entries in 43 groups: eight carry v1 assets, 28 carry v2 assets,
and 24 introduce v4 assets. The incorrect Sarasa Term SC Nerd v2 entry is
removed; Sarasa Mono SC Nerd and Sarasa Mono Slab SC Nerd are new v4 entries.

`audits/font-audit-v4.json` binds cmap evidence to every exact source SHA-256.
CN requires all reviewed Simplified Chinese probes and at least 6,000 unified
CJK ideographs. JP requires all reviewed Japanese probes, at least 2,000 CJK
ideographs, 80 Hiragana, and 80 Katakana characters. Unmarked fonts are not
classified by reverse inference.

Generation requires the immediately previous catalog and refuses changed font
or notice bytes under an old artifact version. V4 emits 50 release assets:
24 WOFF2 files and 26 notices. See the distribution-kit README for audit
regeneration, offline signing, promotion, verification, and publication.

Compatibility notes: v4 deliberately retains the verified static Recursive v2
artifact instead of the proportional-default variable source found in the
staging input. The carried Monaspace Krypton NF and Neon NF bytes also retain
known incorrect legacy family-name records; their typographic family records
are correct, and the client uses the catalog's explicit CSS family alias.
The incorrect Sarasa Term SC Nerd bytes remain only under `sources/retired/` so
v2/v3 can be reproduced; they are absent from the v4 manifest, audit, catalog,
and release asset list.
