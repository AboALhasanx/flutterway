"""Guards against duplicate build/setup jobs (backend side)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import onboarding_app as app  # noqa: E402


class FakeThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.api = app.OnboardingApi({})
        self.real_thread = app.threading.Thread
        app.threading.Thread = lambda *a, **k: FakeThread(*a, **k)

    def tearDown(self):
        app.threading.Thread = self.real_thread

    def test_build_cannot_start_twice(self):
        first = self.api.start_real_gradle_build()
        second = self.api.start_real_gradle_build()
        self.assertTrue(first.get("success"))
        self.assertFalse(second.get("success"))
        self.assertIn("شغال", second.get("error", ""))
        self.assertTrue(self.api.state["build_running"])
        self.api.state["build_running"] = False

    def test_setup_cannot_start_twice(self):
        first = self.api.start_onboarding("usb")
        second = self.api.start_onboarding("usb")
        self.assertTrue(first.get("success"))
        self.assertFalse(second.get("success"))
        self.assertIn("شغال", second.get("error", ""))
        self.assertTrue(self.api.state["setup_running"])
        self.api.state["setup_running"] = False


if __name__ == "__main__":
    unittest.main()
