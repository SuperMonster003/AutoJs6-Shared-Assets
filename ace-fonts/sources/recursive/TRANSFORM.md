# Recursive static instance

`Recursive-Regular.woff2` is a deterministic static instance of the upstream
`Recursive_VF_1.085.woff2` variable font. The Ace editor does not currently
set custom OpenType variation axes, while Recursive defaults to proportional
spacing (`MONO=0`), so publishing the upstream variable file unchanged would
not provide a monospaced code font.

- Upstream repository: `https://github.com/arrowtype/recursive`
- Upstream version: `1.085`
- Pinned upstream WOFF2:
  `https://raw.githubusercontent.com/arrowtype/recursive/v1.085/fonts/ArrowType-Recursive-1.085/Recursive_Web/woff2_variable/Recursive_VF_1.085.woff2`
- Upstream WOFF2 SHA-256:
  `145e9fc086d13403528384bdace7f2a4d5ecef72a2b10a749e99382dbecfce79`
- fontTools version: `4.63.0`
- Pinned axes: `MONO=1`, `CASL=0`, `wght=400`, `slnt=0`, `CRSV=0.5`
- Output SHA-256:
  `ba5b7ff5311807aeecbc0c9b15da75c78ee616975e840476b8bf983c936c52da`

Reproduction command:

```powershell
py -3.12 -m fontTools.varLib.instancer `
  --static --update-name-table --no-recalc-timestamp `
  -o Recursive-Regular.woff2 Recursive_VF_1.085.woff2 `
  MONO=1 CASL=0 wght=400 slnt=0 CRSV=0.5
```

The resulting font remains distributed under the accompanying SIL Open Font
License 1.1.
