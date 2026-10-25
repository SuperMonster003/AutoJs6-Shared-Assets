# Kokoro v1.0 multilingual (int8)

Catalog model `tts.kokoro.multi-lang.v1_0.int8`, version code 1. Kind `tts`, model type `kokoro`.

- Languages: en, zh, es, fr, hi, it, pt.
- Sample rate: 24000 Hz.
- Speakers: 54.
- License expression: `Apache-2.0 AND GPL-3.0-or-later`; commercialUse: `true`.
- Upstream assets: `tts-models/kokoro-int8-multi-lang-v1_0.tar.bz2`.

## Origin

Converted and quantized to int8 by k2-fsa from Kokoro-82M v1.0 (https://huggingface.co/hexgrad/Kokoro-82M, Apache-2.0). espeak-ng-data is compiled eSpeak NG data (GPL-3.0-or-later) from the fork https://github.com/csukuangfj/espeak-ng used by sherpa-onnx.

## Training data

Per the publisher, only permissive or non-copyrighted audio with IPA phoneme labels: public domain audio, audio under licenses such as Apache and MIT, CC BY audio and synthetic audio from large TTS providers. The individual corpora are not itemized.

## Repacked contents

int8 model.int8.onnx, voices, tokens, the US English and Chinese lexicons, the three Chinese rule FSTs, the upstream README and LICENSE and espeak-ng-data, matching the configuration of `tts.kokoro.multi-lang.v1_1`. lexicon-gb-en.txt and the jieba dict directory are omitted.

## Known limits

Speakers: 0-19 American English, 20-27 British English (read with the US lexicon), 28-29 and 53 Spanish, 30 French, 31-34 Hindi, 35-36 Italian, 37-41 Japanese, 42-44 Brazilian Portuguese, 45-52 Chinese. Spanish, French, Hindi, Italian and Portuguese text is read through eSpeak NG, so the plugin passes the speaker's language to sherpa-onnx (`lang`). The five Japanese speakers are not offered: sherpa-onnx 1.13.8 accepts `lang` only for en, es, fr, hi, it and pt-br. Slower than real time on older phones (a Sony G8441 measured a real-time factor of 3.2 - 4.5 with four threads); the plugin splits text into sentences, so audio starts after the first sentence.

## License files

- `LICENSE`
- `LICENSE-espeak-ng-data`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
