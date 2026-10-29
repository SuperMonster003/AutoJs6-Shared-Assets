# Whisper tiny language identification

Catalog model `langid.whisper.tiny.int8`, version code 1. Kind `langid`, model type `whisper-langid`.

- Languages: mul (the 99 languages of Whisper).
- Sample rate: 16000 Hz.
- License expression: `MIT`; commercialUse: `unknown` (the training data is not disclosed).
- Upstream assets: `asr-models/sherpa-onnx-whisper-tiny.tar.bz2` (SHA-256 matching the `checksum.txt` of the sherpa-onnx `asr-models` release).

## Origin

OpenAI Whisper `tiny` (multilingual; https://github.com/openai/whisper, MIT). Exported to ONNX and quantized to int8 by k2-fsa; sherpa-onnx 1.13.8 loads the encoder and decoder through `SpokenLanguageIdentificationWhisperConfig` and answers the Whisper language code of up to 30 s of speech, without a score. The plugin votes over several speech windows (plugin roadmap D144, D148).

## Training data

About 680,000 hours of audio with transcripts collected from the web, as described in the Whisper paper (https://arxiv.org/abs/2212.04356). OpenAI does not name the sources or their licenses, so commercialUse is unknown and the catalog uses the training-data notice (plugin roadmap D144, taken like decision Q80 of the license audit).

## Repacked contents

`tiny-encoder.int8.onnx` and `tiny-decoder.int8.onnx`. The float32 copies, the token table (language identification does not decode text) and the test recordings are left out.

## Known limits

Measured for the plugin (plugin roadmap D144) on 108 synthetic sentences in 11 languages and three human recordings: 97.3% of whole sentences right, 94.6% when only the first 2 s are used; the errors were Spanish heard as Italian or Portuguese. Closely related languages, code switching and very short clips are hard. The decoder holds the whole Whisper vocabulary, so it is much larger than the encoder. One 30 s window took 0.69 s on an Xperia XZ1 Compact (Android 9).

## License files

- `LICENSE` (MIT, from https://github.com/openai/whisper)

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
