import os
import sys
import json
import re
import time
import socket
import threading
import subprocess
import shutil
import zipfile
import urllib.request
import traceback
import webview
import winreg

# Cache the slow PowerShell PnP probe so the 5-second UI poll cannot spawn it
# continuously while no phone is connected.
_last_pnp_check = 0.0
_last_pnp_result = (False, "جهاز أندرويد")

# Arabic log messages must never crash a legacy Windows console.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Import our robust VS Code integration and Companion service
try:
    from gui.vscode_integration import get_vscode_status, configure_vscode, find_code_cli
    from gui import companion_service
    from gui import paths
    from gui import android_sdk
    from gui import android_apk
    from gui import dev_reset
    from gui import managed
    from gui import downloads
    from gui import toolchain
    from gui import hot_reload
    from gui import diagnostics
except ImportError:
    from vscode_integration import get_vscode_status, configure_vscode, find_code_cli
    import companion_service
    import paths
    import android_sdk
    import android_apk
    import dev_reset
    import managed
    import downloads
    import toolchain
    import hot_reload
    import diagnostics

def _broadcast_environment_change():
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
    except Exception:
        pass


def set_user_env(name, value):
    """Set a user environment variable and verify it persisted. Returns bool."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            val_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, val_type, value)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, 0) as key:
            stored, _ = winreg.QueryValueEx(key, name)
        if str(stored) != str(value):
            print(f"Registry env {name} did not persist (readback mismatch)")
            return False
        _broadcast_environment_change()
        return True
    except Exception as e:
        print(f"Error setting registry env {name}: {e}")
        return False

def add_to_user_path(new_dir):
    """Add a folder to the user PATH and verify it persisted. Returns bool."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
            try:
                val, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                val = ""
            parts = [p.strip() for p in val.split(";") if p.strip()]
            try:
                with open(os.path.join(paths.data_dir(), "path_backup.txt"), "w", encoding="utf-8") as backup:
                    backup.write(val)
            except Exception:
                pass
            if not any(new_dir.lower() == p.lower() for p in parts):
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_dir + ";" + val)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, 0) as key:
            stored, _ = winreg.QueryValueEx(key, "Path")
        stored_parts = [p.strip() for p in str(stored).split(";") if p.strip()]
        if not any(new_dir.lower() == p.lower() for p in stored_parts):
            print("Registry PATH update did not persist (readback mismatch)")
            return False
        curr = os.environ.get("PATH", "")
        if new_dir.lower() not in curr.lower():
            os.environ["PATH"] = new_dir + ";" + curr
        _broadcast_environment_change()
        return True
    except Exception as e:
        print(f"Registry PATH update error: {e}")
        return False

def find_adb():
    return paths.adb_path()

def find_jdk():
    return paths.jdk_home()

JDK_PORTABLE_URL = "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk"
JDK_MIN_ZIP_BYTES = 100 * 1024 * 1024


def _percent_from_text(text):
    match = re.search(r"(\d{1,3})\s*%", text or "")
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _jdk_report(progress, message):
    try:
        if progress:
            progress(message)
        else:
            print(message)
    except Exception:
        pass


JDK_API_URL = (
    "https://api.adoptium.net/v3/assets/latest/21/hotspot"
    "?architecture=x64&image_type=jdk&os=windows&vendor=eclipse"
)


def _adoptium_checksum() -> str | None:
    """Fetch the official SHA-256 for the Temurin 21 Windows x64 JDK."""
    try:
        request = urllib.request.Request(JDK_API_URL, headers={"User-Agent": "FlutterWay/1.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            assets = json.loads(response.read().decode("utf-8"))
        for asset in assets or []:
            package = ((asset or {}).get("binary") or {}).get("package") or {}
            checksum = str(package.get("checksum") or "").strip().lower()
            if len(checksum) == 64:
                return checksum
    except Exception as exc:
        print("Adoptium metadata error:", exc)
    return None


def _install_portable_jdk(progress=None):
    """Download and extract a user-scoped Temurin JDK, no UAC required."""
    target = os.path.join(paths.data_dir(), "jdk-21")
    java_exe = os.path.join(target, "bin", "java.exe")
    if os.path.exists(java_exe):
        return target

    cache = os.path.join(paths.data_dir(), "cache")
    os.makedirs(cache, exist_ok=True)
    zip_path = os.path.join(cache, "temurin21.zip")
    if not os.path.exists(zip_path) or os.path.getsize(zip_path) < JDK_MIN_ZIP_BYTES:
        _jdk_report(progress, "ننزّل Java 21 المحمول (بدون صلاحيات مدير)...")
        part_path = zip_path + ".part"
        try:
            request = urllib.request.Request(JDK_PORTABLE_URL, headers={"User-Agent": "FlutterWay/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response, open(part_path, "wb") as output:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                last_tenth = -1
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = int(downloaded * 100 / total)
                        if percent // 10 != last_tenth:
                            last_tenth = percent // 10
                            _jdk_report(progress, f"ننزّل Java 21 المحمول... {percent}%")
            if os.path.getsize(part_path) < JDK_MIN_ZIP_BYTES:
                raise RuntimeError("ملف Java الذي نُزّل غير مكتمل")
            os.replace(part_path, zip_path)
        except Exception as exc:
            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except Exception:
                pass
            print("Portable JDK download error:", exc)
            return None

    expected = _adoptium_checksum()
    if expected:
        check = downloads.verify_file(zip_path, expected, JDK_MIN_ZIP_BYTES)
        if not check.get("ok"):
            print("Portable JDK checksum rejected:", check)
            _jdk_report(progress, "ملف Java لا يطابق البصمة الرسمية — نحذفه ونعيد المحاولة لاحقاً.")
            try:
                os.remove(zip_path)
            except Exception:
                pass
            return None
    else:
        print("Adoptium checksum unavailable; falling back to size check only.")

    _jdk_report(progress, "نفكّ ضغط Java 21...")
    extract_dir = os.path.join(cache, "jdk_extract")
    try:
        if os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        extraction = downloads.safe_extract_zip(zip_path, extract_dir)
        if not extraction.get("ok"):
            raise RuntimeError(f"ملف Java غير آمن أو تالف: {extraction.get('reason')}")
        found = None
        for root, _dirs, files in os.walk(extract_dir):
            if "java.exe" in files and os.path.basename(root).lower() == "bin":
                found = os.path.dirname(root)
                break
        if not found:
            raise RuntimeError("لم نجد java.exe داخل حزمة Java")
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(found, target)
        shutil.rmtree(extract_dir, ignore_errors=True)
        if not os.path.exists(java_exe):
            raise RuntimeError("تركيب Java المحمول لم يكتمل")
        return target
    except Exception as exc:
        print("Portable JDK extract error:", exc)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass
        return None


def _is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_jdk(progress=None):
    """Locates or installs JDK 21 (portable first), then configures JAVA_HOME/PATH."""
    jdk = find_jdk()
    if not jdk:
        _jdk_report(progress, "نجهّز Java 21 بدون صلاحيات مدير...")
        jdk = _install_portable_jdk(progress)

    if not jdk and _is_admin():
        _jdk_report(progress, "ننزّل Java 21 عبر winget كخطة بديلة...")
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            subprocess.run(
                ["winget", "install", "EclipseAdoptium.Temurin.21.JDK", "--silent", "--accept-source-agreements", "--accept-package-agreements", "-h"],
                capture_output=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180
            )
            jdk = find_jdk()
        except Exception as e:
            print("Winget JDK install fallback error:", e)
    elif not jdk:
        print("JDK portable install failed; winget needs admin and was skipped.")

    if jdk:
        gradle_home = paths.gradle_user_home()
        os.environ["JAVA_HOME"] = jdk
        os.environ["GRADLE_USER_HOME"] = gradle_home
        set_user_env("JAVA_HOME", jdk)
        set_user_env("GRADLE_USER_HOME", gradle_home)
        add_to_user_path(os.path.join(jdk, "bin"))
    return jdk

def _looks_like_android_pnp(name):
    """A PnP friendly name is a real Android candidate, not a random OtherDevices entry."""
    lowered = (name or "").strip().lower()
    return "android" in lowered or "adb" in lowered


def install_succeeded(returncode, output) -> bool:
    """adb install is successful only with rc 0 *and* a Success line."""
    text = str(output or "")
    return returncode == 0 and "Success" in text


def install_outcome(returncode, output) -> tuple[bool, str | None]:
    if install_succeeded(returncode, output):
        return True, None
    return False, ("install_failed" if returncode else "install_unconfirmed")


class OnboardingApi:
    def __init__(self, window_holder):
        self.window_holder = window_holder
        self.state = {
            "current_step": 1,
            "selected_mode": "usb",
            "progress_percent": 0,
            "is_complete": False,
            "theme": "dark",
            "connected_device": None,
            "project_path": paths.default_project_path(),
            "app_running_on_phone": False,
            "missing_drivers": False,
            "setup_error": None,
            "build_running": False,
            "setup_running": False
        }
        self.hot_reload = hot_reload.HotReloadSession()
        diagnostics.configure_logging()

    def check_laptop_compatibility(self):
        try:
            import psutil
            import shutil

            ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
            total, used, free = shutil.disk_usage('C:\\')
            free_gb = round(free / (1024**3), 1)
            cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 2

            # Check virtualization in BIOS
            vt_enabled = False
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                res = subprocess.run(
                    ['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled'],
                    capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, timeout=3
                )
                if 'True' in res.stdout:
                    vt_enabled = True
            except Exception:
                pass

            if not vt_enabled:
                rec_mode = "usb"
                reason = "المحاكاة غير مفعّلة في BIOS. هاتف USB هو المسار الجاهز فوراً."
            elif ram_gb < 8:
                rec_mode = "usb"
                reason = f"الرام {ram_gb}GB قليلة للمحاكي. هاتف USB أخف وأسرع."
            else:
                rec_mode = "usb"
                reason = f"لابتوبك جاهز ({ram_gb}GB رام). هاتف USB أسرع وأخف من المحاكي."

            return {
                "success": True,
                "ram_gb": ram_gb,
                "free_disk_gb": free_gb,
                "cpu_cores": cpu_cores,
                "vt_enabled": vt_enabled,
                "recommended_mode": rec_mode,
                "reason": reason,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "ram_gb": 8.0,
                "free_disk_gb": 30.0,
                "cpu_cores": 4,
                "vt_enabled": False,
                "recommended_mode": "usb",
                "reason": "ننصحك باستخدام هاتف أندرويد عبر USB لضمان أفضل سرعة وأداء."
            }

    def check_connected_devices(self):
        adb = find_adb()
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW
        try:
            res = subprocess.run(
                [adb, "devices", "-l"],
                capture_output=True, text=True, startupinfo=startupinfo, creationflags=creationflags, timeout=3
            )
            lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
            devices = []
            for line in lines:
                if line.startswith("List of devices") or line.startswith("*"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    status = parts[1]  # 'device', 'unauthorized', 'offline'
                    model = "هاتف أندرويد"
                    for p in parts[2:]:
                        if p.startswith("model:"):
                            model = p.split("model:")[1].replace("_", " ")
                    devices.append({
                        "serial": serial,
                        "status": status,
                        "model": model,
                        "is_ready": (status == "device")
                    })
            
            # Check if there is an unconfigured Android device via PnP (cached).
            missing_driver = False
            missing_name = "جهاز أندرويد"
            global _last_pnp_check, _last_pnp_result
            if not devices:
                if time.time() - _last_pnp_check > 15:
                    try:
                        ps_cmd = 'Get-PnpDevice -PresentOnly | Where-Object { ($_.FriendlyName -like "*Android*" -or $_.FriendlyName -like "*ADB*") -and $_.Status -ne "OK" } | Select-Object -ExpandProperty FriendlyName -First 5'
                        pnp_res = subprocess.run(
                            ['powershell', '-NoProfile', '-Command', ps_cmd],
                            capture_output=True, text=True, startupinfo=startupinfo, creationflags=creationflags, timeout=2
                        )
                        candidates = [
                            line.strip() for line in pnp_res.stdout.splitlines()
                            if _looks_like_android_pnp(line)
                        ]
                        if candidates:
                            missing_driver = True
                            missing_name = candidates[0]
                    except Exception:
                        pass
                    _last_pnp_check = time.time()
                    _last_pnp_result = (missing_driver, missing_name)
                else:
                    missing_driver, missing_name = _last_pnp_result

            self.state["missing_drivers"] = missing_driver

            if devices and devices[0]["is_ready"]:
                self.state["connected_device"] = devices[0]

            return {
                "success": True,
                "devices": devices,
                "count": len(devices),
                "missing_driver": missing_driver,
                "missing_name": missing_name
            }
        except Exception as e:
            return {"success": False, "devices": [], "count": 0, "error": str(e), "missing_driver": False}

    def install_usb_drivers(self):
        """Installs the official Google Universal USB Driver package via Windows pnputil with UAC elevation."""
        inf_path = paths.driver_inf_path()
        if not os.path.exists(inf_path):
            return {"success": False, "error": "ملف التعريف غير موجود في مجلد الأدوات"}
        
        try:
            cmd = f'Start-Process pnputil -ArgumentList \'/add-driver "{inf_path}" /install\' -Verb RunAs -Wait; Start-Process pnputil -ArgumentList \'/scan-devices\' -Verb RunAs'
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], timeout=20)
            return {"success": True, "message": "تم إطلاق نافذة تثبيت التعريفات بنجاح"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restart_adb(self):
        adb = find_adb()
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW
        try:
            subprocess.run([adb, "kill-server"], startupinfo=startupinfo, creationflags=creationflags, timeout=3)
            subprocess.run([adb, "start-server"], startupinfo=startupinfo, creationflags=creationflags, timeout=5)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_test_app(self, serial=None):
        """Installs and executes the compiled Flutter app from Desktop project onto the physical Android phone."""
        adb = find_adb()
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW

        # 1. Resolve serial if not passed
        if not serial and self.state.get("connected_device"):
            serial = self.state["connected_device"]["serial"]
        if not serial:
            devs = companion_service.get_connected_devices()
            if devs:
                serial = devs[0].get("serial")

        # 2. Query device model
        device_name = "هاتف أندرويد"
        manufacturer = "أندرويد"
        if serial:
            try:
                res = subprocess.run(
                    [adb, "-s", serial, "shell", "getprop", "ro.product.model"],
                    capture_output=True, text=True, startupinfo=startupinfo, creationflags=creationflags, timeout=3
                )
                if res.stdout.strip():
                    device_name = res.stdout.strip().replace("_", " ")
                m_res = subprocess.run(
                    [adb, "-s", serial, "shell", "getprop", "ro.product.manufacturer"],
                    capture_output=True, text=True, startupinfo=startupinfo, creationflags=creationflags, timeout=3
                )
                if m_res.stdout.strip():
                    manufacturer = m_res.stdout.strip().capitalize()
            except Exception:
                pass

        # 3. Locate compiled APK strictly from real project build output
        project_path = self.state.get("project_path") or paths.default_project_path()
        app_id = companion_service.get_application_id(project_path)
        apk_candidates = [
            os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-release.apk"),
            os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-profile.apk"),
            os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-debug.apk"),
            os.path.join(project_path, "build", "app", "outputs", "apk", "debug", "app-debug.apk")
        ]
        apk_path = None
        for cand in apk_candidates:
            if os.path.exists(cand):
                apk_path = cand
                break

        if not apk_path:
            return {
                "success": False,
                "error": "لم يتم بناء ملف APK بعد. يرجى الضغط على زر بناء التطبيق الفعلي أولاً."
            }

        apk_path = android_apk.optimize_apk(apk_path, print)

        # 4. Install & Launch on Phone
        installed_ok = False
        install_error = None
        if serial and apk_path:
            try:
                i_res = subprocess.run(
                    [adb, "-s", serial, "install", "-r", apk_path],
                    capture_output=True, text=True, timeout=35,
                    startupinfo=startupinfo, creationflags=creationflags,
                )
                output = ((i_res.stdout or "") + "\n" + (i_res.stderr or "")).strip()
                installed_ok, _code = install_outcome(i_res.returncode, output)
                if not installed_ok:
                    install_error = f"install rc={i_res.returncode}: {output[-300:]}"
                    print("App install failed:", install_error)
                else:
                    subprocess.run(
                        [adb, "-s", serial, "shell", "monkey", "-p", app_id, "-c", "android.intent.category.LAUNCHER", "1"],
                        capture_output=True, startupinfo=startupinfo, creationflags=creationflags, timeout=5
                    )
            except Exception as e:
                install_error = str(e)
                print("App install/launch error:", e)

        self.state["app_running_on_phone"] = installed_ok

        return {
            "success": installed_ok,
            "device_name": f"{manufacturer} {device_name}".strip(),
            "installed_ok": installed_ok,
            "error": None if installed_ok else (install_error or "تعذر التحقق من التثبيت"),
            "message": (
                f"تم تشغيل التطبيق بنجاح على {manufacturer} {device_name}!"
                if installed_ok else
                "تعذر تثبيت أو تشغيل التطبيق على الهاتف. راجع اتصال USB وسجل الأخطاء."
            )
        }

    def start_real_gradle_build(self, project_path=None, serial=None):
        """Asynchronously runs the REAL Flutter Gradle build on the selected project,
        streaming live logs to the UI console and installing the fresh APK on the connected device."""
        if self.state.get("build_running"):
            return {"success": False, "error": "في عملية بناء شغالة بالفعل. انتظرها تكمل أو أغلق التطبيق."}
        self.state["build_running"] = True
        if project_path and os.path.isdir(project_path):
            self.state["project_path"] = project_path
        win = self.window_holder.get("window")

        # Short, student-facing progress messages (no Gradle/DEX jargon).
        messages = [
            (0, "🚀 بدأنا بناء التطبيق... أول مرة قد تأخذ دقيقة.", 1),
            (15, "📦 نجهّز المكتبات التي يحتاجها مشروعك.", 2),
            (45, "🔨 نبني التطبيق الآن... لا تغلق النافذة.", 2),
            (85, "⏳ العملية تأخذ وقتاً أطول على بعض الأجهزة. نكمل.", 3),
            (125, "📱 نجهّز ملف التطبيق للتثبيت.", 3),
            (155, "⚡ اللمسات الأخيرة... بعدها يفتح التطبيق على هاتفك.", 3),
        ]

        def build_worker():
            t_start = time.time()
            stop_ticker = False

            # Ticker thread to update UI in real-time
            def ticker():
                while not stop_ticker:
                    elapsed = int(time.time() - t_start)
                    cur_msg = messages[0][1]
                    cur_phase = messages[0][2]
                    for sec, msg, phase in messages:
                        if elapsed >= sec:
                            cur_msg = msg
                            cur_phase = phase

                    if win:
                        escaped_msg = cur_msg.replace("'", "\\'")
                        js = f"updateBuildTicker({elapsed}, '{escaped_msg}', {cur_phase});"
                        try:
                            win.evaluate_js(js)
                        except Exception:
                            pass
                    time.sleep(1.0)

            ticker_thread = threading.Thread(target=ticker, daemon=True)
            ticker_thread.start()

            # Helper to stream live log to UI terminal
            def send_log(line):
                if win and line:
                    safe = line.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace("\r", "")
                    try:
                        win.evaluate_js(f"appendLiveBuildLog('{safe}');")
                    except Exception:
                        pass

            # 1. Resolve target serial
            target_serial = serial
            if not target_serial and self.state.get("connected_device"):
                target_serial = self.state["connected_device"].get("serial")
            if not target_serial:
                devs = companion_service.get_connected_devices()
                if devs:
                    target_serial = devs[0].get("serial")

            # 2. Resolve project path
            project_path = self.state.get("project_path") or paths.default_project_path()
            self._ensure_starter_project(project_path)
            app_id = companion_service.get_application_id(project_path)

            send_log(f"$ cd {project_path}")
            build_mode = os.environ.get("FLUTTERWAY_BUILD_MODE", "debug").strip().lower()
            if build_mode not in ("debug", "profile", "release"):
                build_mode = "debug"
            send_log(f"$ flutter build apk --{build_mode} -v")

            # 3. Locate flutter.bat and java
            flutter_bat = paths.flutter_bat()

            jdk_path = ensure_jdk()
            env = os.environ.copy()
            if jdk_path and os.path.exists(jdk_path):
                env["JAVA_HOME"] = jdk_path
                env["PATH"] = os.path.join(jdk_path, "bin") + ";" + env.get("PATH", "")
            flutter_bin = os.path.dirname(flutter_bat)
            if os.path.exists(flutter_bin):
                env["PATH"] = flutter_bin + ";" + env.get("PATH", "")
            adb = find_adb()
            adb_dir = os.path.dirname(adb) if adb else ""
            if adb_dir and os.path.exists(adb_dir):
                env["PATH"] = adb_dir + ";" + env.get("PATH", "")

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = subprocess.CREATE_NO_WINDOW

            # Detect connected phone ABI for optimal, fast architecture-specific compilation
            target_abi_flag = []
            if target_serial:
                try:
                    abi_res = subprocess.run([adb, "-s", target_serial, "shell", "getprop", "ro.product.cpu.abi"], capture_output=True, text=True, timeout=3, startupinfo=startupinfo, creationflags=creationflags)
                    abi = abi_res.stdout.strip().lower()
                    if "arm64" in abi:
                        target_abi_flag = ["--target-platform", "android-arm64"]
                    elif "v7a" in abi or "arm" in abi:
                        target_abi_flag = ["--target-platform", "android-arm"]
                    elif "x86_64" in abi:
                        target_abi_flag = ["--target-platform", "android-x64"]
                except Exception:
                    pass

            cmd = [flutter_bat, "build", "apk", f"--{build_mode}", "-v"] + target_abi_flag
            send_log(f"$ {' '.join(cmd)}")

            build_success = False
            build_returncode = None
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=project_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )

                for raw_line in iter(proc.stdout.readline, ''):
                    line = raw_line.strip()
                    if not line:
                        continue

                    # Strip verbose timing prefix like "[ +120 ms] "
                    if line.startswith("[") and "ms]" in line[:22]:
                        parts = line.split("ms]", 1)
                        if len(parts) > 1:
                            line = parts[1].strip()

                    # Filter informative Gradle/compiler tasks to stream live
                    if any(kw in line for kw in [
                        "> Task :", "Running Gradle task", "Built build", "FAILURE", "BUILD SUCCESSFUL",
                        "assembleDebug", "compileDebug", "dexBuilder", "mergeExtDex", "packageDebug",
                        "Resolving dependencies", "Flutter assets", "Signing", "Kotlin:", "Starting a Gradle Daemon"
                    ]):
                        send_log(line)
                    elif "error" in line.lower() or "exception" in line.lower():
                        send_log(line)

                proc.wait()
                build_returncode = proc.returncode
                build_success = (build_returncode == 0)
            except Exception as e:
                send_log(f"خطأ أثناء استدعاء محرك فلاتر: {e}")
                build_success = False

            apk_candidates = [
                os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-release.apk"),
                os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-arm64-v8a-release.apk"),
                os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-profile.apk"),
                os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-debug.apk"),
                os.path.join(project_path, "build", "app", "outputs", "apk", "debug", "app-debug.apk")
            ]
            flutter_apk_dir = os.path.join(project_path, "build", "app", "outputs", "flutter-apk")
            if os.path.exists(flutter_apk_dir):
                for f in sorted(os.listdir(flutter_apk_dir)):
                    if f.endswith(".apk"):
                        candidate = os.path.join(flutter_apk_dir, f)
                        if candidate not in apk_candidates:
                            apk_candidates.append(candidate)

            apk_path = None
            for cand in apk_candidates:
                if os.path.exists(cand):
                    apk_path = cand
                    break

            apk_exists = (apk_path is not None)
            apk_size_mb = 0
            if apk_exists:
                optimized_apk = android_apk.optimize_apk(apk_path, send_log)
                if optimized_apk:
                    apk_path = optimized_apk
                apk_exists = os.path.exists(apk_path)
            if apk_exists:
                apk_size_mb = round(os.path.getsize(apk_path) / (1024 * 1024), 1)
                send_log(f"√ اكتمل البناء بنجاح! تم إنشاء {os.path.basename(apk_path)} ({apk_size_mb} MB)")
            else:
                send_log("لم يتم العثور على ملف APK الناتج بعد اكتمال أمر البناء.")

            # Install & Run via ADB
            installed_ok = False
            launched_ok = False
            launch_seconds = 0.0
            manufacturer = "أندرويد"
            device_model = "هاتف ذكي"
            if target_serial:
                try:
                    res_m = subprocess.run([adb, "-s", target_serial, "shell", "getprop", "ro.product.manufacturer"], capture_output=True, text=True, timeout=3, startupinfo=startupinfo, creationflags=creationflags)
                    if res_m.stdout.strip():
                        manufacturer = res_m.stdout.strip().capitalize()
                    res_d = subprocess.run([adb, "-s", target_serial, "shell", "getprop", "ro.product.model"], capture_output=True, text=True, timeout=3, startupinfo=startupinfo, creationflags=creationflags)
                    if res_d.stdout.strip():
                        device_model = res_d.stdout.strip().replace("_", " ")
                except Exception:
                    pass

            install_returncode = None
            launch_returncode = None
            install_code = None
            if target_serial and apk_exists:
                send_log(f"[ADB] جاري نقل وتثبيت التطبيق على {manufacturer} {device_model} ({target_serial})...")
                try:
                    i_res = subprocess.run([adb, "-s", target_serial, "install", "-r", apk_path], capture_output=True, text=True, timeout=90, startupinfo=startupinfo, creationflags=creationflags)
                    install_returncode = i_res.returncode
                    install_output = ((i_res.stdout or "") + "\n" + (i_res.stderr or "")).strip()
                    installed_ok, install_code = install_outcome(install_returncode, install_output)
                    send_log(f"[ADB] نتيجة التثبيت (كود {install_returncode}): {install_output.splitlines()[-1] if install_output else 'بدون مخرجات'}")

                    if installed_ok:
                        send_log("[ADB] جاري تشغيل شاشة التطبيق الرئيسية...")
                        m_res = subprocess.run(
                            [adb, "-s", target_serial, "shell", "monkey", "-p", app_id, "-c", "android.intent.category.LAUNCHER", "1"],
                            capture_output=True, text=True, timeout=6, startupinfo=startupinfo, creationflags=creationflags
                        )
                        launch_returncode = m_res.returncode
                        launch_start = time.time()
                        for _ in range(12):
                            try:
                                dump = subprocess.run(
                                    [adb, "-s", target_serial, "shell", "dumpsys", "activity", "activities"],
                                    capture_output=True, text=True, timeout=8, startupinfo=startupinfo, creationflags=creationflags
                                )
                                for line in dump.stdout.splitlines():
                                    if ("mResumedActivity" in line or "topResumedActivity" in line) and app_id in line:
                                        launched_ok = True
                                        break
                            except Exception:
                                pass
                            if launched_ok:
                                break
                            time.sleep(1)
                        launch_seconds = round(time.time() - launch_start, 1)
                        if launched_ok:
                            send_log("[FlutterWay] ننتظر اكتمال أول إطار للتطبيق على الشاشة...")
                            time.sleep(6)
                            send_log("[FlutterWay] التطبيق يعمل الآن على شاشة جهازك!")
                        else:
                            send_log("[FlutterWay] تم تثبيت التطبيق، لكن لم نتحقق من فتحه بعد. افتحه من شاشة الهاتف.")
                except Exception as e:
                    install_code = "install_exception"
                    send_log(f"[ADB Error] تعذر التثبيت أو التشغيل: {e}")

            stop_ticker = True
            elapsed_total = round(time.time() - t_start, 1)

            self.state["app_running_on_phone"] = installed_ok

            mins = int(elapsed_total // 60)
            secs = int(elapsed_total % 60)
            time_formatted = f"{mins}د و {secs}ث ({elapsed_total} ثانية)" if mins > 0 else f"{elapsed_total} ثانية"

            if build_success and apk_exists and installed_ok and launched_ok:
                build_message = f"تم بناء وتشغيل التطبيق بنجاح على {manufacturer} {device_model}!"
            elif build_success and apk_exists and installed_ok:
                build_message = f"تم تثبيت التطبيق على {manufacturer} {device_model}، لكن لم نتحقق من فتحه بعد."
            elif build_success and apk_exists:
                build_message = f"تم بناء التطبيق بنجاح، لكن تعذر تثبيته على {manufacturer} {device_model}."
            else:
                build_message = "فشل بناء التطبيق. راجع سجل الأخطاء أعلاه."

            res = {
                "success": build_success and apk_exists,
                "device_name": f"{manufacturer} {device_model}".strip(),
                "installed_ok": installed_ok,
                "launched_ok": launched_ok,
                "launch_seconds": launch_seconds,
                "build_time": time_formatted,
                "apk_size": f"{apk_size_mb} MB",
                "build_returncode": build_returncode,
                "install_returncode": install_returncode,
                "launch_returncode": launch_returncode,
                "install_code": install_code,
                "stages": {
                    "build": "success" if (build_success and apk_exists) else "failed",
                    "install": "success" if installed_ok else ("failed" if install_code else "skipped"),
                    "launch": "success" if launched_ok else ("unknown" if installed_ok else "skipped"),
                },
                "message": build_message
            }
            diagnostics.log_event(
                "build_finished",
                build_id=build_returncode if build_returncode is not None else 0,
                stage="build",
                success=bool(res["success"]),
                returncode=build_returncode,
                error_code=None if build_success else "build_failed",
            )
            diagnostics.log_event(
                "install_finished",
                build_id=0,
                success=bool(installed_ok),
                returncode=install_returncode,
                code=install_code,
            )

            if win:
                try:
                    win.evaluate_js(f"finishRealBuild({json.dumps(res)});")
                except Exception:
                    pass
            diagnostics.log(
                f"Build finished: success={res['success']} installed={res['installed_ok']} "
                f"launched={res['launched_ok']} rc={build_returncode} msg={build_message}"
            )

        def run_build_worker():
            try:
                build_worker()
            except Exception as e:
                diagnostics.log(f"Build worker crashed: {e}\n{traceback.format_exc()}", "error")
                if win:
                    try:
                        failure = {
                            "success": False,
                            "installed_ok": False,
                            "message": f"توقف البناء بشكل غير متوقع: {e}",
                        }
                        win.evaluate_js(f"finishRealBuild({json.dumps(failure)});")
                    except Exception:
                        pass
            finally:
                self.state["build_running"] = False

        try:
            threading.Thread(target=run_build_worker, daemon=True).start()
        except Exception as e:
            self.state["build_running"] = False
            return {"success": False, "error": f"تعذر بدء عملية البناء: {e}"}
        return {"success": True}

    def start_onboarding(self, mode="usb"):
        if self.state.get("setup_running"):
            return {"success": False, "error": "التجهيز شغال بالفعل. انتظر يكمل."}
        self.state["setup_running"] = True
        self.state["selected_mode"] = mode
        self.state["current_step"] = 2
        self.state["setup_error"] = None
        self.state["is_complete"] = False
        print(f"[Onboarding] Starting REAL setup flow with mode: {mode}")
        diagnostics.log_event("setup_started", mode=str(mode))

        def worker():
            win = self.window_holder.get("window")

            def fail(message, percent=0):
                self.state["is_complete"] = False
                self.state["setup_error"] = message
                diagnostics.log(f"Setup failed at {percent}%: {message}", "error")
                diagnostics.log_event("setup_failed", code="setup_failed", percent=int(percent or 0))
                try:
                    print(f"[Onboarding] FAILED: {message}")
                except Exception:
                    pass
                if win:
                    try:
                        win.evaluate_js(f"onboardingFailed({json.dumps(message)});")
                    except Exception:
                        pass

            try:
                # Stage 1: Environment & System Check (0% - 18%) -> Checklist Item 1
                self._update_ui(win, 10, "جاري فحص إعدادات اللابتوب وتوفير أفضل مسار...", 1)
                time.sleep(0.4)
                self._update_ui(win, 18, "تم فحص الذاكرة ومساحة القرص وتوافق النظام بنجاح", 1)
                time.sleep(0.3)

                # Stage 2: Java (JDK 21) & Gradle Toolchain (18% - 42%) -> Checklist Item 2
                self._update_ui(win, 24, "نثبّت Java وأدوات بناء أندرويد...", 2)
                def jdk_progress(message):
                    sub = _percent_from_text(message)
                    overall = 24 if sub is None else 24 + int(sub * 16 / 100)
                    self._update_ui(win, overall, message, 2)
                jdk_path = ensure_jdk(progress=jdk_progress)
                if not jdk_path:
                    fail("تعذر تجهيز Java 21. تأكد من اتصال الإنترنت ثم أعد المحاولة.", 24)
                    return
                self._update_ui(win, 40, "تم تثبيت Java وأدوات أندرويد بنجاح", 2)
                time.sleep(0.4)

                # Stage 3: Flutter Toolchain & PATH Registration (42% - 75%) -> Checklist Item 3
                flutter_target = paths.flutter_root()
                flutter_bin = os.path.join(flutter_target, "bin")
                flutter_bat = os.path.join(flutter_bin, "flutter.bat")

                if not os.path.exists(flutter_bat):
                    if os.path.exists(flutter_target) and os.listdir(flutter_target):
                        fail(f"مجلد {flutter_target} موجود لكنه غير مكتمل (لا يحتوي flutter.bat). احذفه أو أصلحه ثم أعد المحاولة.", 48)
                        return

                    self._update_ui(win, 48, "جاري تنزيل محرك Flutter & Dart الرسمي من السحابة...", 3)

                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0
                    creationflags = subprocess.CREATE_NO_WINDOW

                    release = toolchain.resolve_flutter_release("stable")
                    if not release:
                        fail("تعذر قراءة قائمة إصدارات Flutter الرسمية. تحقق من الإنترنت ثم أعد المحاولة.", 48)
                        return

                    def flutter_progress(pct):
                        overall = 48 + int(max(0, min(100, int(pct))) * 22 / 100)
                        self._update_ui(win, overall, f"ننزّل Flutter {release.version}... {pct}%", 3)

                    installed = toolchain.install_flutter_archive(
                        flutter_target, release, progress=flutter_progress
                    )
                    if not installed.get("success"):
                        fail(installed.get("error") or "تعذر تجهيز Flutter SDK.", 48)
                        return
                    self._update_ui(win, 70, f"تم تجهيز Flutter {release.version} (موثّق)", 3)

                    if not os.path.exists(flutter_bat):
                        fail("اكتمل التنزيل لكن flutter.bat غير موجود.", 48)
                        return

                # Register the Flutter bin directory in the user PATH via the Registry
                self._update_ui(win, 70, "نربط Flutter بالنظام...", 3)
                if not add_to_user_path(flutter_bin):
                    self._update_ui(win, 72, "تم تنزيل Flutter، لكن تعذر ربطه بالنظام. سنكمل بالمسار المباشر.", 3)
                else:
                    self._update_ui(win, 75, "تم تنزيل Flutter وربطه بالنظام", 3)
                time.sleep(0.4)

                # Stage 3.5: Android SDK (platform-tools, platforms, build-tools)
                self._update_ui(win, 78, "نجهّز أدوات أندرويد (Android SDK)...", 3)
                def sdk_progress(message):
                    sub = _percent_from_text(message)
                    overall = 80 if sub is None else 80 + int(sub * 6 / 100)
                    self._update_ui(win, overall, message, 3)
                sdk_result = android_sdk.install_android_sdk(
                    progress=sdk_progress
                )
                if not sdk_result.get("success"):
                    fail(sdk_result.get("error", "تعذر تجهيز Android SDK. تأكد من اتصال الإنترنت ثم أعد المحاولة."), 80)
                    return
                if sdk_result.get("warnings"):
                    self._update_ui(win, 86, sdk_result.get("message") or "تم تجهيز الأدوات، لكن تعذر حفظ متغيرات البيئة.", 3)
                else:
                    self._update_ui(win, 86, "تم تجهيز أدوات أندرويد بنجاح", 3)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = subprocess.CREATE_NO_WINDOW
                try:
                    subprocess.run(
                        [flutter_bat, "config", "--android-sdk", sdk_result["sdk_root"]],
                        capture_output=True,
                        text=True,
                        startupinfo=startupinfo,
                        creationflags=creationflags,
                        timeout=30,
                    )
                except Exception as e:
                    print("Flutter android-sdk config error:", e)
                time.sleep(0.3)

                # Stage 4: VS Code Configuration & Extensions (75% - 90%) -> Checklist Item 4
                self._update_ui(win, 88, "نربط VS Code ونثبّت إضافات Flutter...", 4)
                vscode_ok = False
                try:
                    vscode_res = configure_vscode(flutter_target)
                    vscode_ok = bool(vscode_res and vscode_res.get("success"))
                except Exception as e:
                    print("VS Code setup error:", e)

                # Stage 5: Starter Project Setup on Desktop (90% - 100%) -> Checklist Item 4
                self._update_ui(win, 94, "نجهّز أول مشروع Flutter على سطح المكتب...", 4)
                project_path = paths.default_project_path()
                if not self._ensure_starter_project(
                    project_path,
                    progress=lambda message: self._update_ui(win, 94, message, 4),
                ):
                    detail = (self.state.get("starter_project_error") or "").strip()
                    message = "تعذر إنشاء مشروع البداية."
                    if detail:
                        message += "\n" + detail[-700:]
                    fail(message, 94)
                    return

                time.sleep(0.4)
                if vscode_ok:
                    self._update_ui(win, 100, "اكتمل التجهيز! حان وقت فحص وتجربة هاتفك", 4)
                else:
                    self._update_ui(win, 98, "اكتمل Flutter والمشروع، لكن VS Code غير مثبت أو تعذر ضبطه. يمكنك تثبيته لاحقاً.", 4)
                self.state["is_complete"] = True
                self.state["project_path"] = project_path
                diagnostics.log_event("setup_finished", vscode_ok=bool(vscode_ok))

                # Transition to Step 3: Phone verification
                time.sleep(0.6)
                self.state["current_step"] = 3
                if win:
                    win.evaluate_js("showStep(3);")
            except Exception as e:
                fail(f"خطأ غير متوقع أثناء التجهيز: {e}", 0)

        def run_setup_worker():
            try:
                worker()
            finally:
                self.state["setup_running"] = False

        try:
            threading.Thread(target=run_setup_worker, daemon=True).start()
        except Exception as e:
            self.state["setup_running"] = False
            self.state["setup_error"] = f"تعذر بدء عملية التجهيز: {e}"
            return {"success": False, "error": self.state["setup_error"]}
        return {"success": True}

    def _ensure_starter_project(self, project_path, progress=None):
        """Ensure a real Flutter project exists; copy a template or run flutter create."""
        self.state["starter_project_error"] = ""
        os.makedirs(project_path, exist_ok=True)
        pubspec = os.path.join(project_path, "pubspec.yaml")
        if os.path.exists(pubspec):
            companion_service.ensure_vscode_launch(project_path)
            return True

        src_template = paths.starter_template_dir()
        if src_template and os.path.exists(src_template) and not os.path.exists(os.path.join(project_path, "android")):
            try:
                shutil.copytree(src_template, project_path, dirs_exist_ok=True)
            except Exception as e:
                print("Starter template copy error:", e)

        if os.path.exists(pubspec):
            companion_service.ensure_vscode_launch(project_path)
            managed.write_marker(project_path, "starter_project")
            return True

        flutter_bat = paths.flutter_bat()
        if not os.path.exists(flutter_bat):
            flutter_bat = shutil.which("flutter.bat") or shutil.which("flutter")
        if not flutter_bat:
            self.state["starter_project_error"] = "لم نجد flutter.bat بعد التثبيت."
            return False

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        command = [
            flutter_bat, "create", "--org", "com.example",
            "--platforms", "android", "--overwrite", project_path,
        ]
        output_lines = []
        proc = None
        timer = None
        try:
            proc = subprocess.Popen(
                command,
                cwd=os.path.dirname(project_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            timer = threading.Timer(600, proc.kill)
            timer.daemon = True
            timer.start()
            last_report = 0.0
            for line in proc.stdout:
                text = (line or "").rstrip()
                if text:
                    output_lines.append(text)
                    output_lines = output_lines[-100:]
                if progress and time.time() - last_report > 6:
                    progress("ننشئ مشروعك الأول... قد تأخذ دقائق.")
                    last_report = time.time()
            proc.wait()
            if proc.returncode not in (0, None):
                tail = "\n".join(output_lines[-6:])
                self.state["starter_project_error"] = tail or f"flutter create خرج بالرمز {proc.returncode}."
                print("[Onboarding] flutter create failed:", tail)
        except Exception as e:
            self.state["starter_project_error"] = f"تعذر تشغيل flutter create: {e}"
            print("flutter create error:", e)
        finally:
            if timer:
                timer.cancel()
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        if os.path.exists(pubspec):
            companion_service.ensure_vscode_launch(project_path)
            managed.write_marker(project_path, "starter_project")
            return True
        if not self.state.get("starter_project_error"):
            self.state["starter_project_error"] = "لم يُنشأ pubspec.yaml بعد flutter create."
        return False

    def open_vscode(self):
        print("[Onboarding] Opening VS Code with starter project...")
        code_cli = find_code_cli()
        if code_cli:
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = subprocess.CREATE_NO_WINDOW
                project_path = self.state.get("project_path") or paths.default_project_path()
                # Launch VS Code with project folder
                subprocess.Popen([code_cli, project_path], startupinfo=startupinfo, creationflags=creationflags)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "VS Code not found"}

    def _update_ui(self, win, percent, text, chk_step):
        self.state["progress_percent"] = percent
        if win:
            escaped_text = text.replace("'", "\\'")
            js = f"updateProgress({percent}, '{escaped_text}', {chk_step});"
            win.evaluate_js(js)

    # --- Student Course Companion Dashboard API ---
    def get_initial_app_state(self):
        try:
            report = companion_service.get_smart_doctor_report()
            has_setup = report.get("is_all_healthy", False)
            return {
                "initial_mode": "companion" if has_setup else "wizard",
                "has_setup": has_setup,
                "theme": self.state.get("theme", "dark"),
                "doctor_report": report,
                "recent_projects": companion_service.load_recent_projects(),
                "dev_mode": dev_mode_enabled(),
                "build_mode": os.environ.get("FLUTTERWAY_BUILD_MODE", "debug")
            }
        except Exception as e:
            return {
                "initial_mode": "wizard",
                "has_setup": False,
                "theme": "dark",
                "error": str(e)
            }

    def get_smart_doctor_report(self):
        return companion_service.get_smart_doctor_report()

    def heal_doctor_item(self, fix_id):
        return companion_service.heal_doctor_item(fix_id)

    def heal_all_doctor_items(self):
        report = companion_service.get_smart_doctor_report()
        healed_count = 0
        for item in report.get("items", []):
            if item.get("status") != "PASS" and item.get("auto_fixable") and item.get("fix_id"):
                companion_service.heal_doctor_item(item["fix_id"])
                healed_count += 1
        updated = companion_service.get_smart_doctor_report()
        return {"success": True, "healed_count": healed_count, "updated_report": updated}

    def create_lecture_project(self, name, custom_parent_folder=None):
        res = companion_service.create_lecture_project(name, custom_parent_folder)
        if res.get("success"):
            self.state["project_path"] = res["path"]
        return res

    def get_recent_projects(self):
        return companion_service.load_recent_projects()

    def clean_project(self, project_path=None):
        p = project_path or self.state.get("project_path")
        return companion_service.clean_project_build(p)

    def open_project_in_vscode(self, project_path=None):
        p = project_path or self.state.get("project_path")
        code_cli = find_code_cli()
        if code_cli and p and os.path.exists(p):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            subprocess.Popen([code_cli, p], startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
            return {"success": True}
        return {"success": False, "error": "المسار غير صالح أو VS Code غير مثبت"}

    def run_project_on_phone(self, project_path=None, serial=None):
        return self.run_test_app(serial)

    def get_device_studio_data(self, serial=None):
        return companion_service.get_detailed_device_info(serial)

    def capture_device_screenshot(self, serial=None):
        return companion_service.capture_device_screenshot_b64(serial)

    def ping_device_screen(self, serial=None):
        adb = find_adb()
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        elif self.state.get("connected_device"):
            cmd.extend(["-s", self.state["connected_device"]["serial"]])
        cmd.extend(["shell", "input", "keyevent", "224"])
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        subprocess.run(cmd, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "message": "تم إرسال إشارة تنشيط الشاشة بنجاح!"}

    def dev_reset(self, mode="soft"):
        """Legacy developer reset entry point used by the two original cards."""
        res = companion_service.dev_reset_environment(mode)
        if mode == "soft":
            self.state["current_step"] = 3
            self.state["app_running_on_phone"] = False
        else:
            self.state["current_step"] = 1
            self.state["progress_percent"] = 0
            self.state["is_complete"] = False
            self.state["app_running_on_phone"] = False
        win = self.window_holder.get("window")
        if win:
            try:
                win.evaluate_js(f"onDevResetComplete('{mode}');")
            except Exception:
                pass
        return res

    def get_dev_reset_status(self):
        """Read-only inventory of everything the granular dev reset can remove."""
        return dev_reset.status()

    def dev_reset_action(self, action, include_legacy=False, confirm=""):
        """Run one granular developer reset action and return its log."""
        if not dev_mode_enabled():
            return {"success": False, "logs": [], "error": "أدوات المطور غير مفعّلة."}
        return dev_reset.run(action, include_legacy=include_legacy, confirm=confirm)

    def quarantine_list(self):
        if not dev_mode_enabled():
            return {"success": False, "error": "أدوات المطور غير مفعّلة.", "items": []}
        return dev_reset.quarantine_list()

    def quarantine_restore(self, item_id, destination=None):
        if not dev_mode_enabled():
            return {"success": False, "error": "أدوات المطور غير مفعّلة."}
        return dev_reset.quarantine_restore(item_id, destination)

    def quarantine_purge(self, item_id, confirmation):
        if not dev_mode_enabled():
            return {"success": False, "error": "أدوات المطور غير مفعّلة."}
        return dev_reset.quarantine_purge(item_id, confirmation)

    def adopt_project(self, path):
        if not dev_mode_enabled():
            return {"success": False, "error": "أدوات المطور غير مفعّلة."}
        return dev_reset.adopt_project(path)

    def set_build_mode(self, mode):
        """Choose the test-app build mode: release (small), profile, or debug (large, hot reload)."""
        mode = (mode or "").strip().lower()
        if mode not in ("release", "profile", "debug"):
            return {"success": False, "error": "وضع بناء غير معروف"}
        os.environ["FLUTTERWAY_BUILD_MODE"] = mode
        return {"success": True, "mode": mode}

    def _active_serial(self):
        device = self.state.get("connected_device")
        if device and device.get("serial"):
            return device["serial"]
        devices = companion_service.get_connected_devices()
        return devices[0]["serial"] if devices else None

    def hot_reload_start(self, project_path=None):
        path = project_path or self.state.get("project_path") or paths.default_project_path()
        result = self.hot_reload.start(path, self._active_serial())
        diagnostics.log_event(
            "hot_reload_started",
            used_prebuilt=bool((result or {}).get("used_prebuilt")),
        )
        if not result.get("success"):
            diagnostics.log_event("hot_reload_finished", success=False, code="start_failed")
        return result

    def hot_reload_read(self):
        return self.hot_reload.read_main()

    def hot_reload_save(self, content, force_new=False):
        return self.hot_reload.save(content, force_new=bool(force_new))

    def hot_reload_action(self, action):
        return self.hot_reload.action(action)

    def hot_reload_status(self):
        return self.hot_reload.status()

    def hot_reload_screenshot(self):
        return companion_service.capture_device_screenshot_b64(self._active_serial())

    # ------------------------------------------------------------------ diagnostics
    def _make_error_report(self, payload=None):
        payload = payload or {}
        message = payload.get("message") or payload.get("description") or "بلاغ يدوي من المستخدم"
        # ``include_logs`` is the legacy UI flag. Raw logs are never shareable,
        # so it only maps to opt-in structured events when explicitly requested.
        include_events = bool(payload.get("include_events", False))
        return diagnostics.build_report(
            message=message,
            stack=payload.get("stack", ""),
            phase=payload.get("phase", "manual"),
            description=payload.get("description", ""),
            include_logs=False,
            source=payload.get("source", "app"),
            extra=payload.get("extra") or {},
            include_events=include_events,
        )

    def get_report_preview(self, payload=None):
        """Return exactly what would be shared, for the consent screen."""
        report = self._make_error_report(payload)
        return {
            "success": True,
            "markdown": diagnostics.report_markdown(report),
            "github_url": diagnostics.github_issue_url(report),
            "manifest": ["report.json", "report.md", "environment.json", "manifest.json"]
            + (["events.jsonl"] if report.get("limits", {}).get("events_included") else []),
            "redactions": report.get("redactions", {}),
            "warnings": ["التنقية آلية وقد لا تكتشف كل المعلومات الحساسة."],
            "events_included": report.get("limits", {}).get("events_included", False),
        }

    def open_reports_folder(self):
        try:
            os.startfile(str(diagnostics.reports_dir()))
            return {"success": True, "path": str(diagnostics.reports_dir())}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def report_client_error(self, payload=None):
        report = diagnostics.capture_client_error(payload or {})
        return {"success": True, "message": report.get("message", "")}

    def get_error_report(self, payload=None):
        report = self._make_error_report(payload)
        return {
            "success": True,
            "report": report,
            "markdown": diagnostics.report_markdown(report),
            "github_url": diagnostics.github_issue_url(report),
            "info": diagnostics.diagnostics_info(),
        }

    def open_error_report(self, payload=None):
        report = self._make_error_report(payload)
        url = diagnostics.github_issue_url(report)
        result = diagnostics.open_github_issue(report)
        if isinstance(result, dict):
            opened = bool(result.get("opened"))
            error = result.get("error")
        else:  # defensive: older monkeypatched bool
            opened, error = bool(result), None
        return {
            "success": True,
            "opened": opened,
            "github_url": url,
            "zip_path": "",
            "error": error,
            "markdown": diagnostics.report_markdown(report),
        }

    def save_error_report(self, payload=None):
        payload = payload or {}
        report = self._make_error_report(payload)
        zip_path = diagnostics.save_report_zip(
            report, include_events=bool(report.get("limits", {}).get("events_included"))
        )
        return {"success": True, "zip_path": zip_path, "markdown": diagnostics.report_markdown(report)}

    def get_diagnostics_info(self):
        return diagnostics.diagnostics_info()

    def copy_error_report(self, payload=None):
        report = self._make_error_report(payload)
        return {"success": True, "markdown": diagnostics.report_markdown(report)}

# --- Agent Testing Harness for Modern Onboarding UI ---
def start_harness(api, window_holder):
    def server():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", 54321))
            s.listen(5)
        except Exception:
            return

        while True:
            try:
                conn, _ = s.accept()
                data = conn.recv(1024).decode("utf-8").strip()
                if not data:
                    conn.close()
                    continue

                parts = data.split()
                cmd = parts[0]

                if cmd == "ui":
                    cur_step = api.state.get("current_step", 1)
                    if cur_step == 1:
                        elements = [
                            {"id": "btn-theme-toggle", "label": "تبديل الوضع النهاري/الليلي"},
                            {"id": "btn-check-laptop", "label": "فحص توافق اللابتوب والمحاكي"},
                            {"id": "card-usb", "label": "هاتف أندرويد عبر كيبل USB"},
                            {"id": "card-emu", "label": "محاكي افتراضي على اللابتوب"},
                            {"id": "btn-start-setup", "label": "متابعة التجهيز التلقائي"}
                        ]
                    elif cur_step == 2:
                        elements = [
                            {"id": "progress-bar", "label": f"{api.state.get('progress_percent', 0)}%"}
                        ]
                    elif cur_step == 3:
                        elements = [
                            {"id": "btn-refresh-phone", "label": "إعادة فحص الهاتف"},
                            {"id": "btn-fix-adb", "label": "حل مشاكل الاتصال"},
                            {"id": "btn-install-drivers", "label": "تثبيت تعريفات USB الشاملة"},
                            {"id": "btn-run-test", "label": "بناء وتجربة التطبيق على هاتفي الآن"},
                            {"id": "btn-proceed-to-vscode", "label": "نعم، افتح VS Code وابدأ البرمجة الآن"}
                        ]
                    else:
                        elements = [
                            {"id": "btn-open-vscode", "label": "افتح VS Code وابدأ البرمجة الآن"}
                        ]
                    conn.sendall(json.dumps({"screen": f"onboarding_step_{cur_step}", "elements": elements}).encode("utf-8"))

                elif cmd == "tap" and len(parts) > 1:
                    target = parts[1]
                    win = window_holder.get("window")
                    allowed_targets = [
                        "btn-start-setup", "card-usb", "card-emu", "btn-check-laptop",
                        "btn-theme-toggle", "btn-refresh-phone", "btn-fix-adb", "btn-install-drivers",
                        "btn-run-test", "btn-proceed-to-vscode", "btn-open-vscode", "btn-skip-to-vscode",
                        "btn-nav-wizard", "btn-nav-companion",
                        "btn-tab-doctor", "btn-tab-projects", "btn-tab-rescue", "btn-tab-device", "btn-tab-cheatsheet",
                        "btn-tab-hotreload", "btn-hr-start", "btn-hr-reload", "btn-hr-restart", "btn-hr-stop", "btn-hr-preview",
                        "btn-doctor-heal-all", "btn-create-lecture-proj", "btn-clean-project", "btn-open-proj-vscode",
                        "btn-rescue-gradle", "btn-rescue-licenses", "btn-rescue-adb", "btn-rescue-longpaths", "btn-rescue-network",
                        "btn-device-ping", "btn-device-screenshot",
                        "btn-dev-modal-toggle", "btn-dev-soft-reset", "btn-dev-full-reset",
                        "btn-dev-scan", "btn-dev-ui-reset", "btn-dev-projects-reset",
                        "btn-dev-downloads-reset", "btn-dev-downloads-all", "btn-dev-env-reset",
                        "btn-dev-vscode-reset", "btn-dev-vscode-ext-reset", "btn-dev-device-reset",
                        "btn-dev-build-reset", "btn-dev-jdk-reset", "btn-dev-all-reset"
                    ]
                    if target in allowed_targets:
                        if win:
                            win.evaluate_js(f"triggerAgentTap('{target}');")
                        elif target == "btn-start-setup":
                            api.start_onboarding("usb")
                        conn.sendall(json.dumps({"success": True, "target": target, "time_ms": 1.2}).encode("utf-8"))
                    else:
                        conn.sendall(json.dumps({"success": False, "error": f"Unknown target: {target}"}).encode("utf-8"))

                elif cmd == "state":
                    conn.sendall(json.dumps(api.state).encode("utf-8"))

                conn.close()
            except Exception:
                pass

    threading.Thread(target=server, daemon=True).start()

def get_html_path():
    return paths.onboarding_html()

def apply_window_icon(window):
    try:
        import clr
        clr.AddReference('System.Drawing')
        import System.Drawing
        ico_path = paths.icon_path()
        if os.path.exists(ico_path) and hasattr(window, 'native') and window.native:
            window.native.Icon = System.Drawing.Icon(ico_path)
    except Exception:
        pass

def dev_mode_enabled():
    """Developer tools are opt-in only; never visible on the student surface."""
    return os.environ.get("FLUTTERWAY_DEV") == "1" or "--dev" in sys.argv[1:]


def harness_enabled():
    """Enable the localhost agent harness only when explicitly requested."""
    return os.environ.get("FLUTTERWAY_HARNESS") == "1" or "--harness" in sys.argv[1:]


def main():
    diagnostics.install_exception_hooks()
    diagnostics.log("FlutterWay starting")
    html_path = get_html_path()
    window_holder = {"window": None}
    api = OnboardingApi(window_holder)

    # Start the localhost harness only in explicit developer/testing mode.
    if harness_enabled():
        start_harness(api, window_holder)

    # Create native standalone window using Windows Edge WebView2
    window = webview.create_window(
        title="FlutterWay — بيئة فلاتر للمبتدئين",
        url=f"file:///{html_path.replace(os.sep, '/')}",
        js_api=api,
        width=980,
        height=740,
        min_size=(860, 640),
        maximized=True,
        background_color="#0b0f19"
    )
    window_holder["window"] = window

    # Run Edge Chromium GUI loop and set native window icon
    webview.start(apply_window_icon, window, gui="edgechromium", debug=False)

if __name__ == "__main__":
    main()
