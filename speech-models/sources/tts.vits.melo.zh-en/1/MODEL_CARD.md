# MeloTTS Chinese and English (VITS)

Catalog model `tts.vits.melo.zh-en`, version code 1. Kind `tts`, model type `vits`.

- Languages: zh, en.
- Sample rate: 44100 Hz.
- Speakers: 1.
- License expression: `MIT`; commercialUse: `true`.
- Upstream assets: `tts-models/vits-melo-tts-zh_en.tar.bz2`.

## Origin

Converted by k2-fsa from https://huggingface.co/myshell-ai/MeloTTS-Chinese (MIT); the archive keeps the MyShell.ai MIT license.

## Training data

Not disclosed by the publisher. MeloTTS states that the library is free for commercial and non-commercial use.

## Repacked contents

model.onnx with lexicon, tokens and the phone and date rule FSTs used by the sherpa-onnx 1.13.8 TTS engine. model.int8.onnx is omitted because the upstream archive contains only a 133-byte Git LFS pointer under that name. number.fst, new_heteronym.fst and the jieba dict directory are omitted (dict_dir is unused since sherpa-onnx 1.12.15).

## Known limits

Single speaker (speaker id 0).

## License files

- `LICENSE`

The license audit with evidence links is `speech-models/audits/license-audit-v1.json`. The exact installed files and digests are recorded in `source.json`.
