# Kokoro v1.1 Chinese and English

Catalog model `tts.kokoro.multi-lang.v1_1`, version code 1. Kind `tts`, model type `kokoro`.

- Languages: zh, en.
- Sample rate: 24000 Hz.
- Speakers: 103.
- License expression: `Apache-2.0 AND GPL-3.0-or-later`; commercialUse: `true`.
- Upstream assets: `tts-models/kokoro-multi-lang-v1_1.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh (Apache-2.0). espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

More than 100 hours: Chinese recordings permissively granted by LongMaoData and about 3 hours of crowdsourced synthetic English, as described by the publisher.

## Repacked contents

float32 model.onnx (the D10 choice; kokoro-int8-multi-lang-v1_1 at 147 MB is a smaller future candidate), voices, tokens, the US English and Chinese lexicons, the three Chinese rule FSTs and espeak-ng-data, matching the sherpa-onnx 1.13.8 TTS engine configuration. lexicon-gb-en.txt and the jieba dict directory are omitted.

## Known limits

Large download and memory footprint for phones. Speakers 0-2 are English (af_maple, af_sol, bf_vale); 3-102 are Chinese.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
