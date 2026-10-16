# AutoJs6 speech models

This asset family will distribute reviewed sherpa-onnx speech models (speech recognition,
voice activity detection, keyword spotting and text-to-speech) for the AutoJs6 plugin
3-Macaw Speech (`AutoJs6-Plugin-Three-Macaw-Speech`). Its layout, schemas, tools
(`tools/speech-model-distribution/`), workflow (`publish-speech-models.yml`) and the
`speech-models-vN` release tags are specified in that plugin's `ROADMAP.md` (phase P2.1,
decisions D24 and D25). Only the signing public key is registered so far.

Unlike `codegen-models/`, model binaries are not versioned in this repository:
`sources/<modelId>/<versionCode>/` will hold only `source.json`, license texts and a model
card, and the release workflow reproduces each content-addressed archive from the recorded
upstream bytes and digests.

## Signing key

- Family key generated on 2026-10-16 with `tools/codegen-model-distribution/generate_keys.py`
  (ECDSA P-256, OpenSSL 3.2.1). The private key stays outside every Git working tree; the
  Ace font and codegen model keys are not reused.
- Key ID: `p256-bf5f0f579c7fbef1`.
- SPKI DER SHA-256: `bf5f0f579c7fbef188e81a02257fc3336189020273b2c69c69092cc402214f68`.
- Public key: `keys/catalog-signing-public.pem`.

Verify the checked-in public key:

```text
openssl pkey -pubin -in speech-models/keys/catalog-signing-public.pem -outform DER | openssl dgst -sha256
```
