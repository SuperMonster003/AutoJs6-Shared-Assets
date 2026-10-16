# VITS AISHELL-3 Chinese, 174 voices

Catalog model `tts.vits.icefall.zh-aishell3`, version code 1. Kind `tts`, model type `vits`.

- Languages: zh.
- Sample rate: 8000 Hz.
- Speakers: 174.
- License expression: `LicenseRef-NoLicenseDeclared`; commercialUse: `unknown`.
- Upstream assets: `tts-models/vits-icefall-zh-aishell3.tar.bz2`.

## Origin

Trained by k2-fsa with the icefall VITS recipe for AISHELL-3 and exported for sherpa-onnx. The model metadata names k2-fsa as author; no license is declared for the weights.

## Training data

AISHELL-3, about 85 hours from 218 Mandarin speakers, Apache-2.0.

## Repacked contents

model.onnx, lexicon, tokens, speakers.txt and the four rule FSTs used by the sherpa-onnx 1.13.8 TTS engine. rule.far (180,717,014 bytes uncompressed) is omitted to keep the model small; the FST rules still normalize phone numbers, dates and numbers.

## Known limits

8 kHz output is telephone quality. Without rule.far some text normalization cases are read literally.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
