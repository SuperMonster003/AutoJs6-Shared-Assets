# CT-Transformer punctuation, Chinese and English (int8)

Catalog model `punct.ct-transformer.zh-en.2024-04-12.int8`, version code 1. Kind `punct`, model type `ct-transformer`.

- Languages: zh, en.
- Sample rate: none (the model works on text).
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2`.

## Origin

Converted by k2-fsa from https://modelscope.cn/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch (Apache-2.0) with the FunASR ONNX exporter and quantized to int8. Attribution: CT-Transformer punctuation model of the FunASR project by Alibaba DAMO Academy (https://github.com/modelscope/FunASR).

## Training data

The model page does not name its training corpora.

## Repacked contents

int8 model and the upstream README. `tokens.json`, `config.yaml` and the export scripts are omitted: sherpa-onnx reads the vocabulary and the punctuation list from the model metadata.

## Known limits

Punctuation only, no letter casing. Works on whole sentences, so it is applied to final results only. About 72 MiB, large for a text model.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v2.json`. The exact installed files and digests are recorded in `source.json`.
