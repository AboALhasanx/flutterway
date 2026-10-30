"""Build/install truth: a failed or unconfirmed adb install is never success."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.onboarding_app import install_outcome, install_succeeded  # noqa: E402


class InstallTruthTests(unittest.TestCase):
    def test_success_line_and_zero_rc(self):
        self.assertTrue(install_succeeded(0, "Performing Streamed Install\nSuccess\n"))
        self.assertEqual(install_outcome(0, "Success"), (True, None))

    def test_non_zero_returncode_is_failure(self):
        ok, code = install_outcome(1, "Success")
        self.assertFalse(ok)
        self.assertEqual(code, "install_failed")

    def test_missing_success_line_is_not_success(self):
        ok, code = install_outcome(0, "Performing Streamed Install\n")
        self.assertFalse(ok)
        self.assertEqual(code, "install_unconfirmed")

    def test_failure_message_is_not_success(self):
        ok, code = install_outcome(1, "adb: failed to install app.apk: INSTALL_FAILED_INSUFFICIENT_STORAGE")
        self.assertFalse(ok)
        self.assertEqual(code, "install_failed")


if __name__ == "__main__":
    unittest.main()
