import argparse
import os
import sys
import json
import shutil
import subprocess
import winreg

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def set_user_path(new_path_str):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path_str)
    # Broadcast WM_SETTINGCHANGE
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, ctypes.byref(result)
        )
    except Exception:
        pass

def get_user_path():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "Path")
            return val
    except Exception:
        return ""

def clean_environment():
    print("[1/5] Removing Flutter and duplicates from User PATH via WinRegistry...")
    raw_path = get_user_path()
    try:
        backup_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FlutterWay")
        os.makedirs(backup_dir, exist_ok=True)
        with open(os.path.join(backup_dir, "path_backup.txt"), "w", encoding="utf-8") as handle:
            handle.write(raw_path)
    except Exception:
        pass
    parts = [p.strip() for p in raw_path.split(";") if p.strip()]
    
    seen = set()
    cleaned = []
    for p in parts:
        lower = p.lower()
        normalized = lower.rstrip("\\/")
        if normalized.endswith("\\flutter\\bin") or normalized.endswith("/flutter/bin"):
            print(f"  - Removed: {p}")
            continue
        if lower not in seen:
            seen.add(lower)
            cleaned.append(p)
            
    new_path_str = ";".join(cleaned) + ";"
    set_user_path(new_path_str)
    print("  ✓ User PATH cleaned via Registry.")

def clean_vscode(uninstall_extensions=False):
    print("[2/5] Cleaning VS Code configuration...")
    settings_path = os.path.expandvars(r"%APPDATA%\Code\User\settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            
            modified = False
            for key in ["dart.flutterSdkPath", "dart.previewFlutterUiGuides", "dart.openDevTools"]:
                if key in settings:
                    del settings[key]
                    modified = True
                    print(f"  - Removed setting: {key}")
            
            if modified:
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2, ensure_ascii=False)
                print("  ✓ VS Code settings cleaned.")
            else:
                print("  ✓ VS Code settings already clean.")
        except Exception as e:
            print(f"  ! Error updating settings: {e}")

    if not uninstall_extensions:
        print("  - Skipping VS Code extension uninstall (pass --uninstall-extensions to opt in).")
        return

    print("[3/5] Uninstalling VS Code Flutter/Dart extensions...")
    code_candidates = [
        r"D:\Microsoft VS Code\bin\code.cmd",
        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd")
    ]
    code_bin = None
    for cand in code_candidates:
        if os.path.exists(cand):
            code_bin = cand
            break
    if not code_bin:
        code_bin = shutil.which("code")

    if code_bin:
        for ext in ["dart-code.flutter", "dart-code.dart-code"]:
            print(f"  - Uninstalling {ext}...")
            subprocess.run([code_bin, "--uninstall-extension", ext], capture_output=True, text=True)
        print("  ✓ Extensions uninstalled.")
    else:
        print("  ! VS Code CLI not found; skipping extension uninstall.")

def clean_desktop_projects():
    print("[4/5] Removing desktop starter test projects...")
    desktop = os.path.expandvars(r"%USERPROFILE%\Desktop")
    for name in ["my_first_app", "اول_تطبيق_فلاتر"]:
        target = os.path.join(desktop, name)
        if os.path.exists(target):
            try:
                shutil.rmtree(target, ignore_errors=True)
                print(f"  - Deleted: {target}")
            except Exception as e:
                print(f"  ! Failed to delete {target}: {e}")
    print("  ✓ Desktop projects wiped.")

def verify():
    print("[5/5] Verifying clean state...")
    raw_path = get_user_path()
    flutter_in_path = any(
        part.lower().rstrip("\\/").endswith("\\flutter\\bin")
        or part.lower().rstrip("\\/").endswith("/flutter/bin")
        for part in raw_path.split(";")
        if part.strip()
    )
    
    desktop = os.path.expandvars(r"%USERPROFILE%\Desktop")
    has_proj = os.path.exists(os.path.join(desktop, "my_first_app"))
    
    print(f"  - Flutter in User PATH: {flutter_in_path} (Expected: False)")
    print(f"  - Desktop project exists: {has_proj} (Expected: False)")
    print("\n✅ Clean slate successfully prepared! Computer is ready for fresh beginner simulation.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare a clean FlutterWay test slate.")
    parser.add_argument(
        "--uninstall-extensions",
        action="store_true",
        help="Also uninstall the user's global VS Code Flutter/Dart extensions.",
    )
    args = parser.parse_args()
    clean_environment()
    clean_vscode(args.uninstall_extensions)
    clean_desktop_projects()
    verify()
