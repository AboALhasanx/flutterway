"""End-to-end test for the in-app Hot Reload Studio.

Launches the real desktop app, selects a project that already has a stripped
signed debug APK, starts a Flutter session, types in the built-in editor, and
verifies that the phone UI changed after the automatic hot reload.

Run:
    python tests/hot_reload_journey.py
"""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "hot_reload_journey"
CDP_PORT = 9222
PROJECT = Path(r"C:\Users\gokoq\Desktop\FlutterProjects\student_custom_142510")
PROJECT_NAME = PROJECT.name

sys.path.insert(0, str(ROOT))
from gui import paths  # noqa: E402


def wait_port(port, timeout=30, open_=True):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                state = True
        except OSError:
            state = False
        if state == open_:
            return True
        time.sleep(0.35)
    return False


def launch_app():
    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={CDP_PORT}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.Popen(
        [sys.executable, "-m", "gui.onboarding_app"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def adb_text(adb):
    try:
        subprocess.run([adb, "shell", "uiautomator", "dump", "/sdcard/fw_hr_dump.xml"], capture_output=True, timeout=20)
        result = subprocess.run([adb, "exec-out", "cat", "/sdcard/fw_hr_dump.xml"], capture_output=True, timeout=10)
        return result.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def adb_png(adb):
    try:
        result = subprocess.run([adb, "exec-out", "screencap", "-p"], capture_output=True, timeout=20)
        return result.stdout if result.returncode == 0 else b""
    except Exception:
        return b""


def images_changed(before: bytes, after: bytes) -> bool:
    if not before or not after:
        return False
    try:
        first = Image.open(io.BytesIO(before)).convert("RGB")
        second = Image.open(io.BytesIO(after)).convert("RGB")
        if first.size != second.size:
            return True
        width, height = first.size
        # Ignore the status bar and the gesture bar; compare the app content.
        box = (0, 100, width, max(101, height - 60))
        diff = ImageChops.difference(first.crop(box), second.crop(box))
        return diff.getbbox() is not None
    except Exception:
        return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)
    if not (PROJECT / "lib" / "main.dart").exists():
        print("Project not found:", PROJECT)
        return 2
    if not (PROJECT / "build" / "app" / "outputs" / "flutter-apk" / "app-debug.signed.apk").exists():
        print("Missing signed debug APK in", PROJECT)
        return 3
    if wait_port(CDP_PORT, timeout=1):
        print("Port 9222 is already in use.")
        return 4

    app = launch_app()
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "project": str(PROJECT),
        "screens": [],
        "findings": [],
        "console_errors": [],
    }
    adb = paths.adb_path()

    def finding(severity, area, note):
        report["findings"].append({"severity": severity, "area": area, "note": note})

    try:
        if not wait_port(CDP_PORT, timeout=35):
            print("No CDP port.")
            return 5
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            page = browser.contexts[0].pages[0]
            page.set_default_timeout(30000)
            page.wait_for_function("window.pywebview && window.pywebview.api")
            page.wait_for_timeout(1000)
            page.on("pageerror", lambda exc: report["console_errors"].append(f"pageerror: {exc}"))
            page.on("console", lambda msg: report["console_errors"].append(f"console: {msg.text}") if msg.type == "error" else None)

            def shot(name, note):
                path = OUT / f"{name}.png"
                page.screenshot(path=str(path))
                report["screens"].append({"name": name, "note": note, "path": str(path)})

            # Select the test project and open the Hot Reload tab.
            page.evaluate("switchMainView('companion');")
            page.evaluate(
                "([name, path]) => { selectActiveProject(name, path); switchCompanionTab('hotreload'); }",
                [PROJECT_NAME, str(PROJECT)],
            )
            page.wait_for_timeout(800)
            shot("01_hotreload_tab", "تبويب Hot Reload قبل البدء")

            # Start the session.
            page.click("#btn-hr-start")
            connected = False
            deadline = time.time() + 90
            while time.time() < deadline:
                status = page.evaluate("async () => await window.pywebview.api.hot_reload_status()")
                if status.get("running") and status.get("ready"):
                    connected = True
                    break
                page.wait_for_timeout(1000)
            report["connected"] = connected
            if not connected:
                finding("high", "Hot Reload start", "الجلسة لم تتصل خلال 90 ثانية.")
                shot("02_start_failed", "فشل بدء الجلسة")
                return 6
            shot("02_connected", "الجلسة متصلة وجاهزة")
            report["start_status"] = page.evaluate("async () => await window.pywebview.api.hot_reload_status()")
            before_png = adb_png(adb)
            if before_png:
                before_path = OUT / "03_device_before.png"
                before_path.write_bytes(before_png)
                report["screens"].append({"name": "03_device_before", "note": "شاشة الهاتف قبل التعديل", "path": str(before_path)})

            # Ensure the editor was populated by the app, then expose advanced tools.
            page.evaluate("document.getElementById('hr-advanced').open = true")
            original = page.input_value("#hr-editor")
            if "const Text(" not in original:
                finding("high", "Editor", "المحرر لم يحمّل lib/main.dart.")
                return 7
            quick_seed = ""
            quick_enabled = False
            if page.locator("#hr-quick-text").count():
                quick_seed = page.input_value("#hr-quick-text")
                quick_enabled = page.locator("#hr-quick-text").is_enabled()
            report["quick_text_seed"] = quick_seed
            if not quick_seed:
                finding("medium", "Hot Reload", "حقل التغيير السريع لم يُملأ من ملف المشروع.")

            marker = "HOT_RELOAD_UI_" + datetime.now().strftime("%H%M%S")
            method = "editor"
            if quick_seed and quick_enabled:
                method = "quick"
                page.fill("#hr-quick-text", marker)
            else:
                page.evaluate("""(marker) => {
                    const ed = document.getElementById('hr-editor');
                    const updated = ed.value.replace(/(const Text\\(\\s*\\n\\s*')[^']+(')/, `$1${marker}$2`);
                    ed.value = updated;
                    ed.dispatchEvent(new Event('input', { bubbles: true }));
                }""", marker)
            report["edit_method"] = method
            reload_ms = None
            reload_log = ""
            deadline = time.time() + 40
            while time.time() < deadline:
                status = page.evaluate("async () => await window.pywebview.api.hot_reload_status()")
                if status.get("last_reload_ms"):
                    reload_ms = status["last_reload_ms"]
                    reload_log = "\n".join(status.get("logs", [])[-8:])
                    break
                page.wait_for_timeout(700)
            report["reload_ms"] = reload_ms
            report["reload_log"] = reload_log
            if not reload_ms:
                finding("high", "Hot Reload", "لم يظهر أي Reload بعد تعديل المحرر.")
            report["editor_has_marker"] = page.evaluate(
                "(marker) => document.getElementById('hr-editor').value.includes(marker)", marker
            )
            if method == "quick" and not report["editor_has_marker"]:
                finding("high", "Hot Reload", "التعديل السريع لم يكتب القيمة في lib/main.dart.")
            page.wait_for_timeout(2200)
            shot("03_after_reload", "بعد التعديل والـ Hot Reload التلقائي")

            time.sleep(2)
            dump = adb_text(adb)
            text_found = marker in dump
            report["device_text_found"] = text_found
            if text_found:
                report["device_marker"] = marker
            else:
                report["device_text_note"] = "UIAutomator لا يعرض نصوص Flutter؛ سيتم الاعتماد على فرق لقطة الشاشة."
            png = adb_png(adb)
            device_changed = images_changed(before_png, png)
            report["device_changed"] = device_changed
            if not device_changed:
                finding("medium", "Device verification", "لقطة شاشة الهاتف لم تتغير بعد الـ Hot Reload.")
            if png:
                image_path = OUT / "04_device_after_reload.png"
                image_path.write_bytes(png)
                report["screens"].append({"name": "04_device_after_reload", "note": "شاشة الهاتف بعد التحديث", "path": str(image_path)})

            # Restore the original code and wait for the automatic reload.
            if method == "quick":
                page.fill("#hr-quick-text", quick_seed)
            else:
                page.evaluate("(original) => { const ed = document.getElementById('hr-editor'); ed.value = original; ed.dispatchEvent(new Event('input', {bubbles:true})); }", original)
            page.wait_for_timeout(2800)

            # Stop the session.
            page.click("#btn-hr-stop")
            page.wait_for_timeout(800)
            final = page.evaluate("async () => await window.pywebview.api.hot_reload_status()")
            report["running_after_stop"] = final.get("running")
            if final.get("running"):
                finding("high", "Stop", "الجلسة بقيت تعمل بعد زر الإيقاف.")
            shot("05_after_stop", "بعد إيقاف الجلسة")

            report["console_errors"] = report["console_errors"]
            if report["console_errors"]:
                finding("high", "Runtime", f"أخطاء JavaScript: {len(report['console_errors'])}")
            if not reload_ms:
                finding("high", "Hot Reload", "التحديث التلقائي لم يعمل.")
            if reload_ms and reload_ms > 10000:
                finding("low", "Hot Reload", f"زمن Reload مرتفع: {reload_ms}ms")

            (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            lines = [
                "# Hot Reload Studio Journey",
                "",
                f"- Project: `{PROJECT_NAME}`",
                f"- Connected: {connected}",
                f"- Last reload: {reload_ms} ms",
                f"- Device text found: {text_found}",
                f"- Device screen changed: {device_changed}",
                f"- Running after stop: {final.get('running')}",
                f"- Findings: {len(report['findings'])}",
                "",
                "## Findings",
            ]
            lines += [f"- **{f['severity'].upper()}** [{f['area']}] {f['note']}" for f in report["findings"]] or ["- No automatic findings."]
            lines += ["", "## Screens"] + [f"- `{s['path']}` — {s['note']}" for s in report["screens"]]
            (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
            print(json.dumps({
                "project": PROJECT_NAME,
                "connected": connected,
                "reload_ms": reload_ms,
                "device_text_found": text_found,
                "device_changed": device_changed,
                "running_after_stop": final.get("running"),
                "findings": report["findings"],
                "console_errors": report["console_errors"],
                "report": str(OUT / "report.md"),
            }, ensure_ascii=False, indent=2))
            browser.close()
            return 0 if connected and reload_ms and not final.get("running") else 8
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
