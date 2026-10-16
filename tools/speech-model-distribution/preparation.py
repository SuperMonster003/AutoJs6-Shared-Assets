"""Download pinned upstream sherpa-onnx assets and repack them into deterministic mirror archives.

Downloads go to an ignored cache (default build/speech-models/upstream/<tag>/<asset>), are
verified by size and SHA-256 before use, and are only ever read as data. Archive members are
streamed into numbered blobs, never extracted by name, so hostile or case-colliding member
names cannot touch the file system.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit


def _distribution():
    key, path = "autojs6_speech_distribution", Path(__file__).with_name("distribution.py").resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise RuntimeError("Unexpected speech distribution module identity")
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


distribution = _distribution()
DistributionError = distribution.DistributionError
ALLOWED_DOWNLOAD_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
USER_AGENT = "AutoJs6-Shared-Assets speech-model-distribution"
CHUNK = 1024 * 1024


def check_download_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS or parsed.username or parsed.port not in (None, 443):
        raise DistributionError("Download redirected outside the allowed GitHub release hosts")
    return url


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        check_download_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def _opener():
    return urllib.request.build_opener(_RedirectGuard())


class _Incomplete(Exception):
    """The connection ended before the pinned size; the next attempt resumes."""


def download(url, target, size, sha256, *, attempts=5, opener=None, sleep=time.sleep):
    """Resumable download into target.part, verified before the atomic rename."""
    distribution.upstream_url(url)
    check_download_url(url)
    opener = opener or _opener()
    target = Path(target)
    partial = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(attempts):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > size:
            partial.unlink()
            offset = 0
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
        if offset:
            request.add_header("Range", f"bytes={offset}-")
        try:
            if offset < size:
                with opener.open(request, timeout=60) as response:
                    check_download_url(response.geturl())
                    if offset and getattr(response, "status", 200) != 206:
                        offset = 0
                    with partial.open("ab" if offset else "wb") as stream:
                        written = offset
                        for block in iter(lambda: response.read(CHUNK), b""):
                            written += len(block)
                            if written > size:
                                stream.close()
                                partial.unlink()
                                raise DistributionError("Upstream download exceeds its pinned size: " + url)
                            stream.write(block)
            if partial.stat().st_size < size:
                raise _Incomplete()
            digest, _ = distribution.sha256_file(partial, size)
            if digest != sha256:
                partial.unlink()
                raise DistributionError("Upstream SHA-256 differs from the pinned value: " + url)
            os.replace(partial, target)
            return target
        except (OSError, _Incomplete) as error:
            last_error = error
        sleep(min(30, 2 ** attempt))
    raise DistributionError(f"Upstream download failed after {attempts} attempts: {url}") from last_error


def cached_upstream(part, cache_dir, *, offline=False, fetch=download):
    tag, asset = distribution.upstream_url(part["url"])
    target = Path(cache_dir) / tag / asset
    if target.is_symlink():
        raise DistributionError("Cached upstream assets may not be symbolic links: " + str(target))
    if target.exists():
        digest, _ = distribution.sha256_file(target, part["size"]) if target.stat().st_size == part["size"] else ("", 0)
        if digest != part["sha256"]:
            raise DistributionError(f"Cached upstream asset differs from its pin; delete it and retry: {target}")
        return target
    if offline:
        raise DistributionError("Upstream asset is not cached and downloads are disabled: " + str(target))
    return fetch(part["url"], target, part["size"], part["sha256"])


def _stage_members(archive_path, members, blobs, records):
    pending = dict(members)
    with tarfile.open(archive_path, "r:bz2") as archive:
        for member in archive:
            target = pending.pop(member.name, None)
            if target is None:
                if member.name in members:
                    raise DistributionError("Upstream archive contains a selected member twice: " + member.name)
                continue
            if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or not 0 <= member.size <= distribution.MAX_FILE_BYTES:
                raise DistributionError("Selected upstream members must be regular files: " + member.name)
            blob = blobs / str(len(records))
            source = archive.extractfile(member)
            if source is None:
                raise DistributionError("Cannot read upstream member: " + member.name)
            with source, blob.open("wb") as stream:
                shutil.copyfileobj(source, stream, CHUNK)
            digest, size = distribution.sha256_file(blob)
            if size != member.size:
                raise DistributionError("Upstream member size differs from its header: " + member.name)
            records[target] = (blob, size, digest)
    if pending:
        raise DistributionError("Upstream archive lacks selected members: " + ", ".join(sorted(pending)))


def repack(source, cache_dir, output_dir, *, offline=False, fetch=download):
    """Measure the installed files and build the content-addressed archive; return (path, files, archive record).

    For an upstream-only source (mirror false) the selected members are still staged and measured,
    so files[] stays verifiable, but no archive is written and (None, files, None) is returned.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".work-", dir=output_dir))
    try:
        blobs = work / "blobs"
        blobs.mkdir()
        records = {}
        for part in source["upstream"]:
            path = cached_upstream(part, cache_dir, offline=offline, fetch=fetch)
            if part["format"] == "tar.bz2":
                _stage_members(path, part["members"], blobs, records)
            else:
                records[part["path"]] = (path, part["size"], part["sha256"])
        files = [{"path": path, "size": records[path][1], "sha256": records[path][2]} for path in sorted(records)]
        distribution.validate_files(files)
        if not source["mirror"]:
            return None, files, None
        entries = [(item["path"], item["size"], (lambda blob=records[item["path"]][0]: blob.open("rb"))) for item in files]
        temporary = work / "archive.tar"
        with temporary.open("wb") as stream:
            digest, size = distribution.write_archive(stream, entries)
            stream.flush()
            os.fsync(stream.fileno())
        if size != distribution.archive_size(item["size"] for item in files):
            raise DistributionError("Archive size differs from the canonical size")
        if distribution.read_archive(temporary) != files:
            raise DistributionError("Archive self-check failed")
        name = distribution.archive_file_name(source["modelId"], source["versionCode"], digest)
        target = output_dir / name
        if target.exists():
            existing, _ = distribution.sha256_file(target)
            if existing != digest:
                raise DistributionError("A different file already uses the content-addressed name: " + name)
        else:
            os.replace(temporary, target)
        return target, files, {"format": "tar", "size": size, "sha256": digest}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prepare(sources, cache_dir, output_dir, *, update_sources=False, offline=False, fetch=download, log=print):
    """Repack every (folder, source); return [(source, archive path)] after checking or recording measurements.

    The archive path is None for upstream-only sources; their files[] are measured and compared all the same.
    """
    result = []
    for folder, source in sources:
        label = f"{source['modelId']}/{source['versionCode']}"
        path, files, archive = repack(source, cache_dir, output_dir, offline=offline, fetch=fetch)
        measured = {"archive": archive, "files": files}
        installed = sum(item["size"] for item in files)
        if (source["archive"], source["files"]) != (archive, files):
            if not update_sources:
                raise DistributionError(f"{label}: rebuilt archive or files differ from source.json; nothing was recorded")
            updated = dict(source, **measured)
            distribution.validate_source(updated)
            (Path(folder) / "source.json").write_bytes(distribution.canonical_json_bytes(updated))
            source = updated
            if archive is None:
                log(f"{label}: recorded {len(files)} upstream-only files ({installed} bytes), no mirror archive")
            else:
                log(f"{label}: recorded {archive['size']} bytes, sha256 {archive['sha256']}")
        elif archive is None:
            log(f"{label}: verified {len(files)} upstream-only files ({installed} bytes), no mirror archive")
        else:
            log(f"{label}: reproduced {path.name} ({archive['size']} bytes)")
        result.append((source, path))
    return result
