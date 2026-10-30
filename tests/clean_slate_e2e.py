"""Full clean-slate journey: setup -> first build -> hot reload.

Requires an empty FlutterWay environment and a connected Android device.
Run:
    python tests/clean_slate_e2e.py
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "clean_slate2"
CDP_PORT = 9222
PROJECT = Path.home() / "Desktop" / "my_first_app"
EXE = ROOT / "dist" / "FlutterWayNative" / "FlutterWayNative.exe"
WATCHDOG = Path.home() / "scripts" / "adb-autoconnect.ps1"


def now():
    return datetime.now().strftime("%H:%M:%S")


def wait_port(port, timeout=35):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def adb_path():
    candidate = Path.home() / "AppData/Local/FlutterWay/android-sdk/platform-tools/adb.exe"
    return candidate


def adb_devices():
    adb = adb_path()
    if not adb.exists():
        return []
    result = subprocess.run([str(adb), "devices"], capture_output=True, text=True, timeout=15)
    devices = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def start_watchdog():
    if not WATCHDOG.exists():
        return False
    adb_dir = str(adb_path().parent)
    env = os.environ.copy()
    env["PATH"] = adb_dir + ";" + env.get("PATH", "")
    subprocess.Popen(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WATCHDOG)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return True


def png_diff(before, after):
    try:
        a = Image.open(io.BytesIO(before)).convert("RGB")
        b = Image.open(io.BytesIO(after)).convert("RGB")
        return ImageChops.difference(a, b).getbbox() is not None
    except Exception:
        return before != after


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)
    if wait_port(CDP_PORT, timeout=1):
        print("Port 9222 is busy; close the app first.")
        return 2
    if not EXE.exists():
        print("Packaged app not found:", EXE)
        return 2
    if not shutil_which_clean():
        print("Environment is not clean: Flutter/SDK still present.")
        return 2

    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={CDP_PORT}"
    app = subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env)
    report = {"started": datetime.now().isoformat(), "screens": []}
    timeline = (OUT / "timeline.jsonl").open("w", encoding="utf-8")
    start_net = psutil.net_io_counters()
    start_disk = psutil.disk_usage("C:\\").free
    peak_cpu = peak_tree = 0.0

    def sample(page, app_proc, phase, extra=None):
        nonlocal peak_cpu, peak_tree
        cpu = psutil.cpu_percent(interval=None)
        tree = 0.0
        if app_proc and app_proc.is_running():
            try:
                for proc in [app_proc] + app_proc.children(recursive=True):
                    try:
                        tree += proc.memory_info().rss / 1024 / 1024
                    except Exception:
                        pass
            except Exception:
                pass
        peak_cpu = max(peak_cpu, cpu)
        peak_tree = max(peak_tree, tree)
        row = {
            "time": now(),
            "phase": phase,
            "cpu": round(cpu, 1),
            "tree_mb": round(tree, 1),
            "disk_free_gb": round(psutil.disk_usage("C:\\").free / 1024**3, 2),
            "net_mb": round((psutil.net_io_counters().bytes_recv - start_net.bytes_recv) / 1024**2, 1),
        }
        if extra:
            row.update(extra)
        timeline.write(json.dumps(row, ensure_ascii=False) + "\n")
        timeline.flush()
        return row

    try:
        if not wait_port(CDP_PORT, timeout=40):
            print("CDP did not open.")
            return 3
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            page = browser.contexts[0].pages[0]
            page.set_default_timeout(30000)
            page.wait_for_function("window.pywebview && window.pywebview.api")
            page.wait_for_timeout(1000)
            app_proc = None
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"] == "FlutterWayNative.exe":
                    app_proc = psutil.Process(proc.info["pid"])
                    app_proc.cpu_percent(None)
                    break

            # ---------------- Setup ----------------
            page.evaluate("switchMainView('wizard'); showStep(1);")
            page.wait_for_timeout(400)
            page.click("#btn-check-laptop")
            try:
                page.wait_for_selector("#diag-result-box", state="visible", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "01_laptop_check.png"))
            page.click("#btn-start-setup")
            setup_start = time.time()
            last_key = None
            shots = set()
            setup_error = ""
            while time.time() - setup_start < 1800:
                data = page.evaluate("""() => ({
                    step: document.querySelector('.step-view.active')?.id,
                    pct: document.getElementById('progress-pct')?.innerText,
                    text: document.getElementById('progress-text')?.innerText,
                    detail: document.getElementById('progress-detail')?.innerText,
                    wait: document.getElementById('progress-wait')?.innerText,
                    err: getComputedStyle(document.getElementById('setup-error-box')).display !== 'none',
                    errText: document.getElementById('setup-error-text')?.innerText,
                    errDetail: document.getElementById('setup-error-details')?.innerText
                })""")
                sample(page, app_proc, "setup", data)
                key = (data.get("pct"), data.get("text"), data.get("step"), data.get("err"))
                if key != last_key:
                    print(json.dumps({"t": round(time.time() - setup_start, 1), **data}, ensure_ascii=False))
                    last_key = key
                pct = str(data.get("pct") or "")
                for threshold in ("10%", "25%", "50%", "75%", "90%", "100%"):
                    if pct == threshold and threshold not in shots:
                        shots.add(threshold)
                        try:
                            page.screenshot(path=str(OUT / f"02_setup_{threshold.replace('%', '')}.png"))
                        except Exception:
                            pass
                if data.get("err"):
                    setup_error = data.get("errText") or "setup failed"
                    try:
                        page.screenshot(path=str(OUT / "02_setup_error.png"))
                    except Exception:
                        pass
                    break
                if data.get("step") == "step-3":
                    break
                page.wait_for_timeout(2000)
            report["setup_seconds"] = round(time.time() - setup_start, 1)
            report["setup_pct"] = page.evaluate("document.getElementById('progress-pct')?.innerText")
            report["setup_error"] = setup_error
            if setup_error:
                raise RuntimeError("Setup failed: " + setup_error)

            # ---------------- Device ----------------
            page.wait_for_timeout(1500)
            devices = adb_devices()
            if not devices:
                print("No device yet; starting ADB watchdog.")
                start_watchdog()
                deadline = time.time() + 45
                while time.time() < deadline and not adb_devices():
                    page.wait_for_timeout(1000)
                devices = adb_devices()
            report["devices"] = devices
            if not devices:
                raise RuntimeError("No device detected after setup")
            page.evaluate("checkDeviceNow()")
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / "03_device_ready.png"))

            # ---------------- First build ----------------
            page.evaluate("runRealGradleBuild()")
            build_start = time.time()
            build_ok = False
            build_error = ""
            last_key = None
            while time.time() - build_start < 1800:
                data = page.evaluate("""() => ({
                    timer: document.getElementById('build-elapsed-timer')?.innerText,
                    task: document.getElementById('build-task-active')?.innerText,
                    bpct: document.getElementById('build-progress-pct')?.innerText,
                    bench: getComputedStyle(document.getElementById('benchmark-card')).display,
                    s3: document.getElementById('bstep-3')?.className,
                    head: document.getElementById('benchmark-head-text')?.innerText,
                    speed: document.getElementById('stat-speed')?.innerText,
                    size: document.getElementById('stat-size')?.innerText
                })""")
                sample(page, app_proc, "build", data)
                key = (data.get("task"), data.get("bench"), data.get("s3"))
                if key != last_key:
                    print(json.dumps({"t": round(time.time() - build_start, 1), **data}, ensure_ascii=False))
                    last_key = key
                if data.get("bench") == "block":
                    build_ok = True
                    break
                if "error" in (data.get("s3") or "") or data.get("task") == "Build Failed":
                    build_error = data.get("task") or "build failed"
                    break
                page.wait_for_timeout(2000)
            report["build_seconds"] = round(time.time() - build_start, 1)
            report["build_ok"] = build_ok
            report["build_error"] = build_error
            report["build_size"] = page.evaluate("document.getElementById('stat-size')?.innerText")
            page.screenshot(path=str(OUT / "04_build_end.png"))
            if not build_ok:
                raise RuntimeError("Build failed: " + build_error)

            # ---------------- Hot reload ----------------
            page.evaluate("async () => { switchMainView('companion'); await refreshAppInit(); selectActiveProject('my_first_app', 'C:\\\\Users\\\\gokoq\\\\Desktop\\\\my_first_app'); switchCompanionTab('home'); }")
            page.wait_for_timeout(700)
            before = subprocess.run([str(adb_path()), "exec-out", "screencap", "-p"], capture_output=True, timeout=20).stdout
            hr_start = time.time()
            page.click("#home-primary")
            ready = False
            status = {}
            deadline = time.time() + 180
            while time.time() < deadline:
                status = page.evaluate("async () => await window.pywebview.api.hot_reload_status()")
                if status.get("running") and status.get("ready"):
                    ready = True
                    break
                page.wait_for_timeout(800)
            report["hot_reload_start_seconds"] = round(time.time() - hr_start, 1)
            report["used_prebuilt"] = status.get("used_prebuilt")
            if not ready:
                raise RuntimeError("Hot reload session did not connect")
            page.wait_for_timeout(2200)
            seed = page.input_value("#hr-quick-text")
            marker = "CLEAN2_" + datetime.now().strftime("%H%M%S")
            page.fill("#hr-quick-text", marker)
            reload_ms = None
            deadline = time.time() + 45
            while time.time() < deadline:
                st = page.evaluate("async () => await window.pywebview.api.hot_reload_status()")
                if st.get("last_reload_ms"):
                    reload_ms = st.get("last_reload_ms")
                    break
                page.wait_for_timeout(700)
            page.wait_for_timeout(2500)
            after = subprocess.run([str(adb_path()), "exec-out", "screencap", "-p"], capture_output=True, timeout=20).stdout
            (OUT / "05_hr_before.png").write_bytes(before)
            (OUT / "06_hr_after.png").write_bytes(after)
            page.screenshot(path=str(OUT / "07_hot_reload.png"))
            report["reload_ms"] = reload_ms
            report["device_changed"] = png_diff(before, after)
            report["editor_has_marker"] = page.evaluate("(m) => document.getElementById('hr-editor').value.includes(m)", marker)
            page.click("#btn-hr-stop")
            page.wait_for_timeout(1200)
            report["stopped"] = not page.evaluate("async () => (await window.pywebview.api.hot_reload_status()).running")
            browser.close()
    except Exception as exc:
        report["fatal"] = str(exc)
        print("FATAL", exc)
    finally:
        try:
            app.terminate()
            app.wait(timeout=5)
        except Exception:
            try:
                app.kill()
            except Exception:
                pass
        timeline.close()
        report["finished"] = datetime.now().isoformat()
        report["peak_cpu"] = round(peak_cpu, 1)
        report["peak_tree_mb"] = round(peak_tree, 1)
        report["net_mb"] = round((psutil.net_io_counters().bytes_recv - start_net.bytes_recv) / 1024**2, 1)
        report["disk_used_gb"] = round((start_disk - psutil.disk_usage("C:\\").free) / 1024**3, 2)
        (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report.get("fatal") else 1


def shutil_which_clean():
    return not Path("C:/flutter").exists() and not Path("C:/Android").exists()


if __name__ == "__main__":
    raise SystemExit(main())
