"""Quarantine replaces deletion; ownership requires a marker."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui import dev_reset, managed, onboarding_app, quarantine  # noqa: E402


def make_project(root: Path, name: str = "proj", marker: bool = True) -> Path:
    project = root / name
    (project / "lib").mkdir(parents=True)
    (project / "lib" / "main.dart").write_text("void main() {}", encoding="utf-8")
    (project / "pubspec.yaml").write_text("name: proj\n", encoding="utf-8")
    if marker:
        assert managed.write_marker(str(project), "starter_project")
    return project


class MarkerTests(unittest.TestCase):
    def test_marker_roundtrip_and_classification(self):
        with tempfile.TemporaryDirectory(prefix="fw-mk-") as temp:
            project = make_project(Path(temp))
            self.assertTrue(managed.is_managed(str(project)))
            self.assertEqual(managed.classify(str(project)), "managed_verified")
            other = make_project(Path(temp), "other", marker=False)
            self.assertEqual(managed.classify(str(other)), "managed_unverified")
            self.assertFalse(managed.write_marker(str(other), "nope"))
            self.assertFalse(managed.write_marker(str(Path(temp) / "missing"), "starter_project"))


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-q-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "appdata"
        self.data.mkdir()
        self.real_data_dir = quarantine.paths.data_dir
        quarantine.paths.data_dir = lambda: str(self.data)
        dev_reset.paths.data_dir = lambda: str(self.data)

    def tearDown(self):
        quarantine.paths.data_dir = self.real_data_dir
        logger = logging.getLogger("flutterway")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def test_quarantine_moves_and_restores(self):
        project = make_project(self.root / "projects")
        expected_files, expected_size = quarantine._tree_stats(str(project))
        result = quarantine.quarantine(str(project), "test", [str(self.root / "projects")])
        self.assertTrue(result["success"], result)
        self.assertFalse(project.exists())
        self.assertEqual(result["manifest"]["file_count"], expected_files)
        self.assertEqual(result["manifest"]["size_bytes"], expected_size)
        items = quarantine.list_items()
        self.assertEqual(len(items), 1)
        restored = quarantine.restore(result["id"])
        self.assertTrue(restored["success"], restored)
        self.assertTrue((project / "lib" / "main.dart").exists())
        self.assertEqual(restored["file_count"], expected_files)
        self.assertEqual(quarantine.list_items(), [])

    def test_restore_refuses_non_empty_destination(self):
        project = make_project(self.root / "projects")
        result = quarantine.quarantine(str(project), "test", [str(self.root / "projects")])
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("x", encoding="utf-8")
        restored = quarantine.restore(result["id"], str(occupied))
        self.assertFalse(restored["success"])
        self.assertTrue((occupied / "keep.txt").exists())
        self.assertTrue((project / "pubspec.yaml").exists() is False)  # still quarantined

    def test_purge_requires_matching_confirmation(self):
        project = make_project(self.root / "projects")
        result = quarantine.quarantine(str(project), "test", [str(self.root / "projects")])
        item = result["id"]
        self.assertFalse(quarantine.purge(item, "DELETE")["success"])
        self.assertFalse(quarantine.purge(item, "delete " + item)["success"])
        self.assertEqual(len(quarantine.list_items()), 1)
        self.assertTrue(quarantine.purge(item, f"DELETE {item}")["success"])
        self.assertEqual(quarantine.list_items(), [])

    def test_traversal_and_root_refused(self):
        outside = make_project(self.root / "outside")
        self.assertFalse(quarantine.quarantine(str(outside), "x", [str(self.root / "projects")])["success"])
        self.assertFalse(quarantine.quarantine(str(self.root / "projects"), "x", [str(self.root / "projects")])["success"])
        self.assertFalse(quarantine.purge("../../evil", "DELETE ../../evil")["success"])

    def test_cross_volume_copy_verifies_before_delete(self):
        project = make_project(self.root / "projects")
        with patch.object(quarantine, "_same_volume", return_value=False):
            result = quarantine.quarantine(str(project), "test", [str(self.root / "projects")])
        self.assertTrue(result["success"], result)
        self.assertFalse(project.exists())
        self.assertTrue((self.data / "quarantine" / result["id"] / "manifest.json").exists())

    def test_reset_projects_only_touches_verified(self):
        desktop = self.root / "desktop"
        lectures = desktop / "FlutterProjects"
        verified = make_project(lectures, "verified")
        unverified = make_project(lectures, "unverified", marker=False)
        with patch.object(dev_reset.paths, "lecture_projects_dir", return_value=str(lectures)), \
             patch.object(dev_reset.os.path, "expandvars", return_value=str(desktop)):
            logs: list[str] = []
            dev_reset.reset_projects(logs)
        self.assertFalse(verified.exists())
        self.assertTrue((unverified / "pubspec.yaml").exists())
        self.assertTrue(any("لا يوجد إثبات ملكية" in line for line in logs))

    def test_api_requires_dev_mode(self):
        api = onboarding_app.OnboardingApi({})
        with patch.object(onboarding_app, "dev_mode_enabled", return_value=False):
            self.assertFalse(api.quarantine_list()["success"])
            self.assertFalse(api.quarantine_restore("x")["success"])
            self.assertFalse(api.quarantine_purge("x", "DELETE x")["success"])
            self.assertFalse(api.adopt_project("x")["success"])

    def test_adopt_legacy_project(self):
        project = make_project(self.root / "legacy", "old_app", marker=False)
        result = dev_reset.adopt_project(str(project))
        self.assertTrue(result["success"], result)
        self.assertTrue(managed.is_managed(str(project)))
        marker = managed.read_marker(str(project))
        self.assertEqual(marker["source"], "user_confirmed")
        # No project files were changed.
        self.assertEqual((project / "lib" / "main.dart").read_text(encoding="utf-8"), "void main() {}")

    def test_adopt_refuses_managed_or_non_flutter(self):
        managed_project = make_project(self.root / "projects")
        self.assertFalse(dev_reset.adopt_project(str(managed_project))["success"])
        plain = self.root / "plain"
        plain.mkdir()
        self.assertFalse(dev_reset.adopt_project(str(plain))["success"])
        self.assertFalse(dev_reset.adopt_project(str(self.root / "missing"))["success"])

    def test_adopted_project_can_be_quarantined(self):
        lectures = self.root / "desktop" / "FlutterProjects"
        project = make_project(lectures, "legacy_app", marker=False)
        self.assertTrue(dev_reset.adopt_project(str(project))["success"])
        with patch.object(dev_reset.paths, "lecture_projects_dir", return_value=str(lectures)), \
             patch.object(dev_reset.os.path, "expandvars", return_value=str(lectures.parent)):
            logs: list[str] = []
            dev_reset.reset_projects(logs)
        self.assertFalse(project.exists())
        self.assertEqual(len(quarantine.list_items()), 1)


if __name__ == "__main__":
    unittest.main()
