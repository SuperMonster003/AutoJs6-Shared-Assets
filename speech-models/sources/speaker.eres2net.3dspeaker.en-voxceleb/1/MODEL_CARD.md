# ERes2Net speaker embedding, VoxCeleb

Catalog model `speaker.eres2net.3dspeaker.en-voxceleb`, version code 1. Kind `speaker`, model type `speaker-embedding`.

- Languages: en, zh (measured; the model itself does not depend on the language).
- Sample rate: 16000 Hz.
- License expression: `Apache-2.0`; commercialUse: `true`.
- Upstream assets: `speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx` (the upstream release tag is spelled this way).

## Origin

ERes2Net speaker verification model `iic/speech_eres2net_sv_en_voxceleb_16k` of the 3D-Speaker project (https://github.com/modelscope/3D-Speaker, Apache-2.0; model card https://www.modelscope.cn/models/iic/speech_eres2net_sv_en_voxceleb_16k). Exported to ONNX by k2-fsa; sherpa-onnx 1.13.8 loads it through `SpeakerEmbeddingExtractorConfig`. It turns 16 kHz speech into a 192-dimensional embedding (voiceprint); the plugin compares embeddings by cosine similarity (plugin roadmap D132-D141).

## Training data

VoxCeleb2 dev (https://www.robots.ox.ac.uk/~vgg/data/voxceleb/), speech of over 5,000 celebrities from interview videos in many languages, released by the Visual Geometry Group, University of Oxford, under CC-BY-4.0. The dataset page states that the copyright of the source videos remains with their owners.

## Repacked contents

The single ONNX file, installed as `model.onnx`.

## Known limits

Measured for the plugin (plugin roadmap D137, D138) with three enrollment clips per speaker averaged: equal error rate on 2 s test clips 0.6% for English (LibriSpeech test-clean, 40 speakers) and 0.7% for Mandarin (AISHELL-1, 12 speakers). At the plugin's default cosine threshold 0.50, 2 s clips gave false rejects of 2.5% (English) and 0% (Mandarin) and false accepts of 0.05% and 0.9%. Shorter clips, noise, other microphones and voice imitation lower the accuracy; a voiceprint is a convenience check, not a security credential. Extracting a 2 s clip took 85 ms on an Xperia 1 V (Android 13) and 393 ms on an Xperia XZ1 Compact (Android 9).

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
