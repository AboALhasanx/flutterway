from __future__ import annotations

import sys
import unittest
from unittest import mock

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import android_sdk  # noqa: E402


class AndroidSdkAdapterTests(unittest.TestCase):
    def test_android_cli_package_paths_use_official_slash_syntax(self):
        self.assertEqual(
            android_sdk._android_cli_packages(["platform-tools", "platforms;android-36", "build-tools;36.0.0"]),
            ["platform-tools", "platforms/android-36", "build-tools/36.0.0"],
        )

    def test_android_cli_is_preferred_when_present(self):
        with mock.patch.object(android_sdk.shutil, "which", side_effect=lambda name: "C:/tools/android.exe" if name == "android" else None):
            self.assertEqual(android_sdk._android_cli(), "C:/tools/android.exe")

    def test_android_cli_installs_sdk_without_metrics_and_can_accept_prompts(self):
        process = mock.MagicMock()
        process.communicate.return_value = ("Packages installed", None)
        process.returncode = 0
        with (
            mock.patch.object(android_sdk, "_android_cli", return_value="C:/tools/android.exe"),
            mock.patch.object(android_sdk, "_startupinfo", return_value=None),
            mock.patch.object(android_sdk.paths, "jdk_home", return_value=None),
            mock.patch.object(android_sdk.subprocess, "Popen", return_value=process) as popen,
        ):
            code, output = android_sdk._run_android_cli("C:/Android/Sdk", ["platforms;android-36"], timeout=10)
        self.assertEqual(code, 0)
        self.assertIn("Packages installed", output)
        command = popen.call_args.args[0]
        self.assertEqual(command, ["C:/tools/android.exe", "--sdk=C:/Android/Sdk", "--no-metrics", "sdk", "install", "platforms/android-36"])
        self.assertTrue(popen.call_args.kwargs["stdin"] is not None)


if __name__ == "__main__":
    unittest.main()
