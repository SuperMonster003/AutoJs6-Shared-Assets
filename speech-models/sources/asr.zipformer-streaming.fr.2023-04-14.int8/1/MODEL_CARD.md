# Streaming Zipformer, French (int8)

Catalog model `asr.zipformer-streaming.fr.2023-04-14.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: fr.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-fr-2023-04-14.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/shaojieli/icefall-asr-commonvoice-fr-pruned-transducer-stateless7-streaming-2023-04-02 (Apache-2.0), trained with the icefall pruned_transducer_stateless7_streaming recipe (streaming Zipformer, sherpa-onnx model type `zipformer`).

## Training data

Common Voice 12, French (CC0), as named on the same model page.

## Repacked contents

int8 encoder and joiner with the float32 decoder, tokens and the upstream README. The float32 encoder and joiner, the int8 decoder, the export script and the test recordings are omitted.

## Known limits

Hotwords are unavailable because the archive has no BPE vocabulary. French only. Common Voice is read speech, so spontaneous or noisy speech may be recognized less accurately.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v2.json`. The exact installed files and digests are recorded in `source.json`.
