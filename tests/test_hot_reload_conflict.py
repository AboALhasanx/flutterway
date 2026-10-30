"""Hot Reload must never overwrite an edit made outside FlutterWay."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.hot_reload import HotReloadSession  # noqa: E402

ORIGINAL = "void main() {\n  // original\n}\n"


class HotReloadConflictTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fw-hr-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "lib").mkdir(parents=True)
        self.main = self.project / "lib" / "main.dart"
        self.main.write_text(ORIGINAL, encoding="utf-8")
        self.session = HotReloadSession()
        self.session.project_path = str(self.project)

    def test_external_edit_is_not_overwritten(self):
        self.session.read_main()
        self.main.write_text("void main() { /* VS Code edit */ }\n", encoding="utf-8")
        before = self.main.read_bytes()
        result = self.session.save("void main() { /* FlutterWay */ }\n")
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "external_change")
        self.assertEqual(self.main.read_bytes(), before)

    def test_normal_save_works_and_updates_hash(self):
        self.session.read_main()
        result = self.session.save("void main() { /* new */ }\n")
        self.assertTrue(result["success"])
        self.assertIn("new", self.main.read_text(encoding="utf-8"))
        second = self.session.save("void main() { /* newer */ }\n")
        self.assertTrue(second["success"])

    def test_save_without_read_still_writes(self):
        self.assertTrue(self.session.save("void main() {}\n")["success"])
        self.assertIn("void main", self.main.read_text(encoding="utf-8"))

    def test_crlf_and_bom_are_preserved(self):
        self.main.write_bytes("\ufeffvoid main() {\r\n  // keep\r\n}\r\n".encode("utf-8"))
        self.session.read_main()
        self.assertTrue(self.session.save("void main() {\n  // changed\n}\n")["success"])
        raw = self.main.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", raw)
        self.assertIn(b"changed", raw)

    def test_backups_rotate_to_three(self):
        for index in range(5):
            self.session.read_main()
            self.session.save(f"void main() {{ /* v{index} */ }}\n")
        baks = list((self.project / "lib").glob("main.dart.bak*"))
        self.assertTrue(1 <= len(baks) <= 3, [p.name for p in baks])

    def test_oversized_content_rejected(self):
        result = self.session.save("x" * (2 * 1024 * 1024 + 1))
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "too_large")

    def test_force_new_saves_sidecar_without_touching_original(self):
        self.session.read_main()
        before = self.main.read_bytes()
        result = self.session.save("void main() { /* mine */ }\n", force_new=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["code"], "saved_copy")
        self.assertTrue((self.project / "lib" / "main.flutterway.dart").exists())
        self.assertEqual(self.main.read_bytes(), before)

    def test_failed_replace_leaves_original_intact(self):
        self.session.read_main()
        before = self.main.read_bytes()
        with patch("gui.hot_reload.os.replace", side_effect=OSError("locked")):
            result = self.session.save("void main() { /* nope */ }\n")
        self.assertFalse(result["success"])
        self.assertEqual(self.main.read_bytes(), before)
        self.assertEqual(list((self.project / "lib").glob("*.tmp-*")), [])


if __name__ == "__main__":
    unittest.main()
