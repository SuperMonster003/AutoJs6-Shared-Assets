"""Synthetic fixtures for the speech model distribution tests: no network, keys or real models."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import unittest
import uuid

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
    if kind == "punct":
        del value["sampleRate"]
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


PUNCT_ID = "punct.ct-transformer.unit-test"
CASING_ID = "punct.cnn-bilstm.unit-test"


def punct_fixtures(sources, cache):
    """The two punctuation model types of catalog schema 2: ct-transformer and cnn-bilstm.

    The cnn-bilstm archive is packed from "." like sherpa-onnx-online-punct-en, so its member names start with "./".
    """
    folders = []
    for model_id, top, model_type, members, config in (
            (PUNCT_ID, PUNCT_ID, "ct-transformer", {"model.int8.onnx": b"ct-transformer" * 30, "config.yaml": b"punc_list: []\n"},
             {"model": "model.int8.onnx"}),
            (CASING_ID, distribution.MEMBER_PREFIX + CASING_ID, "cnn-bilstm",
             {"model.int8.onnx": b"cnn-bilstm" * 30, "bpe.vocab": b"<unk> 0\n"}, {"model": "model.int8.onnx", "bpeVocab": "bpe.vocab"})):
        part = write_upstream(cache, "punctuation-models", model_id + ".tar.bz2", top, members)
        folders.append(write_source(sources, source_value(model_id, [part], config, kind="punct", model_type=model_type,
                                                          languages=["en"])))
    return folders


OFFLINE_TRANSDUCER_ID = "asr.nemo-transducer.unit-test"


def offline_transducer_fixture(sources, cache, model_id=OFFLINE_TRANSDUCER_ID):
    """An offline NeMo transducer of catalog v3 (schema 2 type offline-transducer); packed from "." like the upstream."""
    members = {"encoder.int8.onnx": b"nemo-encoder" * 40, "decoder.int8.onnx": b"nemo-decoder", "joiner.int8.onnx": b"joiner",
               "tokens.txt": b"<unk> 0 "}
    part = write_upstream(cache, "asr-models", model_id + ".tar.bz2", distribution.MEMBER_PREFIX + model_id, members,
                          extra={"test_wavs/es.wav": b"RIFF"})
    config = {"encoder": "encoder.int8.onnx", "decoder": "decoder.int8.onnx", "joiner": "joiner.int8.onnx", "tokens": "tokens.txt",
              "modelType": "nemo_transducer"}
    return write_source(sources, source_value(model_id, [part], config, kind="asr", model_type="offline-transducer", languages=["es"]))


SPEAKER_ID = "speaker.eres2net.unit-test"


def speaker_fixture(sources, cache, model_id=SPEAKER_ID):
    """A speaker embedding model of catalog schema 3: one raw ONNX file, like the speaker-recongition-models assets."""
    raw = write_raw(cache, "speaker-recongition-models", "unit_test_speaker_16k.onnx", b"speaker-embedding" * 30, "model.onnx")
    return write_source(sources, source_value(model_id, [raw], {"model": "model.onnx"}, kind="speaker", model_type="speaker-embedding",
                                              languages=["en", "zh"]))



SEGMENT_ID = "segment.pyannote.unit-test"
LANGID_ID = "langid.whisper.unit-test"
TAGGER_ID = "tagger.ced.unit-test"


def analysis_fixtures(sources, cache):
    """The three analysis kinds of catalog schema 3, as tar.bz2 archives with float32 or int8 duplicates left out:
    a pyannote segmentation model, a whisper encoder and decoder without their tokens, and a CED tagger with its labels."""
    segment = write_upstream(cache, "speaker-segmentation-models", SEGMENT_ID + ".tar.bz2", SEGMENT_ID,
                             {"model.onnx": b"pyannote" * 40}, extra={"model.int8.onnx": b"int8", "LICENSE": b"MIT"})
    langid = write_upstream(cache, "asr-models", LANGID_ID + ".tar.bz2", LANGID_ID,
                            {"tiny-encoder.int8.onnx": b"whisper-encoder" * 30, "tiny-decoder.int8.onnx": b"whisper-decoder" * 20},
                            extra={"tiny-encoder.onnx": b"fp32", "tiny-tokens.txt": b"<|en|> 0"})
    tagger = write_upstream(cache, "audio-tagging-models", TAGGER_ID + ".tar.bz2", TAGGER_ID,
                            {"model.int8.onnx": b"ced" * 60, "class_labels_indices.csv": b'index,mid,display_name\n0,/m/09x0r,"Speech"\n'},
                            extra={"model.onnx": b"fp32", "test_wavs/1.wav": b"RIFF"})
    return [
        write_source(sources, source_value(SEGMENT_ID, [segment], {"model": "model.onnx"}, kind="segment",
                                           model_type="pyannote-segmentation", languages=["zxx"])),
        write_source(sources, source_value(LANGID_ID, [langid], {"encoder": "tiny-encoder.int8.onnx", "decoder": "tiny-decoder.int8.onnx"},
                                           kind="langid", model_type="whisper-langid", languages=["mul"])),
        write_source(sources, source_value(TAGGER_ID, [tagger], {"model": "model.int8.onnx", "labels": "class_labels_indices.csv"},
                                           kind="tagger", model_type="ced", languages=["zxx"])),
    ]


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


# Windows access rights -----------------------------------------------------------------------

MKDTEMP_ACCOUNTS = frozenset({"SY", "BA", "OW"})  # SYSTEM, Administrators, OWNER RIGHTS


def dacl_entries(path):
    """Return (control flags, ACE strings) of the DACL of path, e.g. ("AI", ["A;ID;FA;;;SY", ...])."""
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get = advapi32.GetNamedSecurityInfoW
    get.argtypes = (wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD) + (ctypes.c_void_p,) * 4 + (ctypes.POINTER(ctypes.c_void_p),)
    get.restype = wintypes.DWORD
    convert = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p)
    convert.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    descriptor, text = ctypes.c_void_p(), wintypes.LPWSTR()
    error = get(str(path), 1, 4, None, None, None, None, ctypes.byref(descriptor))  # SE_FILE_OBJECT, DACL only
    if error:
        raise OSError(None, ctypes.FormatError(error), str(path), error)
    try:
        if not convert(descriptor, 1, 4, ctypes.byref(text), None):  # SDDL_REVISION_1, DACL only
            raise ctypes.WinError(ctypes.get_last_error())
        flags, entries = re.fullmatch(r"D:([A-Z]*)((?:\([^()]*\))*)", text.value).groups()
    finally:
        kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        kernel32.LocalFree(descriptor)
    return flags, re.findall(r"\(([^()]*)\)", entries)


def mkdtemp_is_restricted():
    """Whether tempfile.mkdtemp() gives a new directory a protected DACL (Windows since Python 3.12.4 and 3.13)."""
    if os.name != "nt":
        return False
    path = tempfile.mkdtemp()
    try:
        return "P" in dacl_entries(path)[0]
    finally:
        os.rmdir(path)


windows_mkdtemp_dacl = unittest.skipUnless(mkdtemp_is_restricted(), "tempfile.mkdtemp() does not restrict new directories here")


def plain_directory(test):
    """A directory made by a plain mkdir under the temporary root, so it inherits like a checkout does."""
    path = Path(tempfile.gettempdir()) / ("autojs6-speech-acl-" + uuid.uuid4().hex)
    path.mkdir()
    test.addCleanup(shutil.rmtree, path)
    if {entry.split(";")[5] for entry in dacl_entries(path)[1]} <= MKDTEMP_ACCOUNTS:
        test.skipTest("the temporary root grants nothing beyond SYSTEM, Administrators and the owner")
    return path


def assert_inherited_access(test, root):
    """root and everything below it carry the DACL that a plain mkdir or file creation gives at the same place."""
    flags, entries = dacl_entries(root)
    test.assertNotIn("P", flags, "the DACL is still protected from inheritance")
    test.assertTrue(any("ID" in re.findall("..", entry.split(";")[1]) for entry in entries), entries)
    test.assertFalse({entry.split(";")[5] for entry in entries} <= MKDTEMP_ACCOUNTS, entries)
    for path in [root, *sorted(root.rglob("*"))]:
        reference = path.parent / (".plain-" + ("directory" if path.is_dir() else "file"))
        if not reference.exists():
            reference.mkdir() if path.is_dir() else reference.write_bytes(b"")
        test.assertEqual(dacl_entries(reference)[1], dacl_entries(path)[1], path)
        test.assertNotIn("P", dacl_entries(path)[0], path)
        if path.is_file():
            with path.open("rb") as stream:
                stream.read(1)
