"""Manual end-to-end device test.

Requires a connected Android device with USB debugging enabled. It creates a
temporary lecture project, builds it with the real pipeline, installs it on the
device, verifies the package, and cleans up.

Run from the repository root:
    python tests/device_smoke.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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


def main() -> int:
    adb = paths.adb_path()
    devices = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10)
    ready = [line for line in devices.stdout.splitlines() if line.strip().endswith("device")]
    if not ready:
        print("No ready Android device found.")
        return 2

    parent = tempfile.mkdtemp(prefix="fw_device_smoke_")
    original_save = companion_service.save_recent_project
    companion_service.save_recent_project = lambda *args, **kwargs: None
    app_id = "com.university.flutterway.device_smoke"
    try:
        created = companion_service.create_lecture_project("device_smoke", parent)
        if not created.get("success"):
            print("Project creation failed:", created)
            return 3
        project_path = created["path"]
        actual_id = companion_service.get_application_id(project_path)
        if actual_id != app_id:
            print("Unexpected applicationId:", actual_id)
            return 4

        fake = FakeWindow()
        api = OnboardingApi({"window": fake})
        api.start_real_gradle_build(project_path=project_path)

        deadline = time.time() + 900
        result = None
        while time.time() < deadline:
            result = _last_build_result(fake)
            if result:
                break
            time.sleep(2)

        if not result:
            print("Build did not finish within the timeout.")
            return 5

        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("success") or not result.get("installed_ok"):
            print("Build/install failed.")
            return 6

        packages = subprocess.run(
            [adb, "shell", "pm", "list", "packages", app_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if app_id not in packages.stdout:
            print("Package was not installed:", packages.stdout)
            return 7

        print("DEVICE SMOKE PASSED:", app_id)
        return 0
    finally:
        companion_service.save_recent_project = original_save
        try:
            subprocess.run([adb, "uninstall", app_id], capture_output=True, text=True, timeout=15)
        except Exception:
            pass
        shutil.rmtree(parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
