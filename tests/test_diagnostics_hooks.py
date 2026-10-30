"""Exception hooks: chaining, recursion guard, and crash artefacts."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import diagnostics  # noqa: E402


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-hooks-")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._cleanup)
        self.data = Path(self.temp.name)
        self.real_data_dir = diagnostics.paths.data_dir
        diagnostics.paths.data_dir = lambda: str(self.data)
        self._close_logger()

    def _close_logger(self):
        logger = logging.getLogger("flutterway")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        diagnostics._logger = None
        diagnostics._log_path = None

    def _cleanup(self):
        diagnostics.uninstall_exception_hooks()
        self._close_logger()
        diagnostics.paths.data_dir = self.real_data_dir

    def _install(self):
        diagnostics.install_exception_hooks()
        captured = []
        diagnostics._previous_excepthook = lambda *args: captured.append(args)
        return captured

    def test_exception_writes_crash_and_chains(self):
        captured = self._install()
        sys.excepthook(ValueError, ValueError("boom"), None)
        crash = diagnostics.reports_dir() / "last-crash.json"
        self.assertTrue(crash.exists())
        data = json.loads(crash.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 2)
        self.assertIn("ValueError", data["message"])
        self.assertEqual(len(captured), 1)

    def test_keyboard_interrupt_is_not_swallowed_or_logged(self):
        captured = self._install()
        with patch.object(diagnostics, "_write_crash") as write:
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        write.assert_not_called()
        self.assertEqual(captured, [])

    def test_write_failure_does_not_raise(self):
        captured = self._install()
        with patch.object(diagnostics, "_write_crash", side_effect=OSError("disk")):
            sys.excepthook(RuntimeError, RuntimeError("x"), None)  # must not raise
        self.assertEqual(len(captured), 1)

    def test_recursion_guard(self):
        captured = self._install()
        diagnostics._hook_running = True
        with patch.object(diagnostics, "_write_crash") as write:
            sys.excepthook(RuntimeError, RuntimeError("x"), None)
        write.assert_not_called()
        diagnostics._hook_running = False

    def test_thread_hook(self):
        captured = self._install()

        class Args:
            exc_type = RuntimeError
            exc_value = RuntimeError("thread")
            exc_traceback = None

        diagnostics.threading.excepthook(Args)
        self.assertTrue((diagnostics.reports_dir() / "last-crash.json").exists())
        self.assertEqual(len(captured), 1)


if __name__ == "__main__":
    unittest.main()
