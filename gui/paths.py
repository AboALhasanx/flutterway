"""Central path discovery for FlutterWay.

The app must work on a clean Windows machine, not only on the developer's
host. Every path that used to be hardcoded (C:\\flutter, C:\\Android, C:\\g,
d:\\flutterway, ...) should come from this module.

Resolution order is always:
1. Explicit environment override (for tests/portable installs).
2. The legacy location used by the original prototype, if it exists.
3. A per-user location under %LOCALAPPDATA%\\FlutterWay.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys

APP_NAME = "FlutterWay"


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"')


def _first_existing(candidates) -> str | None:
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def resource_root() -> str:
    """Directory that contains bundled resources (works in source and PyInstaller)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def resource_path(*parts: str) -> str:
    return os.path.join(resource_root(), *parts)


def data_dir() -> str:
    """Per-user writable directory for SDKs, caches, and backups."""
    base = _clean(os.environ.get("LOCALAPPDATA")) or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def flutter_root() -> str:
    override = _clean(os.environ.get("FLUTTERWAY_FLUTTER_ROOT")) or _clean(os.environ.get("FLUTTER_ROOT"))
    if override and os.path.isdir(override):
        return os.path.abspath(override)

    candidates = [
        r"C:\flutter",
        os.path.join(data_dir(), "flutter"),
        os.path.expanduser(r"~\flutter"),
        os.path.expandvars(r"%LOCALAPPDATA%\flutter"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(os.path.join(candidate, "bin", "flutter.bat")):
            return os.path.abspath(candidate)

    detected = shutil.which("flutter.bat") or shutil.which("flutter")
    if detected:
        # <root>\bin\flutter.bat -> <root>
        return os.path.dirname(os.path.dirname(os.path.abspath(detected)))

    # Default install target for a clean machine.
    return candidates[1]


def flutter_bat() -> str:
    candidate = os.path.join(flutter_root(), "bin", "flutter.bat")
    if os.path.exists(candidate):
        return candidate
    return shutil.which("flutter.bat") or shutil.which("flutter") or candidate


def flutter_version(root: str | None = None) -> str | None:
    """Read the installed Flutter version without invoking the slow CLI."""
    root = root or flutter_root()
    version_file = os.path.join(root, "bin", "cache", "flutter.version.json")
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("frameworkVersion") or data.get("flutterVersion")
    except Exception:
        pass

    plain_version = os.path.join(root, "version")
    try:
        with open(plain_version, "r", encoding="utf-8") as handle:
            return handle.read().strip() or None
    except Exception:
        return None


def android_sdk_root() -> str:
    override = _clean(os.environ.get("ANDROID_SDK_ROOT")) or _clean(os.environ.get("ANDROID_HOME"))
    if override and os.path.isdir(override):
        return os.path.abspath(override)

    candidates = [
        r"C:\Android",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk"),
        os.path.join(data_dir(), "android-sdk"),
    ]
    return _first_existing(candidates) or candidates[2]


def adb_path() -> str:
    sdk = android_sdk_root()
    candidates = [
        os.path.join(sdk, "platform-tools", "adb.exe"),
        r"C:\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
    ]
    found = _first_existing(candidates)
    return found or shutil.which("adb") or "adb"


def jdk_home() -> str | None:
    override = _clean(os.environ.get("JAVA_HOME"))
    if override and os.path.exists(os.path.join(override, "bin", "java.exe")):
        return os.path.abspath(override)

    patterns = [
        r"C:\Program Files\Eclipse Adoptium\jdk-*",
        r"C:\Program Files\Java\jdk-*",
        r"C:\Program Files\Microsoft\jdk-*",
        os.path.join(data_dir(), "jdk-*"),
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))

    # Newest version first; names include the version and sort reasonably.
    for candidate in sorted(candidates, reverse=True):
        if os.path.exists(os.path.join(candidate, "bin", "java.exe")):
            return os.path.abspath(candidate)
    return None


def gradle_user_home() -> str:
    override = _clean(os.environ.get("GRADLE_USER_HOME"))
    if override:
        return override

    legacy = r"C:\g"
    if os.path.isdir(legacy):
        return legacy

    path = os.path.join(data_dir(), "gradle")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def starter_template_dir() -> str | None:
    return _first_existing([
        resource_path("assets", "starter_template"),
        r"C:\flutter_test_app",
    ])


def default_project_path() -> str:
    return os.path.expandvars(r"%USERPROFILE%\Desktop\my_first_app")


def lecture_projects_dir() -> str:
    return os.path.expandvars(r"%USERPROFILE%\Desktop\FlutterProjects")


def driver_inf_path() -> str:
    return resource_path("assets", "drivers", "google_usb", "usb_driver", "android_winusb.inf")


def icon_path() -> str:
    return resource_path("assets", "icon.ico")


def onboarding_html() -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates = [
            os.path.join(base, "onboarding", "index.html"),
            os.path.join(os.path.dirname(sys.executable), "onboarding", "index.html"),
        ]
    else:
        candidates = [
            os.path.join(os.path.dirname(__file__), "onboarding", "index.html"),
            resource_path("gui", "onboarding", "index.html"),
        ]
    return _first_existing(candidates) or candidates[0]


def recent_projects_file() -> str:
    # Keep the original %APPDATA% location so existing students do not lose
    # their recent-project list after upgrading.
    appdata = os.path.expandvars(r"%APPDATA%\FlutterWay")
    try:
        os.makedirs(appdata, exist_ok=True)
    except Exception:
        pass
    return os.path.join(appdata, "recent_projects.json")


def vscode_settings_path() -> str:
    return os.path.expandvars(r"%APPDATA%\Code\User\settings.json")


def vscode_cli() -> str | None:
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft VS Code\bin\code.cmd"),
    ]
    found = _first_existing(candidates)
    if found:
        return found

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        result = subprocess.run(
            ["where.exe", "code"],
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if line.lower().endswith((".cmd", ".exe")):
                    return line.strip()
    except Exception:
        pass
    return shutil.which("code")
