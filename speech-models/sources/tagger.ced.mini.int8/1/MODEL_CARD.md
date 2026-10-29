# CED-mini audio tagging

Catalog model `tagger.ced.mini.int8`, version code 1. Kind `tagger`, model type `ced`.

- Languages: zxx (sounds, not speech; the labels are English).
- Sample rate: 16000 Hz.
- License expression: `CC-BY-4.0 AND CC-BY-SA-4.0`; commercialUse: `true`.
- Upstream assets: `audio-tagging-models/sherpa-onnx-ced-mini-audio-tagging-2024-04-19.tar.bz2` (SHA-256 matching the `checksum.txt` of the sherpa-onnx `audio-tagging-models` release).

## Origin

CED-mini (Consistent Ensemble Distillation, Xiaomi; https://github.com/RicherMans/CED). The sherpa-onnx export converts the checkpoint published on Zenodo (record 8275347, CC-BY-4.0); the same weights are also published on Hugging Face as `mispeech/ced-mini` under Apache-2.0. Quantized to int8 by k2-fsa; sherpa-onnx 1.13.8 loads it through `AudioTaggingModelConfig.ced`. It scores the 527 AudioSet classes of up to 10 s of audio; the plugin tags longer files in 10 s windows (plugin roadmap D145, D149).

## Training data

AudioSet (Google): about two million 10 s YouTube clips. The labels are released under CC-BY-4.0 and the class ontology under CC-BY-SA-4.0; the audio itself stays on YouTube and is not distributed with the model.

## Repacked contents

`model.int8.onnx` and `class_labels_indices.csv`, the AudioSet class table (index, machine id and English display name) that the plugin shows as labels. The float32 copy, the test recordings and the README of the upstream archive are left out.

## Known limits

Measured for the plugin (plugin roadmap D145) on ESC-50 (10 clips of each of the 48 classes with a matching AudioSet label): the expected label was among the first three in 88.8% of the clips and first in 70.2%. Labels are English only; overlapping sounds, quiet sounds and classes rare in AudioSet score lower. One 10 s window took 234 ms on an Xperia XZ1 Compact (Android 9).

## License files

- `LICENSE` (CC-BY-4.0, the license of the Zenodo checkpoint)
- `LICENSE-audioset-ontology` (CC-BY-SA-4.0, the license of the AudioSet ontology that `class_labels_indices.csv` comes from)

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
