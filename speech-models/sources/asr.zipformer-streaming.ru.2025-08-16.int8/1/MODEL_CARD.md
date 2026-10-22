# Streaming Zipformer, Russian (int8, small)

Catalog model `asr.zipformer-streaming.ru.2025-08-16.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: ru.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/alphacep/vosk-model-small-streaming-ru (Apache-2.0), the small streaming Zipformer of the Vosk project.

## Training data

The model page does not name its training corpora.

## Repacked contents

int8 encoder and joiner with the float32 decoder, tokens and the upstream README. `bpe.model` and the test recordings are omitted: sherpa-onnx hotwords need a `bpe.vocab`, which the upstream archive does not have.

## Known limits

Hotwords are unavailable. Russian only. A small model: accuracy is below larger Russian recognizers.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v2.json`. The exact installed files and digests are recorded in `source.json`.
