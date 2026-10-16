"""Canonical USTAR writer and strict reader."""

import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("autojs6_speech_test_support", Path(__file__).with_name("support.py"))
support = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
if not hasattr(support, "distribution"):
    _spec.loader.exec_module(support)
distribution = support.distribution
DistributionError = distribution.DistributionError


def entries(members):
    return [(path, len(content), (lambda content=content: io.BytesIO(content))) for path, content in sorted(members.items())]


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.members = support.tts_members()

    def write(self, name="a.tar", members=None):
        path = self.root / name
        with path.open("wb") as stream:
            digest, size = distribution.write_archive(stream, entries(members or self.members))
        return path, digest, size

    def test_output_is_deterministic_canonical_and_readable_by_tarfile(self):
        first, digest, size = self.write("first.tar")
        second, digest2, _ = self.write("second.tar")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(digest, digest2)
        self.assertEqual(size, first.stat().st_size)
        self.assertEqual(size, distribution.archive_size(len(content) for content in self.members.values()))
        with tarfile.open(first) as archive:
            names = archive.getnames()
            self.assertEqual(sorted(self.members), names)
            for member in archive.getmembers():
                self.assertEqual((0o644, 0, 0, 0, "", ""), (member.mode, member.uid, member.gid, member.mtime, member.uname, member.gname))
                self.assertEqual(self.members[member.name], archive.extractfile(member).read())
        listed = distribution.read_archive(first)
        self.assertEqual([item["path"] for item in listed], sorted(self.members))
        self.assertEqual(listed[0]["sha256"], distribution.sha256_bytes(self.members[listed[0]["path"]]))

    def test_long_paths_use_the_ustar_prefix_and_unsplittable_paths_are_rejected(self):
        long_path = next(path for path in self.members if len(path) > 100)
        name, prefix = distribution.ustar_split(long_path)
        self.assertTrue(prefix and len(name) <= 100 and len(prefix) <= 155)
        with self.assertRaises(DistributionError):
            distribution.ustar_split("a" * 120)
        with self.assertRaises(DistributionError):
            distribution.install_path("a" * 160 + "/" + "b" * 90)

    def test_writer_requires_sorted_unique_paths_and_exact_member_sizes(self):
        with self.assertRaisesRegex(DistributionError, "ascending"):
            distribution.write_archive(io.BytesIO(), list(reversed(entries(self.members))))
        with self.assertRaisesRegex(DistributionError, "ended early"):
            distribution.write_archive(io.BytesIO(), [("a", 10, lambda: io.BytesIO(b"short"))])
        with self.assertRaisesRegex(DistributionError, "grew"):
            distribution.write_archive(io.BytesIO(), [("a", 1, lambda: io.BytesIO(b"long"))])

    def test_reader_rejects_noncanonical_headers_padding_order_and_trailers(self):
        path, _digest, _size = self.write()
        original = path.read_bytes()

        def mutated(change):
            data = bytearray(original)
            change(data)
            path.write_bytes(bytes(data))
            with self.assertRaises(DistributionError):
                distribution.read_archive(path)

        mutated(lambda data: data.__setitem__(slice(136, 147), b"00000000001"))  # mtime
        mutated(lambda data: data.__setitem__(slice(100, 107), b"0000755"))  # mode
        first_size = len(self.members[sorted(self.members)[0]])
        mutated(lambda data: data.__setitem__(512 + first_size, 1))  # padding byte
        mutated(lambda data: data.extend(b"\0" * 512))  # extra trailer
        mutated(lambda data: data.__delitem__(slice(len(data) - 512, len(data))))  # truncated trailer
        reordered = self.root / "reordered.tar"
        with reordered.open("wb") as stream:
            for path_, size, opener in reversed(entries({"b": b"1", "a": b"2"})):
                stream.write(distribution.tar_header(path_, size))
                stream.write(opener().read().ljust(512, b"\0"))
            stream.write(b"\0" * 1024)
        with self.assertRaisesRegex(DistributionError, "ascending"):
            distribution.read_archive(reordered)

    def test_path_grammar_rejects_traversal_hidden_absolute_and_non_ascii_paths(self):
        for value in ("../x", "a/../x", "/x", "a//b", ".hidden", "a/.hidden", "a\\b", "space ", "-flag", "a/", "\u00e9", "", "a" * 241):
            with self.subTest(value=value), self.assertRaises(DistributionError):
                distribution.install_path(value)
        for value in ("espeak-ng-data/voices/!v/Mr serious", "lexicon-us-en.txt", "a/b.c/d_e+f"):
            distribution.install_path(value)


if __name__ == "__main__":
    unittest.main()
