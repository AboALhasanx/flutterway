"""Diagnostics, sanitization, GitHub URL, and API tests."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import diagnostics  # noqa: E402
from gui import onboarding_app  # noqa: E402


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._clear_logger)
        self.data = Path(self.temp.name)
        self.real_data_dir = diagnostics.paths.data_dir
        diagnostics.paths.data_dir = lambda: str(self.data)
        self._clear_logger()
        diagnostics._last_error = ""

    def _clear_logger(self):
        logger = logging.getLogger("flutterway")
        for handler in list(logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
            logger.removeHandler(handler)
        diagnostics._logger = None
        diagnostics._log_path = None

    def tearDown(self):
        diagnostics.paths.data_dir = self.real_data_dir
        self._clear_logger()

    def test_sanitizes_user_paths_and_tokens(self):
        text = r"C:\Users\gokoq\Desktop\proj ghp_abcdefghijklmnopqrstuvwxyz123456"
        clean = diagnostics._sanitize_text(text)
        self.assertNotIn("gokoq", clean)
        self.assertNotIn("ghp_", clean)
        self.assertIn("<home>", clean)

    def test_report_and_github_url(self):
        report = diagnostics.build_report(
            message="Build failed",
            stack="Traceback ...",
            phase="build",
            description="pressed build",
            include_logs=False,
            extra={"path": r"C:\Users\gokoq\proj"},
        )
        self.assertEqual(report["version"], "1.0.0")
        self.assertNotIn("gokoq", json.dumps(report, ensure_ascii=False))
        url = diagnostics.github_issue_url(report)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertTrue(url.startswith(diagnostics.GITHUB_REPO + "/issues/new?"))
        self.assertIn("Build failed", query["title"][0])
        self.assertIn("pressed build", query["body"][0])
        self.assertLess(len(url), 12000, "GitHub issue URL must stay manageable")

    def test_zip_contains_report_and_log(self):
        diagnostics.log("hello from test")
        report = diagnostics.build_report("boom", include_logs=True)
        path = diagnostics.save_report_zip(report)
        self.assertTrue(Path(path).exists())
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        self.assertIn("report.json", names)
        self.assertIn("report.md", names)
        self.assertIn("flutterway.log", names)

    def test_client_error_is_local_jsonl(self):
        diagnostics.capture_client_error({"message": "js boom", "stack": "at x", "phase": "home"})
        path = diagnostics.logs_dir() / "client-errors.jsonl"
        self.assertTrue(path.exists())
        self.assertIn("js boom", path.read_text(encoding="utf-8"))

    def test_api_open_report_uses_sanitized_payload(self):
        api = onboarding_app.OnboardingApi({})
        original_save = diagnostics.save_report_zip
        original_open = diagnostics.open_github_issue
        diagnostics.save_report_zip = lambda report: str(self.data / "report.zip")
        diagnostics.open_github_issue = lambda report: True
        try:
            result = api.open_error_report({
                "message": "Crash",
                "description": "pressed start",
                "phase": "setup",
                "include_logs": False,
            })
        finally:
            diagnostics.save_report_zip = original_save
            diagnostics.open_github_issue = original_open
        self.assertTrue(result["success"])
        self.assertTrue(result["opened"])
        self.assertTrue(result["github_url"].startswith(diagnostics.GITHUB_REPO))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(result["github_url"]).query)
        self.assertIn("pressed start", query["body"][0])


if __name__ == "__main__":
    unittest.main()
