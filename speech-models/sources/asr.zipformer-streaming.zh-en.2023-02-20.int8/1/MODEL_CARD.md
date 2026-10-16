# Streaming Zipformer, Chinese and English (int8)

Catalog model `asr.zipformer-streaming.zh-en.2023-02-20.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: zh, en.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2`.

## Origin

Converted by k2-fsa from the TorchScript model https://huggingface.co/pfluo/k2fsa-zipformer-chinese-english-mixed (Apache-2.0), trained with the icefall recipe egs/librispeech/ASR/pruned_transducer_stateless7_streaming.

## Training data

The publisher describes the training data only as tens of thousands of hours of an internal dataset (a 12k_hour subset is named in the training configuration). No dataset with a non-commercial restriction is named.

## Repacked contents

int8 encoder and joiner with the float32 decoder, the combination used by sherpa-onnx 1.13.8 OnlineRecognizer type 8. The float32 encoder and joiner, the int8 decoder, bpe.model and the test recordings are omitted. bpe.vocab is kept for cjkchar+bpe hotwords.

## Known limits

Chunked streaming model of the first Zipformer generation (modelType zipformer). Accuracy on accented or far-field speech is not measured here.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
