"""Hot Reload must fall back to a normal build when no prebuilt APK exists."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.hot_reload import HotReloadSession  # noqa: E402


class HotReloadFallbackTests(unittest.TestCase):
    def setUp(self):
        self.session = HotReloadSession()

    def test_prebuilt_apk_is_used(self):
        command = self.session._command("SERIAL", r"C:\project\app-debug.signed.apk")
        self.assertIn("--use-application-binary", command)
        self.assertIn(r"C:\project\app-debug.signed.apk", command)

    def test_missing_apk_builds_normally(self):
        command = self.session._command("SERIAL", None)
        self.assertNotIn("--use-application-binary", command)
        self.assertIn("run", command)
        self.assertIn("SERIAL", command)


if __name__ == "__main__":
    unittest.main()
