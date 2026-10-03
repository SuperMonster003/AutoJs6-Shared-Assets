# AutoJs6 Code Generation Tiny Test

Model `autojs6.codegen.tiny-test`, version `1.0.0` (1). Publisher: AutoJs6.

License expression: `MPL-2.0`. The accompanying LICENSE contains the supplied terms.

## Purpose and inputs

Ranks candidate selector plans that the host has already verified against the captured layout. It does not generate script text or bypass target validation. Inputs are the numeric Kotlin feature schema; the package contains no layout snapshots or captured text.

## Training

Dataset `cg-ds-2026.10-1`; 2016 training task groups. Dataset created at 2026-10-03T09:23:40+00:00.

CatBoost 1.2.10, Python 3.12.5; training completed at 2026-10-03T09:24:47+00:00. Host source commit `166910c968fe3f95e00a6a49cff4ce617d8feb72`.

6 symmetric trees, maximum depth 6, 64 numeric features. Schema 1 (`9c6a5d8279ffca0e`).

## Held-out evaluation

| Split | Groups | Model top-1 survival | Rule top-1 survival | Regret |
| --- | ---: | ---: | ---: | ---: |
| test | 336 | 0.8764880952 | 0.3288690476 | 0.0491071429 |
| realTest | 0 | not measured | not measured | not measured |

Survival measures success in the sampled later interface states. Regret is the best observed candidate survival minus the selected candidate's survival, averaged by task group.

## Known limits

Controlled fixture coverage does not establish performance on unseen applications, devices, or future updates. A realTest count of zero means real application performance has not been measured. Finite sampled changes cannot prove that a selector will remain valid in every future state.

Split thresholds and leaves are stored as float32; desktop/host parity must be checked before release. Packaging alone does not assert release-gate approval or verified official provenance.
