# Piper ar_JO SA miro V2 (high, int8)

Catalog model `tts.vits.piper.ar-jo-sa-miro-v2-high.int8`, version code 1. Kind `tts`, model type `vits`.

- Languages: ar.
- Sample rate: 22050 Hz.
- Speakers: 1.
- License expression: `CC-BY-NC-ND-4.0 AND GPL-3.0-or-later`; commercialUse: `false`.
- Distribution: upstream only (`mirror` is null in the catalog); clients install the listed files from the sherpa-onnx release asset.
- Upstream assets: `tts-models/vits-piper-ar_JO-SA_miro_V2-high-int8.tar.bz2`.

## Origin

Converted and quantized to int8 by k2-fsa from OpenVoiceOS `phoonnx_ar-SA_miro_espeak_V2` (https://huggingface.co/OpenVoiceOS/phoonnx_ar-SA_miro_espeak_V2), a Piper-compatible VITS voice trained with phoonnx (https://github.com/TigreGotico/phoonnx) and licensed CC BY-NC-ND 4.0. espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

TigreGotico `tts-train-synthetic-miro_ar-SA` (https://huggingface.co/datasets/TigreGotico/tts-train-synthetic-miro_ar-SA), synthetic Arabic speech licensed CC BY-NC-ND 4.0.

## Installed contents

int8 model (the file keeps the `.onnx` name of the float32 voice), its Piper JSON configuration, tokens and espeak-ng-data. The upstream README.md is omitted: it is a saved Hugging Face web page, not the model card. No mirror archive is built: the model is NoDerivatives and the sherpa-onnx conversion rewrites its ONNX metadata, so on 2026-10-25 the maintainer chose not to redistribute it (Q85). `files[]` is still measured from the upstream members, so the upstream download is verified file by file.

## Known limits

Single male speaker. Arabic only. Undiacritized input is read through eSpeak NG and some words are mispronounced. Availability depends on the sherpa-onnx `tts-models` release asset staying in place; there is no fallback.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
