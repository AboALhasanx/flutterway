"""Both lecture-project creation paths must agree on their Android identity."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui import companion_service as service  # noqa: E402


def write_project(path: Path, app_id: str) -> None:
    (path / "android" / "app").mkdir(parents=True)
    (path / "lib").mkdir()
    (path / "pubspec.yaml").write_text("name: test\n", encoding="utf-8")
    (path / "lib" / "main.dart").write_text("void main() {}", encoding="utf-8")
    (path / "android" / "app" / "build.gradle.kts").write_text(
        f'android {{\n namespace = "com.example.template"\n defaultConfig {{ applicationId = "{app_id}" }}\n}}\n',
        encoding="utf-8",
    )


class LectureProjectIdentityTests(unittest.TestCase):
    def test_template_creation_changes_application_id_only(self):
        with tempfile.TemporaryDirectory(prefix="fw-identity-") as temp:
            root = Path(temp)
            template = root / "template"
            write_project(template, "com.example.template")
            with patch.object(service.paths, "starter_template_dir", return_value=str(template)), \
                 patch.object(service, "save_recent_project"):
                result = service.create_lecture_project("demo", str(root / "projects"))
            self.assertTrue(result["success"])
            self.assertEqual(service.get_application_id(result["path"]), "com.university.flutterway.demo")
            gradle = Path(result["path"]) / "android" / "app" / "build.gradle.kts"
            self.assertIn('namespace = "com.example.template"', gradle.read_text(encoding="utf-8"))

    def test_flutter_create_uses_same_organization(self):
        with tempfile.TemporaryDirectory(prefix="fw-identity-") as temp:
            def fake_create(command, cwd):
                org = command[command.index("--org") + 1]
                name = command[-1]
                write_project(Path(cwd) / name, f"{org}.{name}")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(service.paths, "starter_template_dir", return_value=None), \
                 patch.object(service.paths, "flutter_bat", return_value="flutter.bat"), \
                 patch.object(service, "run_silent", side_effect=fake_create), \
                 patch.object(service, "save_recent_project"):
                result = service.create_lecture_project("demo", temp)
            self.assertTrue(result["success"])
            self.assertEqual(service.get_application_id(result["path"]), "com.university.flutterway.demo")

    def test_existing_project_identity_is_untouched(self):
        with tempfile.TemporaryDirectory(prefix="fw-identity-") as temp:
            write_project(Path(temp) / "demo", "com.university.student.demo")
            with patch.object(service, "save_recent_project"):
                result = service.create_lecture_project("demo", temp)
            self.assertEqual(service.get_application_id(result["path"]), "com.university.student.demo")


if __name__ == "__main__":
    unittest.main()
