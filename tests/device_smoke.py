"""Manual end-to-end device test.

Requires a connected Android device with USB debugging enabled. It creates a
temporary lecture project, builds it with the real pipeline, installs it on the
device, verifies the package, and cleans up.

Run from the repository root:
    python tests/device_smoke.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import companion_service, paths  # noqa: E402
from gui.onboarding_app import OnboardingApi  # noqa: E402


class FakeWindow:
    def __init__(self):
        self.calls: list[str] = []

    def evaluate_js(self, script: str):
        self.calls.append(script)


def _last_build_result(fake: FakeWindow):
    prefix = "finishRealBuild("
    for call in reversed(fake.calls):
        if call.startswith(prefix):
            raw = call[len(prefix):].strip()
            if raw.endswith(");"):
                raw = raw[:-2]
            elif raw.endswith(")"):
                raw = raw[:-1]
            try:
                return json.loads(raw)
            except Exception:
                return None
    return None


def _print_build_logs(fake: FakeWindow) -> None:
    prefix = "appendLiveBuildLog("
    lines = []
    for call in fake.calls:
        if call.startswith(prefix):
            raw = call[len(prefix):].strip()
            if raw.endswith(");"):
                raw = raw[:-2]
            lines.append(raw[:400])
    print("\n--- LAST BUILD LOGS ---")
    for line in lines[-40:]:
        print(line)
    print("--- END BUILD LOGS ---")


def _stop_owned_build(process) -> bool:
    """Stop only the captured Flutter build and its current descendants."""
    try:
        root = psutil.Process(process.pid)
        descendants = root.children(recursive=True)
    except psutil.NoSuchProcess:
        return True
    owned = descendants + [root]
    for child in reversed(owned):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(owned, timeout=10)
    return not alive


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and install a temporary lecture project on a real device.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary project and the build logs for inspection.")
    args = parser.parse_args()

    adb = paths.adb_path()
    devices = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10)
    ready = [line for line in devices.stdout.splitlines() if line.strip().endswith("device")]
    if devices.returncode != 0 or len(ready) != 1:
        print("Exactly one ready Android device is required.")
        return 2

    parent = tempfile.mkdtemp(prefix="fw_device_smoke_")
    original_save = companion_service.save_recent_project
    companion_service.save_recent_project = lambda *args, **kwargs: None
    project_name = "smoke_" + uuid.uuid4().hex[:12]
    app_id = f"com.university.flutterway.{project_name}"
    started = False
    completed = False
    package_was_absent = False
    build_processes = []
    original_popen = subprocess.Popen

    def capture_build(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        command = args[0] if args else kwargs.get("args", [])
        if isinstance(command, (list, tuple)) and "build" in command and "apk" in command:
            build_processes.append(process)
        return process

    try:
        created = companion_service.create_lecture_project(project_name, parent)
        if not created.get("success"):
            print("Project creation failed:", created)
            return 3
        project_path = created["path"]
        actual_id = companion_service.get_application_id(project_path)
        if actual_id != app_id:
            print("Unexpected applicationId:", actual_id)
            return 4

        existing = subprocess.run(
            [adb, "shell", "pm", "list", "packages", app_id],
            capture_output=True, text=True, timeout=10,
        )
        if existing.returncode != 0 or f"package:{app_id}" in existing.stdout.splitlines():
            print("Cannot safely install: package query failed or package already exists.")
            return 4
        package_was_absent = True

        fake = FakeWindow()
        api = OnboardingApi({"window": fake})
        subprocess.Popen = capture_build
        start = api.start_real_gradle_build(project_path=project_path)
        if not start.get("success"):
            print("Build could not start:", start)
            return 4
        started = True

        deadline = time.time() + 900
        result = None
        while time.time() < deadline:
            result = _last_build_result(fake)
            if result:
                break
            time.sleep(2)

        if not result:
            print("Build did not finish within the timeout.")
            for process in build_processes:
                print("Stopped owned build tree:", _stop_owned_build(process))
            print("TEMP PROJECT KEPT for inspection:", parent)
            return 5

        completed = True

        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("success") or not result.get("installed_ok"):
            print("Build/install failed.")
            _print_build_logs(fake)
            if args.keep:
                print("KEPT PROJECT:", project_path)
            return 6

        packages = subprocess.run(
            [adb, "shell", "pm", "list", "packages", app_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if packages.returncode != 0 or f"package:{app_id}" not in packages.stdout.splitlines():
            print("Package was not installed:", packages.stdout)
            return 7

        if not result.get("launched_ok"):
            print("App launch was not verified by the build pipeline.")
            return 8
        activity = subprocess.run(
            [adb, "shell", "dumpsys", "activity", "activities"],
            capture_output=True, text=True, timeout=10,
        )
        if activity.returncode != 0 or not any(
            app_id in line and ("mResumedActivity" in line or "topResumedActivity" in line)
            for line in activity.stdout.splitlines()
        ):
            print("App was installed but is not verified in the foreground.")
            return 8

        print("DEVICE SMOKE PASSED:", app_id)
        return 0
    finally:
        subprocess.Popen = original_popen
        companion_service.save_recent_project = original_save
        if completed and package_was_absent:
            try:
                subprocess.run([adb, "uninstall", app_id], capture_output=True, text=True, timeout=15)
            except Exception:
                pass
        if args.keep or (started and not completed):
            print("TEMP PROJECT KEPT:", parent)
        else:
            shutil.rmtree(parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
