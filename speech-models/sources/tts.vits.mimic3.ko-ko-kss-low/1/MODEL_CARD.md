# Mimic 3 ko_KO KSS (low)

Catalog model `tts.vits.mimic3.ko-ko-kss-low`, version code 1. Kind `tts`, model type `vits`.

- Languages: ko.
- Sample rate: 22050 Hz.
- Speakers: 1.
- License expression: `CC0-1.0 AND GPL-3.0-or-later`; commercialUse: `false`.
- Upstream assets: `tts-models/vits-mimic3-ko_KO-kss_low.tar.bz2`.

## Origin

Converted by k2-fsa from the Mycroft Mimic 3 voice `ko_KO/kss_low` (https://github.com/MycroftAI/mimic3-voices/tree/master/voices/ko_KO/kss_low), whose LICENSE file is the CC0 1.0 dedication; that file ships as `LICENSE`. espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

The Korean Single Speaker Speech dataset (KSS, https://www.kaggle.com/datasets/bryanpark/korean-single-speaker-speech-dataset), licensed CC BY-NC-SA 4.0. Because the data is non-commercial, the catalog sets commercialUse to false although the weights are CC0.

## Repacked contents

The model, its Mimic 3 JSON configuration, tokens and espeak-ng-data. The k2-fsa conversion scripts (vits-mimic3.py, vits-mimic3.sh) and the README are omitted; the README appends the Apache-2.0 text of those scripts, which does not apply to the voice.

## Known limits

Single female speaker. Korean only. Low quality tier: audible artifacts compared with the medium and high Piper voices.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
