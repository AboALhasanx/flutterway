"""Tests for the isolated app-data directory override."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui import paths
from tests.support import assert_no_canaries, canary_values, fake_webview_bridge, temp_data_dir


class DataDirectoryTests(unittest.TestCase):
    def test_override_is_created_and_used(self):
        with temp_data_dir() as expected:
            actual = Path(paths.data_dir())
            self.assertEqual(actual, expected)
            self.assertTrue(actual.is_dir())
            marker = actual / "test-marker.txt"
            marker.write_text("isolated", encoding="utf-8")
            self.assertEqual(marker.read_text(encoding="utf-8"), "isolated")
            self.assertEqual(actual.parent, Path(os.environ["FLUTTERWAY_DATA_DIR"]).parent)

    def test_override_is_restored_after_context(self):
        previous = os.environ.get("FLUTTERWAY_DATA_DIR")
        with temp_data_dir():
            self.assertIn("FLUTTERWAY_DATA_DIR", os.environ)
        self.assertEqual(os.environ.get("FLUTTERWAY_DATA_DIR"), previous)

    def test_default_path_is_unchanged_without_override(self):
        previous_override = os.environ.get("FLUTTERWAY_DATA_DIR")
        previous_local_appdata = os.environ.get("LOCALAPPDATA")
        with tempfile.TemporaryDirectory(prefix="flutterway-default-path-test-") as base:
            os.environ.pop("FLUTTERWAY_DATA_DIR", None)
            os.environ["LOCALAPPDATA"] = base
            try:
                self.assertEqual(paths.data_dir(), os.path.join(base, paths.APP_NAME))
            finally:
                if previous_override is None:
                    os.environ.pop("FLUTTERWAY_DATA_DIR", None)
                else:
                    os.environ["FLUTTERWAY_DATA_DIR"] = previous_override
                if previous_local_appdata is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_local_appdata

    def test_canary_assertion_detects_synthetic_values(self):
        values = canary_values()
        self.assertEqual(set(values), {"user", "project", "token", "email", "password", "path"})
        assert_no_canaries("A report without any synthetic personal data")
        with self.assertRaises(AssertionError):
            assert_no_canaries("report includes " + values["project"])

    def test_fake_webview_bridge_has_api_namespace(self):
        bridge = fake_webview_bridge(check=lambda: {"success": True})
        self.assertTrue(bridge.api.check()["success"])


if __name__ == "__main__":
    unittest.main()
