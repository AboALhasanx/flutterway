from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import onboarding_app  # noqa: E402


class FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, source):
        self.calls.append(source)


class OnboardingJsBridgeTests(unittest.TestCase):
    def test_js_call_json_encodes_windows_paths_quotes_and_line_separators(self):
        message = "C:\\flutter\\bin\\java.exe: 'setup failed'\n\u2028\u2029"
        source = onboarding_app._js_call("updateBuildTicker", 12, message)

        self.assertTrue(source.startswith("updateBuildTicker(12, "))
        self.assertTrue(source.endswith(");"))
        encoded_message = source[len("updateBuildTicker(12, "):-len(");")]
        self.assertEqual(json.loads(encoded_message), message)
        self.assertNotIn("\u2028", source)
        self.assertNotIn("\u2029", source)

    def test_progress_update_uses_json_encoded_message(self):
        api = onboarding_app.OnboardingApi({"window": None})
        window = FakeWindow()
        message = "Path: C:\\Android\\sdk\\bin, 'check' failed"

        api._update_ui(window, 42, message, 2)

        self.assertEqual(window.calls, [
            onboarding_app._js_call("updateProgress", 42, message, 2)
        ])
        self.assertEqual(api.state["progress_percent"], 42)


if __name__ == "__main__":
    unittest.main()
