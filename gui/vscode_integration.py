import os
import sys
import json
import re
import subprocess

try:
    from gui import paths
except ImportError:
    import paths

def find_code_cli():
    return paths.vscode_cli()

def get_vscode_status(flutter_target_dir=None):
    flutter_target_dir = flutter_target_dir or paths.flutter_root()
    code_cli = find_code_cli()
    if not code_cli:
        return {
            "installed": False,
            "code_path": None,
            "has_flutter_ext": False,
            "has_dart_ext": False,
            "flutter_sdk_path": None,
            "is_ready": False,
            "reason": "لم يتم العثور على محرر VS Code"
        }

    # Check installed extensions (Instant check via .vscode/extensions folder)
    has_flutter = False
    has_dart = False
    ext_dir = os.path.expandvars(r"%USERPROFILE%\.vscode\extensions")
    if os.path.exists(ext_dir):
        try:
            for item in os.listdir(ext_dir):
                item_lower = item.lower()
                if "dart-code.flutter" in item_lower:
                    has_flutter = True
                if "dart-code.dart-code" in item_lower:
                    has_dart = True
        except Exception:
            pass

    # Fallback to CLI if needed
    if not (has_flutter and has_dart):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            res = subprocess.run([code_cli, "--list-extensions"], capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            exts = res.stdout.lower()
            if not has_flutter:
                has_flutter = "dart-code.flutter" in exts
            if not has_dart:
                has_dart = "dart-code.dart-code" in exts
        except Exception:
            pass

    # Check settings.json
    settings_path = paths.vscode_settings_path()
    current_sdk_path = None
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                content = f.read()
            clean = re.sub(r"^\s*//.*$", "", content, flags=re.MULTILINE)
            clean = re.sub(r",\s*([\]}])", r"\1", clean)
            data = json.loads(clean)
            current_sdk_path = data.get("dart.flutterSdkPath")
        except Exception:
            pass

    is_ready = has_flutter and has_dart and (current_sdk_path is not None)

    return {
        "installed": True,
        "code_path": code_cli,
        "has_flutter_ext": has_flutter,
        "has_dart_ext": has_dart,
        "flutter_sdk_path": current_sdk_path,
        "is_ready": is_ready
    }

def configure_vscode(flutter_target_dir=None):
    flutter_target_dir = flutter_target_dir or paths.flutter_root()
    status = get_vscode_status(flutter_target_dir)
    code_cli = status.get("code_path")
    if not code_cli:
        return {"success": False, "error": "VS Code غير مثبت على الجهاز"}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    creationflags = subprocess.CREATE_NO_WINDOW

    # Only install extensions if they are genuinely missing
    if not status["has_flutter_ext"]:
        try:
            subprocess.run([code_cli, "--install-extension", "dart-code.flutter"], capture_output=True, startupinfo=startupinfo, creationflags=creationflags, timeout=30)
        except Exception:
            pass

    if not status["has_dart_ext"]:
        try:
            subprocess.run([code_cli, "--install-extension", "dart-code.dart-code"], capture_output=True, startupinfo=startupinfo, creationflags=creationflags, timeout=30)
        except Exception:
            pass

    # Update settings.json safely
    settings_path = paths.vscode_settings_path()
    settings_dir = os.path.dirname(settings_path)
    os.makedirs(settings_dir, exist_ok=True)

    settings_data = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                content = f.read()
            clean = re.sub(r"^\s*//.*$", "", content, flags=re.MULTILINE)
            clean = re.sub(r",\s*([\]}])", r"\1", clean)
            settings_data = json.loads(clean)
        except Exception:
            settings_data = {}

    settings_data["dart.flutterSdkPath"] = flutter_target_dir
    settings_data["editor.formatOnSave"] = True
    settings_data["dart.previewFlutterUiGuides"] = True
    settings_data["dart.openDevTools"] = "flutter"

    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=2, ensure_ascii=False)
        return {"success": True, "sdk_path": flutter_target_dir}
    except Exception as e:
        return {"success": False, "error": f"فشل حفظ إعدادات VS Code: {e}"}

if __name__ == "__main__":
    print("Status:", get_vscode_status())
