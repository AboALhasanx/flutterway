"""Manual check: install Android SDK and build a real debug APK on a clean host.

Used by the `android-build` CI job. It:
1. installs the pinned Flutter SDK,
2. runs the production Android SDK bootstrap (pinned command-line tools),
3. creates a Flutter project,
4. builds a debug APK and verifies the artefact exists.

Run:
    python tests/verify_android_build.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import android_sdk, toolchain  # noqa: E402


def _ensure_java() -> str | None:
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home and (Path(java_home) / "bin" / "java.exe").exists():
        return java_home
    java = shutil.which("java")
    if java:
        resolved = str(Path(java).resolve().parents[1])
        os.environ["JAVA_HOME"] = resolved
        return resolved
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    data = Path(tempfile.mkdtemp(prefix="fw-ci-data-"))
    os.environ["FLUTTERWAY_DATA_DIR"] = str(data)
    # Force our own SDK root instead of the legacy/preinstalled one on the runner.
    isolated_sdk = data / "android-sdk"
    isolated_sdk.mkdir(parents=True, exist_ok=True)
    os.environ["ANDROID_SDK_ROOT"] = str(isolated_sdk)
    os.environ["ANDROID_HOME"] = str(isolated_sdk)
    java_home = _ensure_java()
    print("JAVA_HOME:", java_home, flush=True)
    if not java_home:
        print("No Java runtime found.")
        return 2

    release = toolchain.resolve_flutter_release("stable")
    if not release:
        print("No Flutter release resolved.")
        return 3
    flutter_root = Path(tempfile.mkdtemp(prefix="fw-ci-flutter-")) / "flutter"
    started = time.time()
    install = toolchain.install_flutter_archive(str(flutter_root), release)
    print("flutter install:", install, flush=True)
    if not install.get("success"):
        return 4
    flutter = flutter_root / "bin" / "flutter.bat"
    os.environ["PATH"] = str(flutter_root / "bin") + os.pathsep + os.environ.get("PATH", "")

    print("installing Android SDK...", flush=True)
    expected_root = str(isolated_sdk.resolve())
    sdk = android_sdk.install_android_sdk(persist=False)
    print("sdk success:", sdk.get("success"), "root:", sdk.get("sdk_root"), flush=True)
    if not sdk.get("success"):
        print("sdk error:", sdk.get("error"), flush=True)
        return 5
    if str(Path(sdk["sdk_root"]).resolve()) != expected_root:
        print("SDK was not installed into the isolated root:", sdk["sdk_root"])
        return 5
    sdk_root = sdk["sdk_root"]
    os.environ["ANDROID_HOME"] = sdk_root
    os.environ["ANDROID_SDK_ROOT"] = sdk_root

    configure = subprocess.run(
        [str(flutter), "config", "--android-sdk", sdk_root],
        capture_output=True, text=True, timeout=120,
    )
    print("flutter config rc:", configure.returncode, configure.stdout[-500:], flush=True)

    project_dir = Path(tempfile.mkdtemp(prefix="fw-ci-project-"))
    create = subprocess.run(
        [str(flutter), "create", "--platforms", "android", "--org", "com.university.flutterway", "demo_app"],
        cwd=str(project_dir), capture_output=True, text=True, timeout=600,
    )
    print("flutter create rc:", create.returncode, flush=True)
    print((create.stdout or "")[-1200:], flush=True)
    print((create.stderr or "")[-800:], flush=True)
    if create.returncode != 0:
        return 6
    app = project_dir / "demo_app"

    build = subprocess.run(
        [str(flutter), "build", "apk", "--debug"],
        cwd=str(app), capture_output=True, text=True, timeout=2400,
    )
    print("flutter build rc:", build.returncode, flush=True)
    print((build.stdout or "")[-2500:], flush=True)
    print((build.stderr or "")[-1500:], flush=True)
    if build.returncode != 0:
        return 7

    apk = app / "build" / "app" / "outputs" / "flutter-apk" / "app-debug.apk"
    if not apk.exists():
        print("APK missing at", apk)
        return 8
    size = apk.stat().st_size
    print("APK:", apk, "bytes:", size)
    if size < 5 * 1024 * 1024:
        print("APK looks too small:", size)
        return 9
    print(f"total seconds: {round(time.time() - started, 1)}")
    print("ANDROID_BUILD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
