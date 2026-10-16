# Streaming Zipformer, English (int8, mobile)

Catalog model `asr.zipformer-streaming.en.2023-06-26.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: en.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26-mobile.tar.bz2`.

## Origin

Mobile export (batch size 1) of sherpa-onnx-streaming-zipformer-en-2023-06-26 (https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26, Apache-2.0), converted from https://huggingface.co/Zengwei/icefall-asr-librispeech-streaming-zipformer-2023-05-17 (icefall pull request 1058).

## Training data

LibriSpeech (CC BY 4.0).

## Repacked contents

int8 encoder and joiner with the only (float32) decoder. The float32 encoder, bpe.model and the test recordings are omitted.

## Known limits

Read-speech training data; conversational and noisy speech are weaker. No bpe.vocab, so modeling-unit hotwords cannot be configured.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
