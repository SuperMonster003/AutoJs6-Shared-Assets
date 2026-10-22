# Piper de_DE thorsten (medium, int8)

Catalog model `tts.vits.piper.de-de-thorsten-medium.int8`, version code 1. Kind `tts`, model type `vits`.

- Languages: de.
- Sample rate: 22050 Hz.
- Speakers: 1.
- License expression: `MIT AND GPL-3.0-or-later`; commercialUse: `false`.
- Upstream assets: `tts-models/vits-piper-de_DE-thorsten-medium-int8.tar.bz2`.

## Origin

Converted and quantized to int8 by k2-fsa from https://huggingface.co/rhasspy/piper-voices (de/de_DE/thorsten/medium, MIT). espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

The voice is trained on the Thorsten-Voice dataset (https://github.com/thorstenMueller/Thorsten-Voice, CC0). Its Piper model card says it is fine-tuned from the U.S. English lessac voice (medium), whose Lessac Blizzard 2013 data (https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html) is licensed for research purposes only, excluding commercial voice synthesis products. Following that lineage, the catalog sets commercialUse to false, as for the lessac voice of catalog v1.

## Repacked contents

int8 model (the file keeps the `.onnx` name of the float32 voice), its Piper JSON configuration, tokens, the Piper model card and espeak-ng-data.

## Known limits

Single speaker. German only. int8 quantization may sound slightly worse than the float32 voice.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v2.json`. The exact installed files and digests are recorded in `source.json`.
