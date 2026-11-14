"""Checksum verification and safe zip extraction."""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from unittest import mock
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

    def test_resumable_download_appends_valid_range(self):
        target = self.root / "download.zip"
        target.with_suffix(".zip.part").write_bytes(b"prefix")
        response = mock.MagicMock()
        response.status = 206
        response.headers = {"Content-Length": "6", "Content-Range": "bytes 6-11/12"}
        response.read.side_effect = [b"suffix", b""]
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response) as open_url:
            result = downloads.resumable_download("https://example.test/file", str(target))
        self.assertTrue(result["ok"], result)
        self.assertEqual(target.read_bytes(), b"prefixsuffix")
        self.assertIn("Range", open_url.call_args.args[0].headers)

    def test_resumable_download_restarts_when_server_ignores_range(self):
        target = self.root / "download.zip"
        target.with_suffix(".zip.part").write_bytes(b"stale")
        response = mock.MagicMock()
        response.status = 200
        response.headers = {"Content-Length": "6"}
        response.read.side_effect = [b"fresh!", b""]
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = downloads.resumable_download("https://example.test/file", str(target))
        self.assertTrue(result["ok"], result)
        self.assertEqual(target.read_bytes(), b"fresh!")

    def test_resumable_download_keeps_partial_file_after_network_error(self):
        target = self.root / "download.zip"
        response = mock.MagicMock()
        response.status = 200
        response.headers = {"Content-Length": "12"}
        response.read.side_effect = [b"partial", OSError("connection dropped")]
        response.__enter__.return_value = response
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = downloads.resumable_download("https://example.test/file", str(target), retries=1)
        self.assertFalse(result["ok"], result)
        self.assertEqual(target.with_suffix(".zip.part").read_bytes(), b"partial")

    def test_resumable_download_promotes_complete_partial_after_http_416(self):
        target = self.root / "download.zip"
        target.with_suffix(".zip.part").write_bytes(b"complete")
        error = urllib.error.HTTPError(
            "https://example.test/file", 416, "Range not satisfiable",
            {"Content-Range": "bytes */8"}, io.BytesIO(b"")
        )
        with mock.patch("urllib.request.urlopen", side_effect=error):
            result = downloads.resumable_download("https://example.test/file", str(target))
        self.assertTrue(result["ok"], result)
        self.assertEqual(target.read_bytes(), b"complete")

    def test_resumable_download_cancel_callback_preserves_safe_partial(self):
        target = self.root / "download.zip"
        response = mock.MagicMock()
        response.status = 200
        response.headers = {"Content-Length": "12"}
        response.read.side_effect = [b"checkpoint", b""]
        response.__enter__.return_value = response

        def cancel(_received, _total):
            raise downloads.DownloadCancelled("user requested stop")

        with mock.patch("urllib.request.urlopen", return_value=response):
            result = downloads.resumable_download("https://example.test/file", str(target), progress=cancel)
        self.assertEqual(result["reason"], "cancelled")
        self.assertEqual(target.with_suffix(".zip.part").read_bytes(), b"checkpoint")
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
