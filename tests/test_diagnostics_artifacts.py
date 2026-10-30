"""ZIP artefacts: unique names, manifest, atomic write, events opt-in."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import diagnostics  # noqa: E402

SECRET = "LOCAL_LOG_SECRET_CANARY_987"


class ArtefactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-zip-")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._clear_logger)
        self.data = Path(self.temp.name)
        self.real_data_dir = diagnostics.paths.data_dir
        diagnostics.paths.data_dir = lambda: str(self.data)
        self._clear_logger()

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

    def test_unique_names_in_same_second(self):
        report = diagnostics.build_report("boom")
        first = Path(diagnostics.save_report_zip(report))
        second = Path(diagnostics.save_report_zip(report))
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())

    def test_manifest_matches_contents(self):
        path = Path(diagnostics.save_report_zip(diagnostics.build_report("boom")))
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for entry in manifest["files"]:
                payload = archive.read(entry["name"])
                self.assertEqual(entry["size"], len(payload))
                self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())

    def test_raw_log_never_present(self):
        diagnostics.log(SECRET)
        for include_events in (False, True):
            path = Path(diagnostics.save_report_zip(diagnostics.build_report("boom", include_events=include_events), include_events=include_events))
            with zipfile.ZipFile(path) as archive:
                self.assertNotIn("flutterway.log", archive.namelist())
                for name in archive.namelist():
                    self.assertNotIn(SECRET.encode(), archive.read(name))

    def test_events_file_only_when_requested(self):
        diagnostics.log_event("build_finished", build_id=7, success=True, returncode=0)
        without = Path(diagnostics.save_report_zip(diagnostics.build_report("x"), include_events=False))
        with zipfile.ZipFile(without) as archive:
            self.assertNotIn("events.jsonl", archive.namelist())
        with_events = Path(diagnostics.save_report_zip(diagnostics.build_report("x", include_events=True), include_events=True))
        with zipfile.ZipFile(with_events) as archive:
            self.assertIn("events.jsonl", archive.namelist())
            lines = archive.read("events.jsonl").decode("utf-8").strip().splitlines()
            self.assertLessEqual(len(lines), diagnostics.MAX_EVENTS)

    def test_no_partial_zip_on_failure(self):
        real_replace = diagnostics.os.replace

        def boom(src, dst):
            raise OSError("disk full")

        with patch.object(diagnostics.os, "replace", side_effect=boom):
            with self.assertRaises(OSError):
                diagnostics.save_report_zip(diagnostics.build_report("x"))
        self.assertEqual(list(diagnostics.reports_dir().glob("*.part")), [])
        self.assertEqual(list(diagnostics.reports_dir().glob("*.zip")), [])
        self.assertIs(real_replace, __import__("os").replace)

    def test_oversized_report_is_rejected_without_leftovers(self):
        report = diagnostics.build_report("x", description="A" * 100)
        with patch.object(diagnostics, "MAX_ZIP_BYTES", 10):
            with self.assertRaises(ValueError):
                diagnostics.save_report_zip(report)
        self.assertEqual(list(diagnostics.reports_dir().glob("*.zip")), [])
        self.assertEqual(list(diagnostics.reports_dir().glob("*.part")), [])


if __name__ == "__main__":
    unittest.main()
