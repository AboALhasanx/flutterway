"""Unit tests for the FlutterWay user-testing metrics helper."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from user_test_metrics import session_summary, sus_scores  # noqa: E402


class MetricsTests(unittest.TestCase):
    def test_task_summary(self):
        rows = [
            {"task": "T1", "success": "1", "time_sec": "600", "interventions": "0", "seq": "7"},
            {"task": "T1", "success": "1", "time_sec": "900", "interventions": "1", "seq": "6"},
            {"task": "T1", "success": "1", "time_sec": "1100", "interventions": "0", "seq": "6"},
            {"task": "T1", "success": "1", "time_sec": "700", "interventions": "2", "seq": "5"},
            {"task": "T1", "success": "0", "time_sec": "1500", "interventions": "3", "seq": "3"},
        ]
        summary = session_summary(rows)["T1"]
        self.assertEqual(summary["success_n"], 5)
        self.assertAlmostEqual(summary["success"], 0.8)
        self.assertAlmostEqual(summary["median_time"], 900)
        self.assertAlmostEqual(summary["avg_interventions"], 1.2)
        self.assertAlmostEqual(summary["avg_seq"], 5.4)

    def test_sus_scoring(self):
        best = {"q1": 5, "q2": 1, "q3": 5, "q4": 1, "q5": 5, "q6": 1, "q7": 5, "q8": 1, "q9": 5, "q10": 1}
        neutral = {f"q{i}": 3 for i in range(1, 11)}
        worst = {"q1": 1, "q2": 5, "q3": 1, "q4": 5, "q5": 1, "q6": 5, "q7": 1, "q8": 5, "q9": 1, "q10": 5}
        self.assertEqual(sus_scores([best]), [100.0])
        self.assertEqual(sus_scores([neutral]), [50.0])
        self.assertEqual(sus_scores([worst]), [0.0])

    def test_incomplete_sus_is_skipped(self):
        self.assertEqual(sus_scores([{"q1": 4, "q2": 2}]), [])

    def test_blank_rows_are_ignored(self):
        summary = session_summary([{"task": "T1", "success": "", "time_sec": "", "seq": ""}])["T1"]
        self.assertIsNone(summary["success"])
        self.assertIsNone(summary["median_time"])


if __name__ == "__main__":
    unittest.main()
