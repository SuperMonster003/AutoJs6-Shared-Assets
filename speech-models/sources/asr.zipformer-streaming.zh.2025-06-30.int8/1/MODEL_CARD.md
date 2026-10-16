# Streaming Zipformer, Chinese (int8, 2025)

Catalog model `asr.zipformer-streaming.zh.2025-06-30.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: zh.
- Sample rate: 16000 Hz.
- License expression: `LicenseRef-NoLicenseDeclared`; commercialUse: `false`.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/yuekai/icefall-asr-multi-zh-hans-zipformer-large (a gated repository with no declared license), trained with the icefall multi_zh-hans recipe (streaming Zipformer large, char-based).

## Training data

The recipe names about 14,000 hours of Chinese corpora: THCHS-30, AISHELL-1, AISHELL-2, AISHELL-4, ST-CMDS, Primewords, aidatatang_200zh, MagicData, AliMeeting, WenetSpeech and KeSpeech. MagicData (CC BY-NC-ND 4.0), KeSpeech and WenetSpeech are restricted to non-commercial use.

## Repacked contents

int8 encoder and joiner with the float32 decoder, as in sherpa-onnx 1.13.8 OnlineRecognizer type 20. Test recordings are omitted.

## Known limits

No license is declared for the weights and the upstream repository is gated; the maintainer should confirm redistribution before signing. Hotword support depends on the char-based token table.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
