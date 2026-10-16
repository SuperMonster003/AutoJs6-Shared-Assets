# SenseVoice Small, multilingual (int8)

Catalog model `asr.sense-voice.zh-en-ja-ko-yue.2024-07-17.int8`, version code 1. Kind `asr`, model type `sense-voice`.

- Languages: zh, en, ja, ko, yue.
- Sample rate: 16000 Hz.
- License expression: `LicenseRef-FunASR-Model-License-1.1`; commercialUse: `true`.
- Upstream assets: `asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2`.

## Origin

The official int8 ONNX export by k2-fsa of FunAudioLLM SenseVoiceSmall (https://huggingface.co/FunAudioLLM/SenseVoiceSmall, https://github.com/FunAudioLLM/SenseVoice), published on 2024-07-17. The weights are covered by the FunASR Model Open Source License Agreement 1.1, which permits use, copying, modification and sharing, including commercial use, as long as the source, the author information and the model names are retained. On 2026-10-16 the maintainer chose this export over the Cantonese fine-tune export of 2025-09-09 (WenetSpeech-Yue, CC BY-NC 4.0, no punctuation) that the unsigned pending v1 catalog listed before; the earlier source directory was removed.

## Training data

More than 400,000 hours of multilingual speech, not itemized by the publisher.

## Repacked contents

The int8 model with tokens, plus the upstream README and the LICENSE pointer file. export-onnx.py and the test recordings are omitted.

## Known limits

Offline model: results are per segment cut by voice activity detection. Language identification, punctuation and inverse text normalization are produced by the model itself (sherpa-onnx 1.13.8 `OfflineSenseVoiceModelConfig`, `useInverseTextNormalization`). Hotwords are not supported.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
