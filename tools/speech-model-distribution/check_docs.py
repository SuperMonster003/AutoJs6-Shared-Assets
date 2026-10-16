#!/usr/bin/env python3
"""Check the speech model documents: ASCII punctuation, relative links and the recorded signing key.

Covers speech-models/README.md, this tool's README.md and every source MODEL_CARD.md. The key ID and
SPKI fingerprint written in the family README must match speech-models/keys/catalog-signing-public.pem.
Standard library only; the markdown workflow runs it on Linux and Windows.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
KEY_ID_PATTERN = re.compile(r"Key ID: `(p256-[0-9a-f]{16})`")
SPKI_PATTERN = re.compile(r"SPKI DER SHA-256: `([0-9a-f]{64})`")


class DocumentError(ValueError):
    pass


def _markdown_rules(root):
    path = root / ".python/generate_markdown.py"
    spec = importlib.util.spec_from_file_location("autojs6_speech_markdown_rules", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def documents(root):
    paths = [root / "speech-models/README.md", root / "tools/speech-model-distribution/README.md"]
    paths += sorted((root / "speech-models/sources").glob("*/*/MODEL_CARD.md"))
    return paths


def spki_sha256(pem_path):
    lines = [line.strip() for line in pem_path.read_text(encoding="ascii").strip().splitlines()]
    if not lines or lines[0] != "-----BEGIN PUBLIC KEY-----" or lines[-1] != "-----END PUBLIC KEY-----":
        raise DocumentError("The speech catalog public key must be one PEM PUBLIC KEY block")
    try:
        return hashlib.sha256(base64.b64decode("".join(lines[1:-1]), validate=True)).hexdigest()
    except (ValueError, binascii.Error) as error:
        raise DocumentError("The speech catalog public key is not valid base64") from error


def check(root):
    root = Path(root).resolve()
    rules = _markdown_rules(root)
    checked = 0
    for path in documents(root):
        if not path.is_file():
            raise DocumentError("Missing document: " + str(path.relative_to(root)))
        text = path.read_text(encoding="utf-8")
        try:
            rules.validate_text(text, str(path.relative_to(root)))
        except rules.MarkdownGenerationError as error:
            raise DocumentError(str(error)) from error
        for target in LINK_PATTERN.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            relative = target.split("#", 1)[0]
            if not (path.parent / relative).resolve().exists():
                raise DocumentError(f"Broken relative link in {path.relative_to(root)}: {target}")
        checked += 1
    readme = (root / "speech-models/README.md").read_text(encoding="utf-8")
    fingerprint = spki_sha256(root / "speech-models/keys/catalog-signing-public.pem")
    key_ids, prints = set(KEY_ID_PATTERN.findall(readme)), set(SPKI_PATTERN.findall(readme))
    if key_ids != {"p256-" + fingerprint[:16]} or prints != {fingerprint}:
        raise DocumentError("speech-models/README.md must record exactly the checked-in key ID and SPKI fingerprint")
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        count = check(args.root)
    except (DocumentError, OSError, UnicodeError) as error:
        print("SPEECH_DOCS_ERROR " + str(error), file=sys.stderr)
        return 1
    print(f"SPEECH_DOCS_OK documents={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
