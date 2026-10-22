# CNN-BiLSTM punctuation and casing, English (int8)

Catalog model `punct.cnn-bilstm.en.2024-08-06.int8`, version code 1. Kind `punct`, model type `cnn-bilstm`.

- Languages: en.
- Sample rate: none (the model works on text).
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `punctuation-models/sherpa-onnx-online-punct-en-2024-08-06.tar.bz2`.

## Origin

Downloaded by k2-fsa from https://huggingface.co/frankyoujian/Edge-Punct-Casing (sherpa-onnx-cnn-bilstm-unigram-bpe-en) of the Edge-Punct-Casing project (https://github.com/frankyoujian/Edge-Punct-Casing, Apache-2.0). The upstream archive is packed from `.`, so its member names start with `./`, which catalog schema 2 allows.

## Training data

The project does not name its training corpora.

## Repacked contents

int8 model, its BPE vocabulary and the upstream README. The float32 model is omitted.

## Known limits

English only. Restores casing and punctuation of whole sentences; it does not correct recognition errors.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v2.json`. The exact installed files and digests are recorded in `source.json`.
