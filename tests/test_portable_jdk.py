"""Portable JDK fallback and starter-project error capture."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import onboarding_app as app  # noqa: E402


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
        self.data = Path(self.temp.name)
        self.real_data_dir = app.paths.data_dir
        self.real_min = app.JDK_MIN_ZIP_BYTES
        app.paths.data_dir = lambda: str(self.data)
        app.JDK_MIN_ZIP_BYTES = 0

    def tearDown(self):
        app.paths.data_dir = self.real_data_dir
        app.JDK_MIN_ZIP_BYTES = self.real_min

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
