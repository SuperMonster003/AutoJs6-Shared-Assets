"""Synthetic fixtures for the speech model distribution tests: no network, keys or real models."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

TOOL_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = TOOL_DIR.parents[1]
BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
TIME1 = "2026-01-01T00:00:00Z"
TIME2 = "2026-01-02T00:00:00Z"
REPOSITORY = "SuperMonster003/AutoJs6-Shared-Assets"
LONG_DIRECTORY = "espeak-ng-data/" + "/".join(["deeply-nested-directory-name"] * 3)


def load(name, filename=None):
    key, path = "autojs6_speech_" + name, (TOOL_DIR / (filename or name + ".py")).resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("Unexpected speech distribution module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


distribution = load("distribution")
preparation = load("preparation")


def tts_members():
    return {
        "model.onnx": bytes(range(256)) * 9 + b"tail",
        "tokens.txt": b"a 0\nb 1\n",
        "lexicon.txt": b"hello h e l l o\n",
        "espeak-ng-data/phontab": b"phoneme table",
        "espeak-ng-data/voices/!v/Mr serious": b"variant\n",
        LONG_DIRECTORY + "/a-file-with-a-rather-long-name-that-forces-a-ustar-prefix-split.dat": b"x" * 700,
        "README.md": b"# fixture\n",
    }


def write_upstream(cache, tag, asset, top, members, *, extra=None, link=None):
    """Write a tar.bz2 into cache/<tag>/<asset> and return its upstream part record."""
    path = Path(cache) / tag / asset
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:bz2", format=tarfile.PAX_FORMAT) as archive:
        directory = tarfile.TarInfo(top)
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, content in list(members.items()) + list((extra or {}).items()):
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size, info.mtime = len(content), 1234567890
            archive.addfile(info, io.BytesIO(content))
        if link:
            info = tarfile.TarInfo(f"{top}/{link}")
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            archive.addfile(info)
    data = path.read_bytes()
    return {"url": f"{BASE}/{tag}/{asset}", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "format": "tar.bz2",
            "members": {f"{top}/{name}": name for name in members}}


def write_raw(cache, tag, asset, content, path):
    target = Path(cache) / tag / asset
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {"url": f"{BASE}/{tag}/{asset}", "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "format": "file", "path": path}


def source_value(model_id, upstream, config, *, kind="tts", model_type="vits", speakers=2, code=1, mirror=True, **extra):
    value = {"format": 1, "modelId": model_id, "versionCode": code, "kind": kind, "modelType": model_type,
             "displayName": {"en": "Unit fixture", "zh-CN": "Unit fixture (zh-CN)"},
             "summary": {"en": "Synthetic offline unit test", "zh-CN": "Synthetic unit test (zh-CN)"},
             "recommended": False, "languages": ["zh", "en"], "sampleRate": 16000, "releasedAt": TIME1,
             "license": {"spdx": "Apache-2.0", "commercialUse": True, "noticeKey": "speech_model_license_commercial"},
             "runtime": {"minSherpaOnnx": "1.13.8", "config": config}, "mirror": mirror, "upstream": upstream,
             "archive": None, "files": None}
    if kind == "tts":
        value["speakers"] = speakers
    value.update(extra)
    return value


def write_source(root, value):
    folder = Path(root) / value["modelId"] / str(value["versionCode"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "source.json").write_bytes(distribution.canonical_json_bytes(value))
    (folder / "MODEL_CARD.md").write_text("# Synthetic fixture\n", encoding="utf-8")
    (folder / "LICENSE").write_text("Synthetic unit-test text, not a license grant.\n", encoding="utf-8")
    return folder


def tts_fixture(sources, cache, model_id="tts.vits.unit-test", code=1, members=None, **extra):
    members = members or tts_members()
    part = write_upstream(cache, "tts-models", f"{model_id}-v{code}.tar.bz2", f"{model_id}-v{code}", members,
                          extra={"test_wavs/0.wav": b"RIFF-not-installed"})
    config = {"model": "model.onnx", "tokens": "tokens.txt", "lexicon": ["lexicon.txt"], "dataDir": "espeak-ng-data"}
    return write_source(sources, source_value(model_id, [part], config, code=code, **extra))


def asr_fixture(sources, cache, model_id="asr.online.unit-test"):
    members = {"encoder.int8.onnx": b"encoder" * 50, "decoder.onnx": b"decoder", "tokens.txt": b"<blk> 0\n"}
    part = write_upstream(cache, "asr-models", model_id + ".tar.bz2", model_id, members)
    raw = write_raw(cache, "asr-models", "joiner-raw.onnx", b"joiner-bytes", "joiner.int8.onnx")
    config = {"encoder": "encoder.int8.onnx", "decoder": "decoder.onnx", "joiner": "joiner.int8.onnx", "tokens": "tokens.txt",
              "modelType": "zipformer2"}
    return write_source(sources, source_value(model_id, [part, raw], config, kind="asr", model_type="online-transducer"))


UPSTREAM_ONLY_ID = "asr.sense-voice.unit-test"


def upstream_only_fixture(sources, cache, model_id=UPSTREAM_ONLY_ID):
    """An upstream-only source (mirror false): files are measured, but no archive is ever built."""
    members = {"model.int8.onnx": b"sense-voice" * 40, "tokens.txt": b"<blk> 0\n", "README.md": b"# upstream only\n"}
    part = write_upstream(cache, "asr-models", model_id + ".tar.bz2", model_id, members, extra={"test_wavs/zh.wav": b"RIFF"})
    config = {"model": "model.int8.onnx", "tokens": "tokens.txt"}
    value = source_value(model_id, [part], config, kind="asr", model_type="sense-voice", mirror=False,
                         license={"spdx": "LicenseRef-NoLicenseDeclared", "commercialUse": False,
                                  "noticeKey": "speech_model_license_non_commercial"})
    return write_source(sources, value)


def measure(sources, cache, output):
    """Run offline preparation with --update-sources semantics and return the archives."""
    loaded = distribution.load_sources(sources, require_measured=False)
    return preparation.prepare(loaded, cache, output, update_sources=True, offline=True, log=lambda _message: None)


def read_source(folder):
    return json.loads((Path(folder) / "source.json").read_text(encoding="utf-8"))
