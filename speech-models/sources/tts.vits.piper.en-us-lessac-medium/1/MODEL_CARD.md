# Piper en_US lessac (medium)

Catalog model `tts.vits.piper.en-us-lessac-medium`, version code 1. Kind `tts`, model type `vits`.

- Languages: en.
- Sample rate: 22050 Hz.
- Speakers: 1.
- License expression: `MIT AND GPL-3.0-or-later`; commercialUse: `false`.
- Upstream assets: `tts-models/vits-piper-en_US-lessac-medium.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/rhasspy/piper-voices (en/en_US/lessac/medium, MIT). espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

Lessac Blizzard 2013 (https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html): licensed for research purposes only, excluding commercial voice synthesis products. The catalog therefore sets commercialUse to false.

## Repacked contents

float32 model (the D10 choice; vits-piper-en_US-lessac-medium-int8 at 21 MB is a smaller future candidate), its Piper JSON configuration, tokens, the Piper model card and espeak-ng-data.

## Known limits

Single speaker. English only.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
