"""Portable JDK fallback and starter-project error capture."""

from __future__ import annotations

import io
import json
import logging
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import diagnostics, onboarding_app as app  # noqa: E402


class FakeCreateProcess:
    def __init__(self, *args, **kwargs):
        self.stdout = io.StringIO("Creating project...\nError: pub get failed\n")
        self.returncode = 1

    def wait(self, timeout=None):
        return 1

    def kill(self):
        pass

    def poll(self):
        return 1


class PortableJdkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._close_test_logger)
        self.data = Path(self.temp.name)
        self.real_data_dir = app.paths.data_dir
        self.real_min = app.JDK_MIN_ZIP_BYTES
        self.real_checksum = app._adoptium_checksum
        app.paths.data_dir = lambda: str(self.data)
        app.JDK_MIN_ZIP_BYTES = 0
        # Offline by default: no metadata request during tests.
        app._adoptium_checksum = lambda: None

    @staticmethod
    def _close_test_logger():
        """Close the file handler before TemporaryDirectory removes its files."""
        logger = logging.getLogger("flutterway")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        diagnostics._logger = None
        diagnostics._log_path = None

    def tearDown(self):
        app.paths.data_dir = self.real_data_dir
        app.JDK_MIN_ZIP_BYTES = self.real_min
        app._adoptium_checksum = self.real_checksum

    def test_extracts_portable_jdk_without_admin(self):
        cache = self.data / "cache"
        cache.mkdir(parents=True)
        zip_path = cache / "temurin21.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("jdk-21.0.1/bin/java.exe", b"fake")
            archive.writestr("jdk-21.0.1/release", "JAVA_VERSION=21")
        result = app._install_portable_jdk()
        self.assertIsNotNone(result)
        self.assertTrue((self.data / "jdk-21" / "bin" / "java.exe").exists())
        self.assertFalse((cache / "jdk_extract").exists())

    def _cached_zip(self) -> Path:
        cache = self.data / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        zip_path = cache / "temurin21.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("jdk-21.0.1/bin/java.exe", b"fake")
            archive.writestr("jdk-21.0.1/release", "JAVA_VERSION=21")
        return zip_path

    def test_checksum_mismatch_rejects_archive(self):
        zip_path = self._cached_zip()
        app._adoptium_checksum = lambda: "0" * 64
        self.assertIsNone(app._install_portable_jdk())
        self.assertFalse(zip_path.exists(), "a rejected archive must be deleted")
        self.assertFalse((self.data / "jdk-21").exists())

    def test_checksum_match_extracts(self):
        import hashlib
        zip_path = self._cached_zip()
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        app._adoptium_checksum = lambda: digest
        self.assertIsNotNone(app._install_portable_jdk())
        self.assertTrue((self.data / "jdk-21" / "bin" / "java.exe").exists())

    def test_checksum_metadata_parsing(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps([
                    {"binary": {"package": {"checksum": "a" * 64}}},
                    {"binary": {"package": {"checksum": "b" * 64}}},
                ]).encode("utf-8")

        real_urlopen = app.urllib.request.urlopen
        app._adoptium_checksum = self.real_checksum
        app.urllib.request.urlopen = lambda *a, **k: FakeResponse()
        try:
            self.assertEqual(app._adoptium_checksum(), "a" * 64)
        finally:
            app.urllib.request.urlopen = real_urlopen

    def test_starter_project_failure_keeps_real_error(self):
        api = app.OnboardingApi({})
        project = self.data / "broken_project"
        real_popen = app.subprocess.Popen
        real_template = app.paths.starter_template_dir
        real_flutter = app.paths.flutter_bat
        app.subprocess.Popen = lambda *a, **k: FakeCreateProcess()
        app.paths.starter_template_dir = lambda: None
        app.paths.flutter_bat = lambda: str(self.data / "flutter.bat")
        (self.data / "flutter.bat").write_text("", encoding="utf-8")
        try:
            ok = api._ensure_starter_project(str(project))
        finally:
            app.subprocess.Popen = real_popen
            app.paths.starter_template_dir = real_template
            app.paths.flutter_bat = real_flutter
        self.assertFalse(ok)
        self.assertIn("pub get failed", api.state.get("starter_project_error", ""))


if __name__ == "__main__":
    unittest.main()
