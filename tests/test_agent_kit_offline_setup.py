from __future__ import annotations

import unittest
from pathlib import Path

from tools.package_agent_kit import ROOT, STATIC_FILES


class OfflineSetupPackageTests(unittest.TestCase):
    def test_android_setup_scripts_are_included_in_shareable_archive(self) -> None:
        packaged = {source.as_posix() for source, _ in STATIC_FILES}
        self.assertIn("agent-kit/offline/Setup-AndroidSDK.ps1", packaged)
        self.assertIn("agent-kit/offline/Warm-OfflineBuild.ps1", packaged)
        for source, _ in STATIC_FILES:
            self.assertTrue((ROOT / source).is_file(), f"Missing package input: {source}")

    def test_android_installer_uses_google_hash_and_does_not_auto_accept_licenses(self) -> None:
        script = (ROOT / "agent-kit/offline/Setup-AndroidSDK.ps1").read_text(encoding="utf-8")
        self.assertIn("https://dl.google.com/android/repository/commandlinetools-win-", script)
        self.assertIn("4d6931209eebb1bfb7c7e8b240a6a3cb3ab24479ea294f3539429574b1eec862", script)
        self.assertIn("--licenses", script)
        self.assertIn("GetEnvironmentVariable('Path', 'User')", script)
        self.assertIn("SetEnvironmentVariable('Path'", script)
        self.assertNotIn('communicate("y', script)
        self.assertNotIn("'y\n'", script)

    def test_offline_warmup_runs_real_offline_gradle_build(self) -> None:
        script = (ROOT / "agent-kit/offline/Warm-OfflineBuild.ps1").read_text(encoding="utf-8")
        self.assertIn("pub get --offline", script)
        self.assertIn("$gradle --offline", script)
        self.assertIn("flutter.Source build apk --debug", script)
        self.assertIn("flutter.Source test", script)

    def test_repository_guide_documents_megafile_and_local_offline_workflow(self) -> None:
        guide = (ROOT / "docs/OFFLINE_AGENT_KIT.ar.md").read_text(encoding="utf-8")
        self.assertIn("https://mega.nz/file/gy1TiJbK#kvhHFPNPDMgD06bZf5ozKk0TJOyIEI5xoPS44fZL4Ck", guide)
        self.assertIn("f9e0fa76800fbc5f764801b2ebe7413ad2fbce375e329ae5a3625ca0632a72b5", guide)
        self.assertIn("--offline", guide)
        self.assertIn("لا تحتوي", guide)

    def test_reliability_log_captures_open_risks_and_measured_probes(self) -> None:
        log = (ROOT / "docs/RELIABILITY_RISK_LOG.md").read_text(encoding="utf-8")
        self.assertIn("R-001", log)
        self.assertIn("R-004", log)
        self.assertIn("1.66 MiB/s", log)
        self.assertIn("developer.android.com/tools/sdkmanager", log)


if __name__ == "__main__":
    unittest.main()
