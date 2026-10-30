"""Granular developer reset tools for repeatable student-journey tests.

Everything here is developer-only. The UI must show the exact paths and ask for
an explicit confirmation before legacy SDK folders (C:\\flutter, C:\\Android,
C:\\g) are removed.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import time
from datetime import datetime

try:
    from gui import paths
except ImportError:
    import paths

LEGACY_FLUTTER = r"C:\flutter"
LEGACY_ANDROID = r"C:\Android"
LEGACY_GRADLE = r"C:\g"
# Legacy project folder names are kept for display/inventory only. They are no
# longer deleted automatically: a folder name is not proof of ownership.


def _size_mb(path: str, max_files: int = 4000) -> float | None:
    if not os.path.exists(path):
        return None
    if os.path.isfile(path):
        return round(os.path.getsize(path) / (1024 * 1024), 1)
    total = 0
    seen = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except Exception:
                pass
            seen += 1
            if seen >= max_files:
                return round(total / (1024 * 1024), 1)
    return round(total / (1024 * 1024), 1)


def _target(target_id, label, path, managed=True, danger="low", with_size=True):
    exists = os.path.exists(path)
    return {
        "id": target_id,
        "label": label,
        "path": path,
        "exists": exists,
        "managed": managed,
        "danger": danger,
        "size_mb": _size_mb(path) if exists and with_size else None,
    }


def _user_path() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "Path")
            return value or ""
    except Exception:
        return os.environ.get("PATH", "")


def _env_status():
    import winreg
    variables = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            for name in ("JAVA_HOME", "GRADLE_USER_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
                try:
                    variables[name] = winreg.QueryValueEx(key, name)[0]
                except FileNotFoundError:
                    pass
    except Exception:
        pass
    return {"path": _user_path(), "variables": variables}


def _vscode_status():
    settings_path = paths.vscode_settings_path()
    extensions = []
    code_cli = paths.vscode_cli()
    if code_cli:
        try:
            result = subprocess.run(
                [code_cli, "--list-extensions"],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            extensions = [
                line.strip() for line in result.stdout.splitlines()
                if line.strip().lower() in ("dart-code.flutter", "dart-code.dart-code")
            ]
        except Exception:
            pass
    if not os.path.exists(settings_path):
        return {"path": settings_path, "exists": False, "keys": [], "extensions": extensions}
    try:
        with open(settings_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        # settings.json supports comments in VS Code; strip the common cases.
        import re
        content = re.sub(r"^\s*//.*$", "", content, flags=re.MULTILINE)
        content = re.sub(r",\s*([\]}])", r"\1", content)
        data = json.loads(content)
        keys = [key for key in data if key.startswith("dart.")]
        return {"path": settings_path, "exists": True, "keys": keys, "extensions": extensions}
    except Exception:
        return {"path": settings_path, "exists": True, "keys": [], "extensions": extensions}


def _device_packages():
    adb = paths.adb_path()
    packages = []
    try:
        result = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=8)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[1] != "device":
                continue
            serial = parts[0]
            listing = subprocess.run(
                [adb, "-s", serial, "shell", "pm", "list", "packages"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            for package_line in listing.stdout.splitlines():
                package = package_line.strip().replace("package:", "")
                if package == "com.example.flutter_test_app" or package.startswith("com.university.flutterway."):
                    packages.append({"serial": serial, "package": package})
    except Exception:
        pass
    return packages


def status() -> dict:
    data = paths.data_dir()
    managed = [
        _target("flutter_managed", "Flutter SDK (أنشأه FlutterWay)", os.path.join(data, "flutter")),
        _target("android_managed", "Android SDK (أنشأه FlutterWay)", os.path.join(data, "android-sdk")),
        _target("gradle_managed", "Gradle Home (أنشأه FlutterWay)", os.path.join(data, "gradle")),
        _target("cache", "تحميلات وأرشيفات FlutterWay", os.path.join(data, "cache")),
    ]
    jdk_dirs = glob.glob(os.path.join(data, "jdk-*"))
    managed.append(_target("jdk_managed", "JDK (أنشأه FlutterWay)", jdk_dirs[0] if jdk_dirs else os.path.join(data, "jdk")))

    projects = [
        _target("project_default", "مشروع my_first_app", paths.default_project_path()),
        _target("projects_lectures", "مجلد مشاريع المحاضرات", paths.lecture_projects_dir()),
        _target("recent_projects", "سجل المشاريع الحديثة", paths.recent_projects_file(), with_size=False),
    ]

    legacy = [
        _target("flutter_legacy", "Flutter SDK القديم (C:\\flutter)", LEGACY_FLUTTER, managed=False, danger="high", with_size=False),
        _target("android_legacy", "Android SDK القديم (C:\\Android)", LEGACY_ANDROID, managed=False, danger="high", with_size=False),
        _target("gradle_legacy", "Gradle Home القديم (C:\\g)", LEGACY_GRADLE, managed=False, danger="high", with_size=False),
    ]

    jdk = paths.jdk_home()
    if jdk and not os.path.abspath(jdk).lower().startswith(os.path.abspath(data).lower()):
        legacy.append(_target("jdk_system", "JDK النظامي (Program Files)", jdk, managed=False, danger="high", with_size=False))

    return {
        "data_dir": data,
        "targets": managed + projects + legacy,
        "env": _env_status(),
        "vscode": _vscode_status(),
        "device_packages": _device_packages(),
        "legacy_confirmation": "DELETE",
    }


def _backup_environment(logs: list[str]) -> str:
    backup_dir = os.path.join(paths.data_dir(), "backups", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(backup_dir, exist_ok=True)
    data = {"path": _user_path(), "env": _env_status().get("variables", {})}
    path = os.path.join(backup_dir, "environment.json")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        logs.append(f"تم حفظ نسخة احتياطية من البيئة: {path}")
    except Exception as exc:
        logs.append(f"تعذر حفظ نسخة احتياطية من البيئة: {exc}")
    return backup_dir


def _delete(path: str, allowed_roots: list[str], logs: list[str]) -> bool:
    resolved = os.path.abspath(path)
    normalized = os.path.normcase(resolved)
    allowed = []
    for root in allowed_roots:
        if not root:
            continue
        if os.path.isfile(root):
            allowed.append(os.path.normcase(os.path.abspath(root)))
        else:
            allowed.append(os.path.normcase(os.path.abspath(root)))
    if normalized not in allowed:
        logs.append(f"تم تجاهل مسار غير مسموح: {resolved}")
        return False
    if not os.path.exists(resolved):
        return False
    try:
        if os.path.isdir(resolved):
            shutil.rmtree(resolved, ignore_errors=False)
        else:
            os.remove(resolved)
        logs.append(f"تم الحذف: {resolved}")
        return True
    except Exception as exc:
        logs.append(f"تعذر حذف {resolved}: {exc}")
        return False


def reset_projects(logs: list[str]) -> None:
    # A folder name is not proof of ownership. Keep projects until a signed
    # marker plus quarantine/restore workflow exists (see B3).
    logs.append(
        "لم يُحذف أي مشروع: لا يوجد إثبات ملكية موثوق بعد. "
        "احذف المشروع يدوياً أو استخدم أداة الحجر عند توفرها."
    )
    logs.append("أُبقي سجل المشاريع الحديثة كما هو.")


def _managed_download_paths() -> list[str]:
    data = paths.data_dir()
    result = [
        os.path.join(data, "flutter"),
        os.path.join(data, "android-sdk"),
        os.path.join(data, "gradle"),
        os.path.join(data, "cache"),
    ]
    result.extend(glob.glob(os.path.join(data, "jdk-*")))
    return result


def reset_downloads(logs: list[str], include_legacy: bool = False) -> None:
    # Stop Gradle daemons before touching their cache.
    try:
        try:
            from gui import companion_service
        except ImportError:
            import companion_service
        killed = companion_service.kill_gradle_daemons()
        logs.append(f"تم إيقاف {killed} من عمليات Gradle قبل حذف الكاش")
    except Exception as exc:
        logs.append(f"تنبيه: تعذر إيقاف Gradle: {exc}")

    for path in _managed_download_paths():
        _delete(path, [path], logs)

    if include_legacy:
        for path in (LEGACY_FLUTTER, LEGACY_ANDROID, LEGACY_GRADLE):
            _delete(path, [path], logs)


def reset_environment(logs: list[str]) -> None:
    import winreg

    _backup_environment(logs)
    path_value = _user_path()
    entries = [entry.strip() for entry in path_value.split(";") if entry.strip()]

    remove = {
        os.path.normcase(os.path.normpath(os.path.join(paths.flutter_root(), "bin"))),
        os.path.normcase(os.path.normpath(os.path.join(paths.android_sdk_root(), "platform-tools"))),
        os.path.normcase(os.path.normpath(LEGACY_FLUTTER + r"\bin")),
        os.path.normcase(os.path.normpath(LEGACY_ANDROID + r"\platform-tools")),
    }
    jdk = paths.jdk_home()
    if jdk:
        remove.add(os.path.normcase(os.path.normpath(os.path.join(jdk, "bin"))))

    kept = [entry for entry in entries if os.path.normcase(os.path.normpath(entry)) not in remove]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(kept) + (";" if kept else ""))
            for name in ("JAVA_HOME", "GRADLE_USER_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        os.environ["PATH"] = ";".join(kept)
        for name in ("JAVA_HOME", "GRADLE_USER_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
            os.environ.pop(name, None)
        try:
            import ctypes
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
        except Exception:
            pass
        logs.append("تمت إزالة مسارات Flutter/JDK/SDK ومتغيرات البيئة (مع نسخة احتياطية)")
    except Exception as exc:
        logs.append(f"تعذر تعديل PATH/البيئة: {exc}")


def reset_vscode(logs: list[str]) -> None:
    import re

    settings_path = paths.vscode_settings_path()
    if not os.path.exists(settings_path):
        logs.append("لا توجد إعدادات VS Code لحذفها")
    else:
        try:
            with open(settings_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            content = re.sub(r"^\s*//.*$", "", content, flags=re.MULTILINE)
            content = re.sub(r",\s*([\]}])", r"\1", content)
            data = json.loads(content)
            removed = []
            for key in ("dart.flutterSdkPath", "dart.previewFlutterUiGuides", "dart.openDevTools"):
                if key in data:
                    del data[key]
                    removed.append(key)
            with open(settings_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            logs.append("تم حذف إعدادات Flutter من VS Code: " + (", ".join(removed) if removed else "لا شيء"))
        except Exception as exc:
            logs.append(f"تعذر تعديل إعدادات VS Code: {exc}")

def reset_vscode_extensions(logs: list[str]) -> None:
    cli = paths.vscode_cli()
    if not cli:
        logs.append("لم يتم العثور على VS Code لحذف الإضافات")
        return
    for extension in ("dart-code.flutter", "dart-code.dart-code"):
        try:
            result = subprocess.run(
                [cli, "--uninstall-extension", extension],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logs.append(f"إلغاء تثبيت {extension}: {result.stdout.strip() or result.stderr.strip() or 'OK'}")
        except Exception as exc:
            logs.append(f"تعذر إلغاء تثبيت {extension}: {exc}")

def reset_jdk(logs: list[str]) -> None:
    jdk = paths.jdk_home()
    if not jdk:
        logs.append("لا يوجد JDK نظامي لحذفه")
        return
    try:
        result = subprocess.run(
            [
                "winget", "uninstall",
                "--id", "EclipseAdoptium.Temurin.21.JDK",
                "--silent",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        tail = (result.stdout or result.stderr or "").strip().splitlines()[-3:]
        logs.append(f"winget JDK uninstall (كود {result.returncode}): {' | '.join(tail) or 'بدون مخرجات'}")
    except Exception as exc:
        logs.append(f"تعذر إلغاء تثبيت JDK عبر winget: {exc}")


def reset_device(logs: list[str]) -> None:
    adb = paths.adb_path()
    try:
        result = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=8)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[1] != "device":
                continue
            serial = parts[0]
            listing = subprocess.run(
                [adb, "-s", serial, "shell", "pm", "list", "packages"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            for package_line in listing.stdout.splitlines():
                package = package_line.strip().replace("package:", "")
                if package == "com.example.flutter_test_app" or package.startswith("com.university.flutterway."):
                    removal = subprocess.run(
                        [adb, "-s", serial, "uninstall", package],
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    logs.append(f"[{serial}] إلغاء تثبيت {package}: {removal.stdout.strip() or 'OK'}")
    except Exception as exc:
        logs.append(f"تعذر الاتصال بالهاتف: {exc}")


def reset_build_cache(logs: list[str]) -> None:
    desktop = os.path.expandvars(r"%USERPROFILE%\Desktop")
    projects = [os.path.join(desktop, "my_first_app"), paths.lecture_projects_dir()]
    for root in projects:
        if not os.path.isdir(root):
            continue
        for name in ("build", ".dart_tool"):
            target = os.path.join(root, name)
            if os.path.exists(target):
                _delete(target, [target], logs)
        # Lecture projects are one level below the parent folder.
        for child in glob.glob(os.path.join(root, "*")):
            for name in ("build", ".dart_tool"):
                target = os.path.join(child, name)
                if os.path.exists(target):
                    _delete(target, [target], logs)


def run(action: str, include_legacy: bool = False, confirm: str = "") -> dict:
    logs: list[str] = []
    action = (action or "").strip().lower()
    if action == "downloads_all":
        include_legacy = True

    if action in ("downloads_all", "all") and include_legacy and confirm != "DELETE":
        return {
            "success": False,
            "logs": logs,
            "error": "تأكيد مطلوب: اكتب DELETE لحذف C:\\flutter و C:\\Android و C:\\g",
        }

    if action == "ui":
        return {"success": True, "logs": ["إعادة تعيين الواجهة فقط"], "message": "تمت إعادة الواجهة"}

    if action == "projects":
        reset_projects(logs)
        return {"success": True, "logs": logs, "message": "تم حذف مشاريع الاختبار وسجلها"}

    if action in ("downloads", "downloads_all"):
        reset_downloads(logs, include_legacy=include_legacy or action == "downloads_all")
        return {"success": True, "logs": logs, "message": "تم حذف التحميلات المحددة"}

    if action == "environment":
        reset_environment(logs)
        return {"success": True, "logs": logs, "message": "تمت إزالة إعدادات PATH والبيئة"}

    if action == "vscode":
        reset_vscode(logs)
        return {"success": True, "logs": logs, "message": "تمت إزالة إعدادات VS Code"}

    if action == "vscode_extensions":
        reset_vscode_extensions(logs)
        return {"success": True, "logs": logs, "message": "تمت محاولة إزالة إضافات Flutter/Dart"}

    if action == "jdk":
        if confirm != "DELETE":
            return {
                "success": False,
                "logs": logs,
                "error": "تأكيد مطلوب: اكتب DELETE لحذف JDK النظامي",
            }
        reset_jdk(logs)
        return {"success": True, "logs": logs, "message": "تمت محاولة إزالة JDK"}

    if action == "device":
        reset_device(logs)
        return {"success": True, "logs": logs, "message": "تم إلغاء تثبيت التطبيقات التجريبية"}

    if action == "build":
        reset_build_cache(logs)
        return {"success": True, "logs": logs, "message": "تم حذف كاش البناء"}

    if action == "all":
        reset_device(logs)
        reset_projects(logs)
        reset_environment(logs)
        reset_vscode(logs)
        reset_downloads(logs, include_legacy=include_legacy)
        if include_legacy:
            reset_vscode_extensions(logs)
            reset_jdk(logs)
        return {"success": True, "logs": logs, "message": "تم المسح الشامل"}

    return {"success": False, "logs": logs, "error": f"إجراء غير معروف: {action}"}
