"""Environment writes must be verified, not assumed."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui import android_sdk, onboarding_app  # noqa: E402


class FakeKey:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    REG_SZ = 1
    REG_EXPAND_SZ = 2
    KEY_SET_VALUE = 1
    KEY_ALL_ACCESS = 1

    def __init__(self, silent: bool = False):
        self.store: dict = {}
        self.silent = silent

    def OpenKey(self, hive, path, reserved=0, access=0):
        return FakeKey(self)

    def QueryValueEx(self, key, name):
        if name not in key.owner.store:
            raise FileNotFoundError(name)
        return key.owner.store[name], 1

    def SetValueEx(self, key, name, reserved, value_type, value):
        if not key.owner.silent:
            key.owner.store[name] = value


class EnvPersistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-env-")
        self.addCleanup(self.temp.cleanup)
        self.real_data_dir = onboarding_app.paths.data_dir
        onboarding_app.paths.data_dir = lambda: self.temp.name

    def tearDown(self):
        onboarding_app.paths.data_dir = self.real_data_dir

    def _patch(self, fake):
        return patch.multiple(
            onboarding_app,
            winreg=fake,
            _broadcast_environment_change=lambda: None,
        )

    def test_set_user_env_verifies_readback(self):
        fake = FakeWinreg()
        with self._patch(fake):
            self.assertTrue(onboarding_app.set_user_env("JAVA_HOME", r"C:\jdk"))
        self.assertEqual(fake.store["JAVA_HOME"], r"C:\jdk")

    def test_set_user_env_reports_silent_failure(self):
        fake = FakeWinreg(silent=True)
        with self._patch(fake):
            self.assertFalse(onboarding_app.set_user_env("JAVA_HOME", r"C:\jdk"))

    def test_add_to_path_deduplicates_and_verifies(self):
        fake = FakeWinreg()
        fake.store["Path"] = r"C:\Windows"
        with self._patch(fake):
            self.assertTrue(onboarding_app.add_to_user_path(r"C:\flutter\bin"))
            self.assertTrue(onboarding_app.add_to_user_path(r"C:\flutter\bin"))
        parts = [p.lower() for p in fake.store["Path"].split(";")]
        self.assertEqual(parts.count(r"c:\flutter\bin"), 1)

    def test_add_to_path_reports_silent_failure(self):
        fake = FakeWinreg(silent=True)
        fake.store["Path"] = r"C:\Windows"
        with self._patch(fake):
            self.assertFalse(onboarding_app.add_to_user_path(r"C:\flutter\bin"))

    def test_android_sdk_persist_helpers_verify(self):
        fake = FakeWinreg()
        with patch.dict(sys.modules, {"winreg": fake}):
            self.assertTrue(android_sdk._persist_env("ANDROID_HOME", r"C:\sdk"))
        silent = FakeWinreg(silent=True)
        with patch.dict(sys.modules, {"winreg": silent}):
            self.assertFalse(android_sdk._persist_env("ANDROID_HOME", r"C:\sdk"))


if __name__ == "__main__":
    unittest.main()
