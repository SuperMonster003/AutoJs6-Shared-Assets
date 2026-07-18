# AutoJs6 Ace fonts

This namespace contains optional fonts downloaded by the AutoJs6 Ace editor.
Regular Iosevka is the bundled default and is deliberately absent; Iosevka Slab
is an independent downloadable font.

`sources/` is the canonical, Git-tracked reproduction input. Applications do
not download these paths: they fetch files named `autojs6-ace-font-*` from
immutable `ace-fonts-vN` releases after accepting the signed catalog in
`catalogs/catalog-v1.json`.

The manifest records each font's author, upstream repository/version, license,
stable ID, display order, source paths, explicit `features`, and two release
fields:

- `artifactVersion`: the release version that introduced the current bytes.
- `artifactReleaseTag`: exactly `ace-fonts-v<artifactVersion>`.
- `features`: a canonical array containing only `nerd`, `variable`, or `cn`.
  An empty array means that none of these filter features applies.

The current wire format is schema v1 (`schemaVersion: 1`); `catalog-v1.json` is
named for that schema, not the release number. The current catalog has
`catalogVersion: 3` and 37 entries. Eight fonts keep their v1 artifacts and 29
keep their v2 artifacts. Catalog v3 adds only explicit filter metadata and no
font or notice asset bytes. Signed v1 and v2 catalogs/signatures are preserved
byte-for-byte under `catalogs/history/v1/` and `catalogs/history/v2/`.
The source manifest that exactly reproduces signed catalog v1 is frozen at
`manifests/history/v1/font-sources.json`; its historical omission of `features`
is equivalent to an empty array.

Generation requires the immediately previous catalog and refuses changed font
or notice bytes under an old artifact version. Because every v3 font retains an
older artifact version, its release asset list is empty; the v3 release contains
only the reviewed catalog and detached signature.

See the distribution-kit README for offline signing, incremental publication,
updates, verification, revocation considerations, and recovery procedures.
