from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import onboarding_app, paths  # noqa: E402


class SetupCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-checkpoint-")
        self.addCleanup(self.temp.cleanup)
        self.original_data_dir = paths.data_dir
        paths.data_dir = lambda: self.temp.name
        with mock.patch("gui.onboarding_app.diagnostics.configure_logging"):
            self.api = onboarding_app.OnboardingApi({"window": None})

    def tearDown(self):
        paths.data_dir = self.original_data_dir

    def test_checkpoint_is_atomic_minimal_and_readable_for_retry(self):
        self.api._write_setup_checkpoint("flutter", 70, "running")
        saved = json.loads(Path(self.api._setup_checkpoint_path()).read_text(encoding="utf-8"))
        self.assertEqual(saved["stage"], "flutter")
        self.assertEqual(saved["percent"], 70)
        self.assertEqual(saved["status"], "running")
        self.assertNotIn(".tmp", [p.name for p in Path(self.temp.name, "cache").iterdir()])
        self.assertEqual(self.api._read_setup_checkpoint(), saved)

    def test_stop_request_is_cooperative_and_does_not_claim_completion(self):
        self.api.state["setup_running"] = True
        result = self.api.stop_onboarding()
        self.assertTrue(result["success"], result)
        self.assertTrue(self.api._setup_stop_event.is_set())
        self.assertFalse(self.api.state["is_complete"])
        self.api.state["setup_running"] = False
        self.assertFalse(self.api.stop_onboarding()["success"])

    def test_stop_when_idle_does_not_mutate_state(self):
        result = self.api.stop_onboarding()
        self.assertFalse(result["success"])
        self.assertFalse(self.api._setup_stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
