# Whisper base language identification

Catalog model `langid.whisper.base.int8`, version code 1. Kind `langid`, model type `whisper-langid`.

- Languages: mul (the 99 languages of Whisper).
- Sample rate: 16000 Hz.
- License expression: `MIT`; commercialUse: `unknown` (the training data is not disclosed).
- Upstream assets: `asr-models/sherpa-onnx-whisper-base.tar.bz2` (SHA-256 matching the `checksum.txt` of the sherpa-onnx `asr-models` release).

## Origin

OpenAI Whisper `base` (multilingual; https://github.com/openai/whisper, MIT). Exported to ONNX and quantized to int8 by k2-fsa; sherpa-onnx 1.13.8 loads the encoder and decoder through `SpokenLanguageIdentificationWhisperConfig` and answers the Whisper language code of up to 30 s of speech, without a score. The plugin votes over several speech windows (plugin roadmap D144, D148).

## Training data

About 680,000 hours of audio with transcripts collected from the web, as described in the Whisper paper (https://arxiv.org/abs/2212.04356). OpenAI does not name the sources or their licenses, so commercialUse is unknown and the catalog uses the training-data notice (plugin roadmap D144, taken like decision Q80 of the license audit).

## Repacked contents

`base-encoder.int8.onnx` and `base-decoder.int8.onnx`. The float32 copies, the token table (language identification does not decode text) and the test recordings are left out.

## Known limits

Measured for the plugin (plugin roadmap D144) on 108 synthetic sentences in 11 languages and three human recordings: 98.2% of whole sentences right, 96.4% when only the first 2 s are used (tiny: 97.3% and 94.6%). Closely related languages, code switching and very short clips are hard. One 30 s window took 1.34 s on an Xperia XZ1 Compact (Android 9), about twice as long as tiny, with about 110 MiB more memory.

## License files

- `LICENSE` (MIT, from https://github.com/openai/whisper)

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
