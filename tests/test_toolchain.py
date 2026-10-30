"""Pinned Flutter release parsing and verified installation."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui import paths, toolchain  # noqa: E402


def build_archive(path: Path, with_flutter: bool = True) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        if with_flutter:
            archive.writestr("flutter/bin/flutter.bat", "@echo off")
            archive.writestr("flutter/bin/cache/flutter.version.json", '{"frameworkVersion":"3.19.0"}')
        else:
            archive.writestr("notes/readme.txt", "not flutter")
    return path.read_bytes()


def manifest(archive_name: str, sha: str, size: int, version: str = "3.19.0") -> dict:
    return {
        "current_release": {"stable": "hash-stable"},
        "releases": [
            {"hash": "hash-beta", "channel": "beta", "version": "3.20.0-beta", "release_date": "2026-01-01",
             "archive": "beta/" + archive_name, "sha256": "b" * 64, "size": size},
            {"hash": "hash-stable", "channel": "stable", "version": version, "release_date": "2025-12-01",
             "archive": "stable/" + archive_name, "sha256": sha, "size": size},
        ],
    }


class ManifestTests(unittest.TestCase):
    def test_bundled_manifest_is_valid(self):
        data = toolchain.load_bundled_manifest()
        self.assertIsNotNone(data, "bundled manifest must ship with the app")
        release = toolchain.parse_release_manifest(data, "stable")
        self.assertIsNotNone(release)
        self.assertRegex(release.sha256, r"^[0-9a-f]{64}$")
        self.assertTrue(release.archive.endswith(".zip"))

    def test_resolves_from_bundled_when_network_fails(self):
        real_urlopen = toolchain.urllib.request.urlopen if hasattr(toolchain, "urllib") else None
        import urllib.request

        def boom(*args, **kwargs):
            raise OSError("offline")

        original = urllib.request.urlopen
        urllib.request.urlopen = boom
        try:
            release = toolchain.resolve_flutter_release("stable")
        finally:
            urllib.request.urlopen = original
        self.assertIsNotNone(release)
        self.assertTrue(release.version)

    def test_picks_current_stable(self):
        release = toolchain.parse_release_manifest(manifest("flutter.zip", "a" * 64, 10), "stable")
        self.assertEqual(release.version, "3.19.0")
        self.assertEqual(release.sha256, "a" * 64)
        self.assertEqual(release.archive_name, "flutter.zip")

    def test_unknown_channel(self):
        self.assertIsNone(toolchain.parse_release_manifest(manifest("f.zip", "a" * 64, 1), "dev"))

    def test_rejects_missing_checksum(self):
        data = manifest("f.zip", "a" * 64, 1)
        data["releases"][1]["sha256"] = ""
        self.assertIsNone(toolchain.parse_release_manifest(data, "stable"))


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-tc-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.real_data_dir = paths.data_dir
        paths.data_dir = lambda: str(self.root / "appdata")
        (self.root / "appdata" / "cache").mkdir(parents=True)
        self.source = self.root / "source.zip"
        self.size = len(build_archive(self.source))
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.target = self.root / "flutter"

    def tearDown(self):
        paths.data_dir = self.real_data_dir

    def _downloader(self, url, target, progress=None):
        Path(target).write_bytes(self.source.read_bytes())
        return True

    def test_install_verified_archive(self):
        release = toolchain.FlutterRelease("3.19.0", "stable/flutter.zip", self.sha, self.size)
        result = toolchain.install_flutter_archive(str(self.target), release, downloader=self._downloader)
        self.assertTrue(result["success"], result)
        self.assertTrue((self.target / "bin" / "flutter.bat").exists())
        self.assertEqual(result["version"], "3.19.0")

    def test_checksum_mismatch_refuses(self):
        release = toolchain.FlutterRelease("3.19.0", "stable/flutter.zip", "0" * 64, self.size)
        result = toolchain.install_flutter_archive(str(self.target), release, downloader=self._downloader)
        self.assertFalse(result["success"])
        self.assertFalse(self.target.exists())

    def test_existing_sdk_kept_when_new_archive_is_bad(self):
        self.target.mkdir()
        (self.target / "keep.txt").write_text("old sdk", encoding="utf-8")
        bad = self.root / "bad.zip"
        bad.write_bytes(build_archive(bad, with_flutter=False))
        sha = hashlib.sha256(bad.read_bytes()).hexdigest()
        release = toolchain.FlutterRelease("9.9.9", "stable/bad.zip", sha, len(bad.read_bytes()))

        def downloader(url, target_path, progress=None):
            Path(target_path).write_bytes(bad.read_bytes())
            return True

        result = toolchain.install_flutter_archive(str(self.target), release, downloader=downloader)
        self.assertFalse(result["success"])
        self.assertTrue((self.target / "keep.txt").exists())
        self.assertEqual((self.target / "keep.txt").read_text(encoding="utf-8"), "old sdk")

    def test_zip_slip_archive_rejected(self):
        evil = self.root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("flutter/../../evil.txt", "evil")
            archive.writestr("flutter/bin/flutter.bat", "@echo off")
        sha = hashlib.sha256(evil.read_bytes()).hexdigest()
        release = toolchain.FlutterRelease("3.19.0", "stable/evil.zip", sha, len(evil.read_bytes()))

        def downloader(url, target_path, progress=None):
            Path(target_path).write_bytes(evil.read_bytes())
            return True

        result = toolchain.install_flutter_archive(str(self.target), release, downloader=downloader)
        self.assertFalse(result["success"])
        self.assertIn("غير آمن", result["error"])
        self.assertFalse((self.root / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
