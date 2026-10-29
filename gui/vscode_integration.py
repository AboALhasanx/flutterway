import os
import sys
import json
import re
import subprocess

def find_code_cli():
    candidates = [
        r"D:\Microsoft VS Code\bin\code.cmd",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd"),
        "code"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Try where.exe
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        res = subprocess.run(["where.exe", "code"], capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().splitlines()
            for line in lines:
                if line.endswith(".cmd") or line.endswith(".exe"):
                    return line
    except Exception:
        pass
    return None

def get_vscode_status(flutter_target_dir="C:\\flutter"):
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

    # Check installed extensions silently
    has_flutter = False
    has_dart = False
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        res = subprocess.run([code_cli, "--list-extensions"], capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
        exts = res.stdout.lower()
        has_flutter = "dart-code.flutter" in exts
        has_dart = "dart-code.dart-code" in exts
    except Exception:
        pass

    # Check settings.json
    settings_path = os.path.expandvars(r"%APPDATA%\Code\User\settings.json")
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

def configure_vscode(flutter_target_dir="C:\\flutter"):
    code_cli = find_code_cli()
    if not code_cli:
        return {"success": False, "error": "VS Code غير مثبت على الجهاز"}

    # Install extensions silently
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    creationflags = subprocess.CREATE_NO_WINDOW

    try:
        subprocess.run([code_cli, "--install-extension", "dart-code.flutter", "--force"], capture_output=True, startupinfo=startupinfo, creationflags=creationflags)
        subprocess.run([code_cli, "--install-extension", "dart-code.dart-code", "--force"], capture_output=True, startupinfo=startupinfo, creationflags=creationflags)
    except Exception as e:
        return {"success": False, "error": f"فشل تثبيت الإضافات: {e}"}

    # Update settings.json safely
    settings_dir = os.path.expandvars(r"%APPDATA%\Code\User")
    os.makedirs(settings_dir, exist_ok=True)
    settings_path = os.path.join(settings_dir, "settings.json")

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
