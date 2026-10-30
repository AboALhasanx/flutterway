"""The PnP driver hint must only fire for actual Android/ADB devices."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.onboarding_app import _looks_like_android_pnp  # noqa: E402


class PnpFilterTests(unittest.TestCase):
    def test_android_names_pass(self):
        for name in ("Android", "Android Composite ADB Interface", "My Android Phone", "ADB Interface"):
            self.assertTrue(_looks_like_android_pnp(name), name)

    def test_unrelated_devices_are_rejected(self):
        for name in ("Bluetooth Radio", "USB Input Device", "Generic PnP Monitor", "Realtek Audio", ""):
            self.assertFalse(_looks_like_android_pnp(name), name)

    def test_case_insensitive(self):
        self.assertTrue(_looks_like_android_pnp("ANDROID ADB"))


if __name__ == "__main__":
    unittest.main()
