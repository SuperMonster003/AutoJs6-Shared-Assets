# pyannote speaker segmentation 3.0

Catalog model `segment.pyannote.3-0`, version code 1. Kind `segment`, model type `pyannote-segmentation`.

- Languages: zxx (the model looks at voices, not words; it works for any language).
- Sample rate: 16000 Hz.
- License expression: `MIT`; commercialUse: `false` (one named training set is for research only, see below).
- Upstream assets: `speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2` (6,958,444 bytes; its size matches the GitHub release, which publishes no checksum for this tag).

## Origin

`pyannote/segmentation-3.0` by the pyannote.audio project (Hervé Bredin, CNRS; https://huggingface.co/pyannote/segmentation-3.0, MIT). Exported to ONNX by k2-fsa; sherpa-onnx 1.13.8 loads it through `OfflineSpeakerSegmentationPyannoteModelConfig` inside `OfflineSpeakerDiarization`. It labels every 10 s window with up to three overlapping speakers (powerset encoding); the plugin pairs it with a `speaker` embedding model to cluster the speakers of a whole file (plugin roadmap D146, D154).

## Training data

The model card names the training sets of AISHELL-4, AliMeeting, AMI, AVA-AVD, DIHARD III, Ego4D, MSDWild, REPERE and VoxConverse. MSDWild is published "ONLY for research purposes" under its own license agreement, so the catalog records commercialUse false (license audit policy: a named training set that limits use to research takes precedence). The details and evidence are in the license audit.

## Repacked contents

Only the float32 `model.onnx` (5,992,913 bytes). The int8 copy, the export and test scripts and the README of the upstream archive are left out: on 14 synthetic LibriSpeech dialogs the float32 model counted the speakers of all 14 right at the plugin's default clustering threshold 0.85, the int8 model 13 (plugin roadmap D154).

## Known limits

Measured for the plugin (plugin roadmap D146, D154) with the ERes2Net VoxCeleb embedding model: frame error rate (DER without collar) 0.221 on the 14 dialogs (2 to 4 speakers, 60 to 123 s), 0.144 with a 0.25 s collar. Overlapping speech, very short turns, far microphones and similar voices lower the accuracy. A 63 s two-speaker dialog took 19 s on an Xperia XZ1 Compact (Android 9), most of it in the embedding model.

## License files

- `LICENSE` (MIT, copied from the upstream archive)

The license audit with evidence links is `speech-models/audits/license-audit-v3.json`. The exact installed files and digests are recorded in `source.json`.
