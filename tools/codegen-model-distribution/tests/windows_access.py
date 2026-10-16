"""Windows DACL checks for outputs staged through tempfile.mkdtemp(); imported by the tests, not a test module."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
import uuid


windows_mkdtemp_dacl = unittest.skipUnless(os.name == "nt" and sys.version_info >= (3, 13),
                                           "only Python 3.13+ on Windows gives mkdtemp() a restricted DACL")
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


def plain_directory(test):
    """A directory made by a plain mkdir under the temporary root, so it inherits like a checkout does."""
    path = Path(tempfile.gettempdir()) / ("autojs6-codegen-acl-" + uuid.uuid4().hex)
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
