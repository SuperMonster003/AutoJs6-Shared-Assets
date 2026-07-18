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

On catalog v2, an unchanged v1 font keeps both fields at v1 and continues to
use its immutable v1 URL. A new or changed font uses v2. Generation requires the
immediately previous catalog and refuses changed bytes or notice files under an
old artifact version.

See the distribution-kit README for initial publication, offline signing,
updates, verification, revocation considerations, and recovery procedures.

