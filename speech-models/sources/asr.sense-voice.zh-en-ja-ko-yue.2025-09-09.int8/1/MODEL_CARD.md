# SenseVoice Small, Cantonese fine-tune (int8)

Catalog model `asr.sense-voice.zh-en-ja-ko-yue.2025-09-09.int8`, version code 1. Kind `asr`, model type `sense-voice`.

- Languages: zh, en, ja, ko, yue.
- Sample rate: 16000 Hz.
- License expression: `LicenseRef-FunASR-Model-License-1.1 AND Apache-2.0`; commercialUse: `false`.
- Upstream assets: `asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/ASLP-lab/WSYue-ASR/tree/main/sensevoice_small_yue (repository license Apache-2.0), a fine-tune of FunAudioLLM SenseVoiceSmall, whose weights and derivatives are covered by the FunASR Model Open Source License Agreement 1.1 (attribution and model-name retention required).

## Training data

Base model: more than 400,000 hours, not itemized by the publisher. Fine-tuning: about 21,800 hours of Cantonese from WenetSpeech-Yue, licensed CC BY-NC 4.0.

## Repacked contents

The single int8 model file with tokens; test recordings are omitted.

## Known limits

Upstream documentation lists no punctuation support for this export, unlike the 2024-07-17 SenseVoice export. Offline model: partial results are per segment.

## License files

- `LICENSE-FunASR-Model`
- `LICENSE-Apache-2.0`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
