"""Build/install truth: a failed or unconfirmed adb install is never success."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.onboarding_app import build_artifact_usable, install_outcome, install_succeeded  # noqa: E402


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

    def test_failed_build_does_not_reuse_existing_apk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            apk = Path(temp_dir) / "old-app.apk"
            apk.write_bytes(b"previous build")
            self.assertFalse(build_artifact_usable(1, str(apk)))
            self.assertTrue(build_artifact_usable(0, str(apk)))

    def test_successful_build_requires_an_apk_file(self):
        self.assertFalse(build_artifact_usable(0, "missing-app.apk"))


if __name__ == "__main__":
    unittest.main()
