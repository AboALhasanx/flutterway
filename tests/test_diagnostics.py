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
from unittest.mock import patch

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
        self.assertEqual(report["schema"], 2)
        self.assertEqual(report["build"]["version"], diagnostics.__version__)
        self.assertNotIn("gokoq", json.dumps(report, ensure_ascii=False))
        self.assertNotIn("logs", report)
        url = diagnostics.github_issue_url(report)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertTrue(url.startswith(diagnostics.GITHUB_REPO + "/issues/new?"))
        self.assertIn("Build failed", query["title"][0])
        self.assertIn("pressed build", query["body"][0])
        self.assertLess(len(url), 12000, "GitHub issue URL must stay manageable")
        self.assertIn("التنقية آلية", query["body"][0])

    def test_zip_never_contains_raw_log_even_if_requested(self):
        secret = "SYNTHETIC_LOCAL_LOG_CANARY_123"
        diagnostics.log(secret)
        for include_logs in (True, False):
            with self.subTest(include_logs=include_logs):
                report = diagnostics.build_report("boom", include_logs=include_logs)
                path = diagnostics.save_report_zip(report)
                with zipfile.ZipFile(path) as archive:
                    self.assertNotIn("flutterway.log", archive.namelist())
                    for name in archive.namelist():
                        self.assertNotIn(secret.encode(), archive.read(name))
                self.assertNotIn(secret, diagnostics.report_markdown(report))
                self.assertNotIn(secret, diagnostics.github_issue_url(report))

        # Defend the output boundary against legacy report objects, too.
        legacy = {"message": "legacy", "logs": secret, "raw_log": secret}
        with zipfile.ZipFile(diagnostics.save_report_zip(legacy)) as archive:
            for name in archive.namelist():
                self.assertNotIn(secret.encode(), archive.read(name))
        self.assertNotIn(secret, diagnostics.github_issue_url(legacy))

    def test_browser_false_is_not_reported_as_success(self):
        with patch.object(diagnostics.webbrowser, "open", return_value=False):
            result = diagnostics.open_github_issue({"message": "test"})
        self.assertFalse(result["opened"])
        self.assertTrue(result["url"].startswith(diagnostics.GITHUB_REPO))

        with patch.object(diagnostics.webbrowser, "open", return_value=True):
            self.assertTrue(diagnostics.open_github_issue({"message": "test"})["opened"])

    def test_client_error_is_local_jsonl(self):
        diagnostics.capture_client_error({"message": "js boom", "stack": "at x", "phase": "home"})
        path = diagnostics.client_errors_path()
        self.assertTrue(path.exists())
        self.assertIn("js boom", path.read_text(encoding="utf-8"))

    def test_api_open_report_uses_sanitized_payload(self):
        api = onboarding_app.OnboardingApi({})
        original_save = diagnostics.save_report_zip
        original_open = diagnostics.open_github_issue
        diagnostics.save_report_zip = lambda report: self.fail("Opening GitHub must not save a ZIP")
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
        self.assertEqual(result["zip_path"], "")
        self.assertTrue(result["github_url"].startswith(diagnostics.GITHUB_REPO))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(result["github_url"]).query)
        self.assertIn("pressed start", query["body"][0])

    def test_api_preview_lists_what_will_be_shared(self):
        api = onboarding_app.OnboardingApi({})
        preview = api.get_report_preview({"message": "Crash", "phase": "build"})
        self.assertTrue(preview["success"])
        self.assertIn("report.json", preview["manifest"])
        self.assertNotIn("events.jsonl", preview["manifest"])
        self.assertNotIn("flutterway.log", preview["markdown"])
        self.assertTrue(preview["warnings"])

    def test_save_report_honours_events_opt_in(self):
        api = onboarding_app.OnboardingApi({})
        without_events = api.save_error_report({"message": "x", "include_events": False})
        with zipfile.ZipFile(without_events["zip_path"]) as archive:
            self.assertNotIn("events.jsonl", archive.namelist())
        with_events = api.save_error_report({"message": "x", "include_events": True})
        with zipfile.ZipFile(with_events["zip_path"]) as archive:
            self.assertIn("events.jsonl", archive.namelist())


if __name__ == "__main__":
    unittest.main()
