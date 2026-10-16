# Keyword spotter, Chinese and English (3M)

Catalog model `kws.zipformer.zh-en.2025-12-20`, version code 1. Kind `kws`, model type `kws-transducer`.

- Languages: zh, en.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `kws-models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2`.

## Origin

Exported from https://modelscope.cn/models/pkufool/icefall-kws-zipformer-zh-en-3M-2025-12-20 (Apache License 2.0), a streaming Zipformer2 transducer trained with icefall.

## Training data

Not disclosed by the publisher.

## Repacked contents

chunk-16-left-64 int8 encoder and joiner with the float32 decoder, tokens and en.phone (the English phone lexicon used for phone+ppinyin keyword tokens). The chunk-8 (160 ms) variants, the float32 encoder and joiner and the test recordings are omitted.

## Known limits

Keywords must be converted to tokens (pinyin with tones for Chinese, ARPAbet phones for English). Detection thresholds need per-keyword tuning.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
