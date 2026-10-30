"""Student-level test of the custom lecture-project build feature.

Launches the real desktop app, creates a new project through the Projects tab,
presses "تشغيل وبناء على الهاتف", and watches the actual build console and the
Android device until the app is installed and launched.

This is intentionally interactive-level: it uses the same UI a student uses,
not the backend directly. It creates a real project under Desktop\\FlutterProjects.

Run:
    python tests/custom_project_journey.py
    python tests/custom_project_journey.py --keep-build
    python tests/custom_project_journey.py --cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "custom_project_journey"
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

sys.path.insert(0, str(ROOT))
from gui import companion_service, paths  # noqa: E402


def wait_for_port(port: int, timeout: float = 30.0, should_be_open: bool = True) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                open_now = True
        except OSError:
            open_now = False
        if open_now == should_be_open:
            return True
        time.sleep(0.35)
    return False


def launch_app():
    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={CDP_PORT}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "gui.onboarding_app"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-build", action="store_true", help="Keep the project's build/ directory.")
    parser.add_argument("--cleanup", action="store_true", help="Remove the created project and uninstall the app.")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if wait_for_port(CDP_PORT, timeout=1):
        print("Port 9222 is already in use; close the other app first.")
        return 2

    project_name = "student_custom_" + datetime.now().strftime("%H%M%S")
    app = launch_app()
    project_path = None
    app_id = None
    console_errors: list[str] = []
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "project_name": project_name,
        "screens": [],
        "samples": [],
        "findings": [],
        "console_errors": [],
    }

    def finding(severity, area, note):
        report["findings"].append({"severity": severity, "area": area, "note": note})

    try:
        if not wait_for_port(CDP_PORT, timeout=35):
            print("The app did not expose WebView2 CDP.")
            return 3

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            page.set_default_timeout(30000)
            page.wait_for_function("window.pywebview && window.pywebview.api")
            page.wait_for_timeout(1200)
            page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
            page.on("console", lambda msg: console_errors.append(f"console: {msg.text}") if msg.type == "error" else None)

            def shot(name, note):
                path = OUT / f"{name}.png"
                page.screenshot(path=str(path))
                report["screens"].append({"name": name, "note": note, "path": str(path)})

            # 1. Companion -> Projects tab, like a returning student.
            page.evaluate("switchMainView('companion'); switchCompanionTab('projects');")
            page.wait_for_timeout(1000)
            shot("01_projects_before", "تبويب مشاريع المحاضرات قبل الإنشاء")

            # 2. Create a custom project through the actual input/button.
            page.fill("#input-lecture-name", project_name)
            page.click("#btn-create-lecture-proj")
            created = False
            deadline = time.time() + 60
            while time.time() < deadline:
                state = page.evaluate("""() => ({
                    active: document.getElementById('active-proj-name')?.innerText || '',
                    path: document.getElementById('active-proj-path')?.innerText || '',
                    recent: document.getElementById('recent-projects-list')?.innerText || ''
                })""")
                if project_name in state["active"] or project_name in state["recent"]:
                    created = True
                    project_path = state["path"] if state["path"] and os.path.isdir(state["path"]) else None
                    break
                page.wait_for_timeout(500)
            if not created:
                finding("high", "Create project", "الطالب كتب اسم المشروع وضغط إنشاء، لكن المشروع لم يظهر في القائمة/المشروع النشط.")
                shot("02_create_failed", "فشل إنشاء المشروع")
                return 4

            page.wait_for_timeout(300)
            shot("02_project_created", "تم إنشاء المشروع وتحديده كنشط")
            if not project_path:
                path_text = page.locator("#active-proj-path").inner_text()
                project_path = path_text if os.path.isdir(path_text) else None
            if not project_path:
                finding("high", "Create project", "المشروع أُنشئ لكن مساره النشط غير صالح.")
                return 5
            app_id = companion_service.get_application_id(project_path)
            report["project_path"] = project_path
            report["application_id"] = app_id
            if not app_id.startswith("com.university.flutterway."):
                finding("high", "Application ID", f"معرّف الحزمة غير متوقع: {app_id}")
            if not os.path.exists(os.path.join(project_path, "pubspec.yaml")):
                finding("high", "Create project", "المشروع لا يحتوي pubspec.yaml.")

            # 3. Click the student-facing "run on phone" button.
            page.click("#btn-run-proj-phone")
            page.wait_for_timeout(1000)
            build_visible = page.evaluate("getComputedStyle(document.getElementById('build-console')).display !== 'none'")
            if not build_visible:
                finding("high", "Build screen", "شاشة البناء لم تظهر بعد الضغط على تشغيل وبناء.")
            shot("03_build_start", "بداية شاشة البناء بعد اختيار المشروع")

            # 4. Monitor the real build screen every 2 seconds.
            start = time.time()
            last_lines = 0
            last_task = ""
            success = False
            failed = False
            deadline = time.time() + 900
            mid_shot = False
            while time.time() < deadline:
                sample = page.evaluate("""() => {
                    const console = document.getElementById('build-console');
                    const bench = document.getElementById('benchmark-card');
                    const terminal = document.getElementById('build-terminal-lines');
                    return {
                        console: console ? getComputedStyle(console).display : 'missing',
                        benchmark: bench ? getComputedStyle(bench).display : 'missing',
                        timer: document.getElementById('build-elapsed-timer')?.innerText || '',
                        task: document.getElementById('build-task-active')?.innerText || '',
                        lines: terminal ? terminal.textContent.slice(-2000) : '',
                        lineCount: terminal ? terminal.querySelectorAll('div').length : 0,
                        step1: document.getElementById('bstep-1')?.className || '',
                        step2: document.getElementById('bstep-2')?.className || '',
                        step3: document.getElementById('bstep-3')?.className || '',
                        head: document.getElementById('benchmark-head-text')?.innerText || '',
                        speed: document.getElementById('stat-speed')?.innerText || '',
                        size: document.getElementById('stat-size')?.innerText || ''
                    };
                }""")
                elapsed = round(time.time() - start, 1)
                if sample["lineCount"] != last_lines or sample["task"] != last_task:
                    print(f"[{elapsed:6.1f}s] task={sample['task']!r} lines={sample['lineCount']} timer={sample['timer']}")
                    last_lines = sample["lineCount"]
                    last_task = sample["task"]
                report["samples"].append({"elapsed": elapsed, **sample})
                if not mid_shot and elapsed > 12 and sample["lineCount"] > 0:
                    shot("04_build_mid", "منتصف البناء: شاشة مبسطة والسجل مطوي")
                    mid_shot = True
                if sample["benchmark"] == "block" and "يعمل" in sample["head"]:
                    success = True
                    break
                if "error" in sample["step3"]:
                    failed = True
                    break
                page.wait_for_timeout(2000)

            elapsed = round(time.time() - start, 1)
            end = page.evaluate("""() => ({
                console: getComputedStyle(document.getElementById('build-console')).display,
                benchmark: getComputedStyle(document.getElementById('benchmark-card')).display,
                head: document.getElementById('benchmark-head-text')?.innerText || '',
                speed: document.getElementById('stat-speed')?.innerText || '',
                size: document.getElementById('stat-size')?.innerText || '',
                task: document.getElementById('build-task-active')?.innerText || '',
                lines: document.getElementById('build-terminal-lines')?.textContent || '',
                step3: document.getElementById('bstep-3')?.className || ''
            })""")
            report["result"] = {"elapsed": elapsed, **end}
            shot("05_build_end", "نهاية البناء: بطاقة النجاح أو الخطأ")
            build_done_at = next((s["elapsed"] for s in report["samples"] if "Build Succeeded" in s.get("task", "")), None)
            benchmark_at = next((s["elapsed"] for s in report["samples"] if s.get("benchmark") == "block"), None)
            install_logged = any("[ADB]" in s.get("lines", "") or "تثبيت" in s.get("lines", "") for s in report["samples"])
            report["install_gap"] = round((benchmark_at - build_done_at), 1) if build_done_at and benchmark_at else None
            if report["install_gap"] and report["install_gap"] > 20 and not install_logged:
                finding(
                    "medium",
                    "Build screen",
                    f"الشاشة تبقى على Build Succeeded حوالي {report['install_gap']} ثانية أثناء التثبيت، بدون مؤشر تثبيت/تقدم واضح.",
                )
            if not install_logged:
                finding("medium", "Build screen", "سجل البناء لا يوضح مرحلة التجريد/التثبيت على الهاتف.")
            if "لم يفتح" in end.get("head", ""):
                finding("medium", "Device", "بطاقة النجاح تقول إن التطبيق لم يفتح بعد رغم نجاح التثبيت.")
            if not success:
                failed = True
                finding("high", "Build", f"البناء لم ينجح خلال {elapsed} ثانية.")

            # 5. Verify what the student sees: APK size, device name, logs.
            if success:
                if "MB" not in end["size"]:
                    finding("medium", "Benchmark", "بطاقة النجاح لا تعرض حجم APK.")
                if not end["speed"]:
                    finding("medium", "Benchmark", "بطاقة النجاح لا تعرض زمن البناء.")
                if "تم تجريد APK" not in end["lines"]:
                    finding("medium", "Build log", "سجل البناء لا يبيّن خطوة تجريد/تصغير APK.")
                # Actual built APK size for comparison.
                apk_files = []
                apk_dir = os.path.join(project_path, "build", "app", "outputs", "flutter-apk")
                if os.path.isdir(apk_dir):
                    for name in os.listdir(apk_dir):
                        if name.endswith(".apk"):
                            path = os.path.join(apk_dir, name)
                            apk_files.append({"name": name, "mb": round(os.path.getsize(path) / 1024 / 1024, 1)})
                report["apk_files"] = apk_files

            # 6. Verify package + capture the tablet screen.
            adb = paths.adb_path()
            package_out = subprocess.run(
                [adb, "shell", "pm", "list", "packages", app_id],
                capture_output=True, text=True, timeout=10,
            )
            installed = app_id in package_out.stdout
            report["installed"] = installed
            if not installed:
                finding("high", "Device", f"الحزمة {app_id} غير مثبتة على الهاتف بعد البناء.")
            else:
                time.sleep(2)
                screen_path = OUT / "06_device_screen.png"
                try:
                    png = subprocess.run([adb, "exec-out", "screencap", "-p"], capture_output=True, timeout=15)
                    if png.returncode == 0 and len(png.stdout) > 1000:
                        screen_path.write_bytes(png.stdout)
                        report["screens"].append({"name": "06_device_screen", "note": "شاشة التابلت بعد التشغيل", "path": str(screen_path)})
                except Exception as exc:
                    finding("low", "Device screenshot", f"تعذر التقاط شاشة الهاتف: {exc}")

            report["console_errors"] = console_errors
            if console_errors:
                finding("high", "Runtime", f"أخطاء JavaScript أثناء التجربة: {len(console_errors)}")

            (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            lines = [
                "# Custom Project Journey Report",
                "",
                f"- Project: `{project_name}`",
                f"- Path: `{project_path}`",
                f"- applicationId: `{app_id}`",
                f"- Build time: {elapsed}s",
                f"- Installed: {installed}",
                f"- Findings: {len(report['findings'])}",
                "",
                "## Findings",
            ]
            if report["findings"]:
                lines += [f"- **{f['severity'].upper()}** [{f['area']}] {f['note']}" for f in report["findings"]]
            else:
                lines.append("- No automatic findings.")
            lines += ["", "## Screens"]
            lines += [f"- `{s['path']}` — {s['note']}" for s in report["screens"]]
            (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")

            print(json.dumps({
                "project": project_name,
                "path": project_path,
                "app_id": app_id,
                "success": success,
                "failed": failed,
                "elapsed": elapsed,
                "benchmark_size": end.get("size"),
                "benchmark_speed": end.get("speed"),
                "installed": installed,
                "findings": report["findings"],
                "console_errors": console_errors,
                "report": str(OUT / "report.md"),
            }, ensure_ascii=False, indent=2))

            browser.close()

            # Cleanup policy: keep source + app by default, remove the huge build dir.
            if not args.keep_build and project_path:
                build_dir = os.path.join(project_path, "build")
                shutil.rmtree(build_dir, ignore_errors=True)
            if args.cleanup and project_path:
                subprocess.run([adb, "uninstall", app_id], capture_output=True, timeout=15)
                shutil.rmtree(project_path, ignore_errors=True)
                try:
                    recent = paths.recent_projects_file()
                    if os.path.exists(recent):
                        with open(recent, "r", encoding="utf-8") as handle:
                            items = json.load(handle)
                        items = [item for item in items if item.get("path") != project_path]
                        with open(recent, "w", encoding="utf-8") as handle:
                            json.dump(items, handle, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            return 0 if success else 6
    finally:
        try:
            app.terminate()
            app.wait(timeout=6)
        except Exception:
            try:
                app.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
