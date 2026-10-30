# Matcha-TTS Baker Chinese

Catalog model `tts.matcha.icefall.zh-baker`, version code 2. Kind `tts`, model type `matcha`.

- Languages: zh.
- Sample rate: 22050 Hz.
- Speakers: 1.
- License expression: `LicenseRef-NoLicenseDeclared AND MIT`; commercialUse: `false`.
- Upstream assets: `tts-models/matcha-icefall-zh-baker.tar.bz2`, `vocoder-models/hifigan_v2.onnx`.

## Origin

Acoustic model trained by k2-fsa with the icefall recipe egs/baker_zh/TTS (Matcha-TTS) and exported for sherpa-onnx; no license is declared for its weights. Vocoder hifigan_v2.onnx from the sherpa-onnx vocoder-models release: generator_v2 of https://github.com/jik876/hifi-gan (MIT) trained on LJ Speech (public domain).

## Training data

Data-Baker free corpus: about 12 hours, 10,000 sentences from one female speaker, non-commercial use only.

## Repacked contents

Acoustic model, lexicon, tokens and the three rule FSTs from the matcha archive, plus hifigan_v2.onnx (3.7 MB). sherpa-onnx 1.13.8 pairs this model with vocos-22khz-univ.onnx (53.9 MB, Apache-2.0) in its own APK; HiFi-GAN v2 was chosen here for size and keeps a single-source MIT vocoder. The jieba dict directory is omitted (unused since sherpa-onnx 1.12.15).

## Known limits

Single speaker. Vocoder quality is below the vocos alternative; a vocos variant would be a new versionCode.

## Version 2

k2-fsa replaced the upstream asset after version 1 was published, changing model-steps-3.onnx; version 2 (2026-10-30) pins the replacement with the same member selection and configuration, and sherpa-onnx 1.13.8 synthesizes intelligible speech with it. Version 1 stays in the catalog and keeps its mirror archive on `speech-models-v1`, but its upstream pin no longer matches, so it installs from the mirror only.

## License files

- `LICENSE`
- `LICENSE-hifigan`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
