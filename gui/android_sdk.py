"""Android SDK bootstrap for FlutterWay.

A clean Windows machine has Flutter and Java but no Android SDK. This module
downloads the official command-line tools, verifies their SHA-256, installs the
USB-only package set, accepts the SDK licenses, and persists ANDROID_HOME.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from typing import Callable

try:
    from gui import paths
except ImportError:
    import paths

CMDLINE_TOOLS_VERSION = "11076708"
CMDLINE_TOOLS_URL = f"https://dl.google.com/android/repository/commandlinetools-win-{CMDLINE_TOOLS_VERSION}_latest.zip"
CMDLINE_TOOLS_MIRROR = f"https://mirrors.cloud.tencent.com/AndroidSDK/commandlinetools-win-{CMDLINE_TOOLS_VERSION}_latest.zip"
CMDLINE_TOOLS_SHA256 = "4d6931209eebb1bfb7c7e8b240a6a3cb3ab24479ea294f3539429574b1eec862"

USB_PACKAGES = [
    "platform-tools",
    "platforms;android-36",
    "build-tools;36.0.0",
    "platforms;android-35",
    "build-tools;35.0.0",
]

REQUIRED_PLATFORM = "android-36"
REQUIRED_BUILD_TOOLS = "36.0.0"


def _startupinfo():
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    return info


def sdk_ready(sdk_root: str | None = None) -> bool:
    """True when adb, the required platform, and build-tools are present."""
    sdk_root = sdk_root or paths.android_sdk_root()
    adb = os.path.join(sdk_root, "platform-tools", "adb.exe")
    platform = os.path.join(sdk_root, "platforms", REQUIRED_PLATFORM)
    build_tools = os.path.join(sdk_root, "build-tools", REQUIRED_BUILD_TOOLS)
    return os.path.exists(adb) and os.path.isdir(platform) and os.path.isdir(build_tools)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: str, progress: Callable[[str], None] | None = None) -> None:
    if progress:
        progress(f"جاري تنزيل أدوات Android SDK من {url.split('/')[2]}...")
    request = urllib.request.Request(url, headers={"User-Agent": "FlutterWay/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)
            received += len(chunk)
            if progress and total:
                progress(f"جاري تنزيل أدوات Android SDK... {int(received * 100 / total)}%")


def _download_verified(destination: str, progress: Callable[[str], None] | None = None) -> None:
    last_error = None
    for url in (CMDLINE_TOOLS_URL, CMDLINE_TOOLS_MIRROR):
        try:
            _download(url, destination, progress)
            if _sha256(destination).lower() == CMDLINE_TOOLS_SHA256:
                return
            last_error = f"تحقق SHA-256 فشل للملف من {url}"
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "تعذر تنزيل Android command-line tools")


def _extract_cmdline_tools(archive: str, sdk_root: str) -> None:
    with tempfile.TemporaryDirectory(prefix="fw_cmdline_") as temp_dir:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(temp_dir)
        extracted = os.path.join(temp_dir, "cmdline-tools")
        if not os.path.isdir(extracted):
            raise RuntimeError("حزمة cmdline-tools لا تحتوي المجلد المتوقع")
        target = os.path.join(sdk_root, "cmdline-tools", "latest")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(extracted, target)


def _sdkmanager(sdk_root: str) -> str:
    candidate = os.path.join(sdk_root, "cmdline-tools", "latest", "bin", "sdkmanager.bat")
    if not os.path.exists(candidate):
        raise RuntimeError("sdkmanager.bat غير موجود بعد فك الضغط")
    return candidate


def _run_sdkmanager(sdk_root: str, args: list[str], timeout: int = 900) -> tuple[int, str]:
    manager = _sdkmanager(sdk_root)
    env = os.environ.copy()
    java_home = paths.jdk_home()
    if java_home:
        env["JAVA_HOME"] = java_home
        env["PATH"] = os.path.join(java_home, "bin") + ";" + env.get("PATH", "")
    env["ANDROID_HOME"] = sdk_root
    env["ANDROID_SDK_ROOT"] = sdk_root

    process = subprocess.Popen(
        [manager, f"--sdk_root={sdk_root}", *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        startupinfo=_startupinfo(),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    output, _ = process.communicate("y\n" * 40, timeout=timeout)
    return process.returncode, output or ""


def _persist_env(name: str, value: str) -> bool:
    try:
        import ctypes
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            value_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, value_type, value)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, 0) as key:
            stored, _ = winreg.QueryValueEx(key, name)
        if str(stored) != str(value):
            return False
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
        return True
    except Exception:
        return False


def _persist_path_entry(entry: str) -> bool:
    try:
        import ctypes
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current = ""
            parts = [part.strip() for part in current.split(";") if part.strip()]
            if not any(entry.lower() == part.lower() for part in parts):
                parts.insert(0, entry)
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, 0) as key:
            stored, _ = winreg.QueryValueEx(key, "Path")
        if not any(entry.lower() == part.strip().lower() for part in str(stored).split(";")):
            return False
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
        return True
    except Exception:
        return False


def install_android_sdk(progress: Callable[[str], None] | None = None, persist: bool = True) -> dict:
    """Install the USB-only Android SDK profile if it is not already present."""
    sdk_root = paths.android_sdk_root()
    os.makedirs(sdk_root, exist_ok=True)

    if sdk_ready(sdk_root):
        warnings = []
        if persist:
            os.environ["ANDROID_HOME"] = sdk_root
            os.environ["ANDROID_SDK_ROOT"] = sdk_root
            if not _persist_env("ANDROID_HOME", sdk_root):
                warnings.append("ANDROID_HOME لم يُحفظ")
            if not _persist_env("ANDROID_SDK_ROOT", sdk_root):
                warnings.append("ANDROID_SDK_ROOT لم يُحفظ")
            if not _persist_path_entry(os.path.join(sdk_root, "platform-tools")):
                warnings.append("platform-tools لم تُضف إلى PATH")
        if progress:
            progress("Android SDK جاهز مسبقاً — لا حاجة لإعادة التنزيل")
        return {"success": True, "sdk_root": sdk_root, "warnings": warnings,
                "message": "Android SDK جاهز مسبقاً" + (" (تحذير: تعذر حفظ بعض متغيرات البيئة)" if warnings else "")}

    archive = os.path.join(paths.data_dir(), "cache", f"commandlinetools-{CMDLINE_TOOLS_VERSION}.zip")
    os.makedirs(os.path.dirname(archive), exist_ok=True)

    try:
        if not os.path.exists(archive) or _sha256(archive).lower() != CMDLINE_TOOLS_SHA256:
            _download_verified(archive, progress)
        if progress:
            progress("جاري فك ضغط أدوات Android command-line...")
        _extract_cmdline_tools(archive, sdk_root)
    except Exception as exc:
        return {"success": False, "sdk_root": sdk_root, "error": f"تعذر تجهيز Android SDK: {exc}"}

    try:
        if progress:
            progress("جاري قبول تراخيص Android SDK...")
        _run_sdkmanager(sdk_root, ["--licenses"], timeout=180)
        if progress:
            progress("جاري تثبيت platform-tools وplatforms وbuild-tools...")
        code, output = _run_sdkmanager(sdk_root, USB_PACKAGES, timeout=900)
    except Exception as exc:
        return {"success": False, "sdk_root": sdk_root, "error": f"تعذر تشغيل sdkmanager: {exc}"}

    if not sdk_ready(sdk_root):
        tail = "\n".join(output.strip().splitlines()[-6:])
        return {"success": False, "sdk_root": sdk_root, "error": f"فشل تثبيت حزم Android SDK (كود {code}).\n{tail}"}

    os.environ["ANDROID_HOME"] = sdk_root
    os.environ["ANDROID_SDK_ROOT"] = sdk_root
    warnings = []
    if persist:
        if not _persist_env("ANDROID_HOME", sdk_root):
            warnings.append("ANDROID_HOME لم يُحفظ")
        if not _persist_env("ANDROID_SDK_ROOT", sdk_root):
            warnings.append("ANDROID_SDK_ROOT لم يُحفظ")
        if not _persist_path_entry(os.path.join(sdk_root, "platform-tools")):
            warnings.append("platform-tools لم تُضف إلى PATH")

    message = "تم تثبيت Android SDK وأدوات adb بنجاح"
    if warnings:
        message += " — لكن تعذر حفظ بعض متغيرات البيئة. سنكمل بالمسار المباشر."
    return {"success": True, "sdk_root": sdk_root, "warnings": warnings, "message": message}
