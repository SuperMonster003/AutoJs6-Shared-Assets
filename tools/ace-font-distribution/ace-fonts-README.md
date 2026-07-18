# AutoJs6 Ace fonts

This namespace contains optional fonts downloaded by the AutoJs6 Ace editor.
Regular Iosevka is the bundled default and is deliberately absent; Iosevka Slab
is an independent downloadable font.

`sources/` is the canonical, Git-tracked reproduction input. Applications do
not download these paths: they fetch files named `autojs6-ace-font-*` from
immutable `ace-fonts-vN` releases after accepting the signed catalog in
`catalogs/catalog-v1.json`.

The manifest records each font's author, upstream repository/version, license,
stable ID, display order, source paths, and two release fields:

- `artifactVersion`: the release version that introduced the current bytes.
- `artifactReleaseTag`: exactly `ace-fonts-v<artifactVersion>`.

The current wire format is schema v1 (`schemaVersion: 1`); `catalog-v1.json` is
named for that schema, not the release number. The catalog now prepared here has
`catalogVersion: 2` and 37 entries. Eight unchanged fonts keep both artifact
fields at v1 and continue to use immutable v1 URLs; 29 new fonts use v2. The
signed v1 catalog and signature are preserved byte-for-byte under
`catalogs/history/v1/` for incremental generation and verification.

Generation requires the immediately previous catalog and refuses changed font
or notice bytes under an old artifact version. Only v2 assets are included in
the v2 upload set. The v2 Release does not exist merely because its sources and
catalog are committed; it remains unavailable until the reviewed publication
workflow succeeds.

See the distribution-kit README for offline signing, incremental publication,
updates, verification, revocation considerations, and recovery procedures.
