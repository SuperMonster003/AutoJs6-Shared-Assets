# NeMo FastConformer, Spanish (int8)

Catalog model `asr.nemo-transducer.es.2026-05-03.int8`, version code 1. Kind `asr`, model type `offline-transducer`.

- Languages: es.
- Sample rate: 16000 Hz.
- License expression: `CC-BY-4.0`; commercialUse: `true`.
- Upstream assets: `asr-models/sherpa-onnx-nemo-fast-conformer-transducer-es-1424-int8.tar.bz2`.

## Origin

The transducer (RNN-T) head of NVIDIA `stt_es_fastconformer_hybrid_large_pc` (https://huggingface.co/nvidia/stt_es_fastconformer_hybrid_large_pc, CC-BY-4.0), a FastConformer hybrid transducer and CTC model that writes punctuation and capitalization. Exported to ONNX and quantized to int8 by k2-fsa; sherpa-onnx 1.13.8 loads it through `OfflineTransducerModelConfig` with model type `nemo_transducer`. The archive members carry a `./` prefix.

## Training data

NeMo ASRSET 1424 hours of Spanish, as listed on the model card: Mozilla Common Voice 12.0 (CC0-1.0), Multilingual LibriSpeech Spanish (CC-BY-4.0), VoxPopuli Spanish (CC0-1.0) and Fisher Spanish (LDC2010S01 and LDC2010T04, distributed by the Linguistic Data Consortium under its user agreements). NVIDIA publishes the trained weights under CC-BY-4.0.

## Repacked contents

int8 encoder, decoder and joiner with tokens. The test recording is omitted.

## Known limits

Offline model: the plugin recognizes each segment cut by voice activity detection, so text appears after a pause, not while speaking. Spanish only. Hotwords are not supported. Attribution to NVIDIA is required by CC-BY-4.0.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
