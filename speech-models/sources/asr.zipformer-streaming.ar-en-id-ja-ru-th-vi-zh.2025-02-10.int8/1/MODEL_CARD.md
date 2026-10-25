# Streaming Zipformer, 8 languages (PengChengStarling, int8)

Catalog model `asr.zipformer-streaming.ar-en-id-ja-ru-th-vi-zh.2025-02-10.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: ar, en, id, ja, ru, th, vi, zh.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `unknown`.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10.tar.bz2`.

## Origin

Converted by k2-fsa from PengChengStarling (https://github.com/yangb05/PengChengStarling, weights at https://huggingface.co/stdo/PengChengStarling), a multilingual streaming Zipformer trained with icefall recipes (sherpa-onnx model type `zipformer2`). The Hugging Face model card declares Apache-2.0; the GitHub repository declares no license.

## Training data

Not named. The publisher only says that each language has about 2,000 hours of training speech, mostly from open datasets. Because the training data and its licenses cannot be looked up, the model fails the catalog gate of decision D124; the maintainer took it as an exception on 2026-10-25 (Q80), with commercialUse `unknown` and the notice key `speech_model_license_unknown_data`, which tells users that the training data is not disclosed. Plugins that do not know this key show the generic unknown-license notice.

## Repacked contents

int8 encoder and joiner with the float32 decoder, tokens and the upstream README. `bpe.model` and the test recordings are omitted: sherpa-onnx hotwords need a `bpe.vocab`, which the upstream archive does not have.

## Known limits

The language cannot be chosen: the model detects it by itself, and the first words of an utterance are sometimes read as another language. No punctuation. Hotwords are unavailable. The largest recognizer in this catalog: on a Sony G8441 (4 GB) loading takes about 5 s and peak memory is about 600 MiB.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
