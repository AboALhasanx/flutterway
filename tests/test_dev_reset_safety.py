"""Developer reset must not delete student projects by name alone."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui import dev_reset, onboarding_app  # noqa: E402


class DevResetSafetyTests(unittest.TestCase):
    def test_projects_and_recent_list_are_not_deleted(self):
        with tempfile.TemporaryDirectory(prefix="fw-reset-") as temp:
            desktop = Path(temp)
            project = desktop / "my_first_app"
            project.mkdir()
            (project / "main.dart").write_text("student work", encoding="utf-8")
            lectures = desktop / "FlutterProjects"
            lectures.mkdir()
            recent = desktop / "recent_projects.json"
            recent.write_text("[]", encoding="utf-8")
            with patch.object(dev_reset.paths, "lecture_projects_dir", return_value=str(lectures)), \
                 patch.object(dev_reset.paths, "recent_projects_file", return_value=str(recent)):
                logs: list[str] = []
                dev_reset.reset_projects(logs)
            self.assertTrue((project / "main.dart").exists())
            self.assertTrue(lectures.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(any("لم يُحذف" in line for line in logs))

    def test_api_requires_dev_mode(self):
        api = onboarding_app.OnboardingApi({})
        with patch.object(onboarding_app, "dev_mode_enabled", return_value=False):
            result = api.dev_reset_action("projects")
        self.assertFalse(result["success"])
        self.assertIn("المطور", result["error"])


if __name__ == "__main__":
    unittest.main()
