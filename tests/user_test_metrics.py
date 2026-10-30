"""Compute FlutterWay user-testing metrics from the CSV templates.

Usage:
    python tests/user_test_metrics.py
    python tests/user_test_metrics.py --sessions path.csv --sus path.csv --out report.md

The script is dependency-free and tolerant of blank template cells.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS = ROOT / "docs" / "user_testing" / "sessions_template.csv"
DEFAULT_SUS = ROOT / "docs" / "user_testing" / "sus_template.csv"
TASKS = ["T1", "T2", "T3", "T4", "T5"]


def number(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fmt(value, digits=1, suffix=""):
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def session_summary(rows: list[dict]) -> dict:
    summary = {}
    for task in TASKS:
        task_rows = [r for r in rows if (r.get("task") or "").strip().upper() == task]
        success_values = [number(r.get("success")) for r in task_rows]
        success_values = [v for v in success_values if v is not None]
        times = [number(r.get("time_sec")) for r in task_rows]
        times = [v for v in times if v is not None and v > 0]
        interventions = [number(r.get("interventions")) for r in task_rows]
        interventions = [v for v in interventions if v is not None]
        seqs = [number(r.get("seq")) for r in task_rows]
        seqs = [v for v in seqs if v is not None and 1 <= v <= 7]
        summary[task] = {
            "n": len(task_rows),
            "success_n": len(success_values),
            "success": (sum(success_values) / len(success_values)) if success_values else None,
            "median_time": statistics.median(times) if times else None,
            "avg_interventions": (sum(interventions) / len(interventions)) if interventions else None,
            "avg_seq": (sum(seqs) / len(seqs)) if seqs else None,
        }
    return summary


def sus_scores(rows: list[dict]) -> list[float]:
    scores = []
    for row in rows:
        values = [number(row.get(f"q{i}")) for i in range(1, 11)]
        if any(v is None or not 1 <= v <= 5 for v in values):
            continue
        total = 0.0
        for index, value in enumerate(values, start=1):
            total += (value - 1) if index % 2 == 1 else (5 - value)
        scores.append(total * 2.5)
    return scores


def build_report(sessions_path: Path, sus_path: Path) -> str:
    sessions = read_rows(sessions_path)
    sus_rows = read_rows(sus_path)
    tasks = session_summary(sessions)
    scores = sus_scores(sus_rows)

    lines = [
        "# ملخص اختبار المستخدم — FlutterWay",
        "",
        f"- ملف المهام: `{sessions_path.name}`",
        f"- ملف SUS: `{sus_path.name}`",
        "",
    ]

    if not any(task["success_n"] or task["median_time"] for task in tasks.values()) and not scores:
        lines.append("> لا توجد بيانات كافية بعد. املأ ملفات CSV ثم أعد التشغيل.")
        return "\n".join(lines) + "\n"

    lines += [
        "## نتائج المهام",
        "",
        "| المهمة | الصفوف | نجاح | وسيط الزمن | متوسط التدخلات | متوسط SEQ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for task in TASKS:
        data = tasks[task]
        success = f"{data['success'] * 100:.0f}%" if data["success"] is not None else "—"
        lines.append(
            f"| {task} | {data['n']} | {success} | {fmt(data['median_time'], 1, ' ث')} "
            f"| {fmt(data['avg_interventions'], 1)} | {fmt(data['avg_seq'], 1)} |"
        )

    t1 = tasks["T1"]
    lines += [
        "",
        "## المهمة الحرجة T1",
        "",
        f"- نسبة النجاح: **{fmt((t1['success'] or 0) * 100, 0, '%') if t1['success'] is not None else '—'}**",
        f"- وسيط الزمن: **{fmt(t1['median_time'], 1, ' ث')}**",
        f"- متوسط التدخلات: **{fmt(t1['avg_interventions'], 1)}**",
        "",
        "## SUS",
        "",
    ]
    if scores:
        lines += [
            f"- عدد الاستبيانات المكتملة: **{len(scores)}**",
            f"- متوسط SUS: **{statistics.mean(scores):.1f}**",
            f"- المدى: {min(scores):.1f} – {max(scores):.1f}",
        ]
    else:
        lines.append("- لا توجد استبيانات SUS مكتملة.")

    lines += [
        "",
        "## القبول",
        "",
        "| المعيار | النتيجة | الهدف |",
        "|---|---:|---:|",
        f"| نجاح T1 | {fmt((t1['success'] or 0) * 100, 0, '%') if t1['success'] is not None else '—'} | ≥ 80% |",
        f"| وسيط T1 | {fmt(t1['median_time'], 1, ' ث')} | ≤ 1200 ث |",
        f"| SUS | {f'{statistics.mean(scores):.1f}' if scores else '—'} | ≥ 68 |",
        f"| SEQ | {fmt(t1['avg_seq'], 1)} | ≥ 5.5 |",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FlutterWay user-testing metrics")
    parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--sus", type=Path, default=DEFAULT_SUS)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = build_report(args.sessions, args.sus)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
