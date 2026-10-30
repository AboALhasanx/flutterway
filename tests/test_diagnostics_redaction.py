"""Canary tests: no synthetic personal data may survive redaction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import diagnostics  # noqa: E402
from tests.support import CANARY_EMAIL, CANARY_PASSWORD, CANARY_PATH, CANARY_PROJECT, CANARY_TOKEN, CANARY_USER  # noqa: E402


class RedactionTests(unittest.TestCase):
    def test_windows_home_with_space_and_arabic(self):
        cases = [
            CANARY_PATH,
            r"C:\Users\Jane Doe\Desktop\private\main.dart",
            r"C:\Users\مستخدم عربي\Desktop\مشروع\lib\main.dart",
        ]
        for case in cases:
            with self.subTest(case=case):
                clean = diagnostics.redact(case).text
                self.assertNotIn("Jane Doe", clean)
                self.assertNotIn("Doe", clean)
                self.assertNotIn("مستخدم عربي", clean)
                self.assertIn("<home>", clean)

    def test_project_path_outside_home(self):
        clean = diagnostics.redact(CANARY_PROJECT + r"\lib\main.dart").text
        self.assertNotIn("SecretClient", clean)
        self.assertIn("<path>", clean)

    def test_tokens_and_assignments(self):
        samples = [
            CANARY_TOKEN,
            "github_pat_" + "B" * 30,
            "sk-" + "c" * 32,
            "xoxb-1234567890-abcdefghij",
            "AIza" + "D" * 35,
            "AKIA" + "E" * 16,
            CANARY_PASSWORD,
            "Authorization: Bearer abc.def.ghi",
            "api_key=my-secret-value",
        ]
        for sample in samples:
            with self.subTest(sample=sample[:24]):
                result = diagnostics.redact(sample)
                self.assertNotEqual(sample, result.text)
                self.assertNotIn("SuperSecret123", result.text)
                self.assertNotIn("abc.def.ghi", result.text)
                self.assertNotIn("my-secret-value", result.text)
                self.assertGreaterEqual(result.total(), 1)

    def test_email_and_connection_string(self):
        result = diagnostics.redact(
            f"contact {CANARY_EMAIL} via postgres://user:pass@db.local:5432/app"
        )
        self.assertNotIn(CANARY_EMAIL, result.text)
        self.assertNotIn("user:pass", result.text)
        self.assertIn("<email>", result.text)

    def test_idempotent(self):
        text = f"{CANARY_PATH} {CANARY_PROJECT} {CANARY_EMAIL} {CANARY_TOKEN} {CANARY_PASSWORD}"
        once = diagnostics.redact(text).text
        twice = diagnostics.redact(once).text
        self.assertEqual(once, twice)
        self.assertEqual(diagnostics.redact(twice).text, twice)

    def test_false_positives_survive(self):
        normal = (
            "The password manager opened. Token bucket rate limit is 10/s. "
            "C:\\flutter\\bin\\flutter.bat reported BUILD SUCCESSFUL in 32s."
        )
        self.assertEqual(diagnostics.redact(normal).text, normal)

    def test_report_body_and_markdown_are_clean(self):
        report = diagnostics.build_report(
            message="Crash at " + CANARY_PATH,
            stack="Traceback " + CANARY_PROJECT,
            description="mail " + CANARY_EMAIL,
            extra={"client_error": {"message": CANARY_TOKEN, "stack": CANARY_PASSWORD}},
            include_logs=True,
            include_events=True,
        )
        blob = diagnostics.report_markdown(report)
        import json
        payload = json.dumps(report, ensure_ascii=False)
        for canary in (CANARY_USER, CANARY_PROJECT, CANARY_TOKEN, CANARY_EMAIL, CANARY_PASSWORD, CANARY_PATH):
            self.assertNotIn(canary, blob)
            self.assertNotIn(canary, payload)
        self.assertIn("التنقية آلية", blob)

    def test_unknown_extra_fields_are_dropped(self):
        report = diagnostics.build_report(
            "x", extra={"secret_field": CANARY_TOKEN, "url": "https://example.com/a"}
        )
        self.assertNotIn("secret_field", report["extra"])
        self.assertIn("url", report["extra"])


if __name__ == "__main__":
    unittest.main()
