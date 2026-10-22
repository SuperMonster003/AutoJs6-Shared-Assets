# Streaming Zipformer, Korean (int8)

Catalog model `asr.zipformer-streaming.ko.2024-06-16.int8`, version code 1. Kind `asr`, model type `online-transducer`.

- Languages: ko.
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `false`.
- Distribution: upstream only (`mirror` is null in the catalog); clients install the listed files from the sherpa-onnx release asset.
- Upstream assets: `asr-models/sherpa-onnx-streaming-zipformer-korean-2024-06-16.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/johnBamma/icefall-asr-ksponspeech-pruned-transducer-stateless7-streaming-2024-06-12 (Apache-2.0), trained with the icefall pruned_transducer_stateless7_streaming recipe (streaming Zipformer, sherpa-onnx model type `zipformer`).

## Training data

KsponSpeech from AI Hub (https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=realm&dataSetSn=123). Applications for the data are open to Korean nationals only, and the AI Hub usage policy (https://aihub.or.kr/intrcn/guid/usagepolicy.do?currMenu=151&topMenu=105) requires a separate agreement for use outside Korea. The catalog therefore sets commercialUse to false.

## Installed contents

int8 encoder and joiner with the float32 decoder, and tokens. `bpe.model`, the float32 encoder and joiner, the int8 decoder and the test recordings are omitted. No mirror archive is built: on 2026-10-22 the maintainer decided not to redistribute these weights, because the training data terms restrict use outside Korea. `files[]` is still measured from the upstream members, so the upstream download is verified file by file.

## Known limits

Hotwords are unavailable because the archive has no BPE vocabulary. Korean only. Availability depends on the sherpa-onnx `asr-models` release asset staying in place; there is no fallback.

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v2.json`. The exact installed files and digests are recorded in `source.json`.
