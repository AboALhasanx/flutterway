"""Checksum verification and safe zip extraction."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui import downloads  # noqa: E402


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-dl-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "tool.zip"
        self.file.write_bytes(b"payload")
        self.sha = hashlib.sha256(b"payload").hexdigest()

    def test_verify_ok(self):
        result = downloads.verify_file(str(self.file), self.sha, min_bytes=1)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["sha256"], self.sha)

    def test_verify_rejects(self):
        self.assertFalse(downloads.verify_file(str(self.file), "0" * 64)["ok"])
        self.assertEqual(downloads.verify_file(str(self.file), self.sha, 999)["reason"], "too_small")
        self.assertEqual(downloads.verify_file(str(self.root / "nope"), self.sha)["reason"], "missing_file")
        self.assertEqual(downloads.verify_file(str(self.file), "")["reason"], "missing_checksum")

    def test_safe_extract_ok(self):
        with zipfile.ZipFile(self.file, "w") as bundle:
            bundle.writestr("jdk/bin/java.exe", b"x")
        out = self.root / "out"
        result = downloads.safe_extract_zip(str(self.file), str(out))
        self.assertTrue(result["ok"], result)
        self.assertTrue((out / "jdk" / "bin" / "java.exe").exists())

    def test_safe_extract_blocks_traversal(self):
        for name in ("../evil.txt", "a/../../evil.txt", "/abs/evil.txt"):
            with self.subTest(name=name):
                archive = self.root / "bad.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(name, b"evil")
                result = downloads.safe_extract_zip(str(archive), str(self.root / "safe"))
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["reason"], "unsafe_path")
                self.assertFalse((self.root / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
