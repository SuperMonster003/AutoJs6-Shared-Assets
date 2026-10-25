# Piper ar_JO SA dii (high, int8)

Catalog model `tts.vits.piper.ar-jo-sa-dii-high.int8`, version code 1. Kind `tts`, model type `vits`.

- Languages: ar.
- Sample rate: 22050 Hz.
- Speakers: 1.
- License expression: `CC-BY-NC-SA-4.0 AND GPL-3.0-or-later`; commercialUse: `false`.
- Upstream assets: `tts-models/vits-piper-ar_JO-SA_dii-high-int8.tar.bz2`.

## Origin

Converted and quantized to int8 by k2-fsa (https://github.com/k2-fsa/sherpa-onnx/pull/2480) from OpenVoiceOS `phoonnx_ar-SA_dii_espeak` (https://huggingface.co/OpenVoiceOS/phoonnx_ar-SA_dii_espeak), a Piper-compatible VITS voice trained with phoonnx (https://github.com/TigreGotico/phoonnx) from the `phoonnx_ar-SA_miro_espeak` checkpoint. The upstream README licenses the model under CC BY-NC-SA 4.0. espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

TigreGotico `tts-train-synthetic-dii_ar-diacritics` (https://huggingface.co/datasets/TigreGotico/tts-train-synthetic-dii_ar-diacritics), synthetic Arabic speech licensed CC BY-NC-ND 4.0. Both the model and its data are non-commercial.

## Repacked contents

int8 model (the file keeps the `.onnx` name of the float32 voice), its Piper JSON configuration, tokens, the upstream README with the license statement and espeak-ng-data.

## Known limits

Single female speaker. Arabic only. The voice was trained on diacritized text; undiacritized input is read through eSpeak NG and some words are mispronounced.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
