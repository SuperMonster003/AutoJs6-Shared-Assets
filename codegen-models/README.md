# AutoJs6 layout code generation models

This asset family distributes small numerical rankers for AutoJs6's layout-code-generation
tool. Models rank candidate plans that the host has already verified. Packages contain
declarative symmetric-tree data, metadata, a feature schema, a model card and license text.
Training tools and the Kotlin interpreter remain in the AutoJs6 host repository.

The model family uses its own `codegen-models-vN` release tags, catalog schemas, workflow and
ECDSA P-256/SHA-256 signing key. Ace font files, signatures and keys remain separate.

## Layout and current setup

```text
sources/<modelId>/<versionCode>/
  model.ajcgm                      # one reviewed .ajcgm, source basename may differ
  MODEL_CARD.md                    # exact card from the package
  dataset-manifest.json            # reviewed aggregate dataset provenance
  source.json                     # explicit catalog summary, release date and status
  gate.json                       # production publication gate bound to package SHA
catalogs/catalog-v1.json           # promoted exact signed catalog bytes
catalogs/catalog-v1.sig.json       # detached signature envelope
catalogs/history/vN/               # immutable prior catalog/signature snapshots
catalogs/pending/vN/               # unsigned or signed material awaiting promotion
keys/catalog-signing-public.pem   # maintainer-provided model public key, never a private key
schemas/
```

The first implementation includes schemas/tools and the reviewed
`autojs6.codegen.tiny-test/1` source. The maintainer supplied the model signing public key:

- Key ID: `p256-f1a540e052cf0865`.
- SPKI DER SHA-256: `f1a540e052cf086520619e429cd3e3240fa3f8a4b8fca46e3531358906a67de3`.

The empty pending v1 catalog has been signed for the host's offline bootstrap. It is not
promoted to a remote current catalog or Release; `codegen-models-v1` remains reserved for
the first approved production model. Pending catalogs require signature verification
before use, and test repository keys never establish production trust.

The tiny package is the controlled-only six-tree model accepted by AutoJs6 P4. Its package
license is MPL-2.0, copied from the host repository. It exists for reproducible tool tests
and a fork/private workflow acceptance run, and is refused in the canonical production
repository's catalog. Its source release date is a fixed fixture field, not a claim that
a Release has already been published.

The accompanying dataset manifest is an aggregate copy. Device serials are omitted, while
`sourceManifestSha256` records the original manifest digest. No layout snapshots, task
selectors, raw interface text, private key or unconfirmed real-app annotations belong here.

## Version and integrity rules

- Catalog wire schema is v1. Catalog versions increase monotonically and tags are
  `codegen-models-vN`, where N is the catalog version.
- Model versions are independent positive integers. A previously accepted `(modelId,
  versionCode)` cannot acquire different package bytes or immutable metadata.
- Each download has a content-addressed filename:
  `autojs6-codegen-<modelId>-v<versionCode>-<sha8>.ajcgm`. Unchanged versions retain their
  original Release URLs; only new assets are uploaded by a new release.
- A signed catalog binds its repository and every package's size, SHA-256, schema, model
  version, dataset, metrics and license. Status can move toward deprecated/revoked;
  unavailable versions are not recommended for download.
- Official trust comes from matching a package against a verified signed catalog. A
  package's publisher string or model ID alone does not establish official provenance.
- Published packages must be smaller than 100 MiB and have a passed publication gate
  bound to the exact package hash. Test-mode exceptions are limited to the tiny test
  model in a noncanonical repository; they cannot admit production models without gates.

## Publication workflow

Review sources and their license, prepare a pending catalog, verify its model and history
invariants, sign the exact bytes offline, then promote the verified catalog/signature and
public key. The maintainer dispatches `publish-codegen-models.yml` after reviewing the
complete commit. The workflow reproduces the reviewed catalog/assets, checks signatures,
refuses an existing tag or Release, publishes immutable assets, and downloads them again
for verification. No signing private key is given to CI.

Read [the distribution tools guide](../tools/codegen-model-distribution/README.md) for
commands, bootstrap preparation and the local acceptance procedure.

## Test release acceptance (2026-10-04)

The maintainer completed [workflow run 37138706446](https://github.com/SuperMonster003/AutoJs6-Codegen-Distribution-Test/actions/runs/37138706446)
on test commit `8a0ae0128913f40b7fca306c76efc7c6209ac477`. All 63 CI tests, signature checks,
catalog reproduction and the final published-asset readback passed. The resulting
[codegen-models-v1 test release](https://github.com/SuperMonster003/AutoJs6-Codegen-Distribution-Test/releases/tag/codegen-models-v1)
contains the 23,633-byte tiny package, catalog and signature. An independent desktop download
verified the same bytes, and anonymous HTTPS requests to the public catalog/package URLs
also matched. Read-only preflight now refuses the existing release as required.

This establishes P5.4's remote workflow evidence. Production trust remains with the separate
maintainer key above; the first production model/current catalog still belongs to P8.3.
