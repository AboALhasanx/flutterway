import os
import sys
import json
import time
import socket
import threading
import subprocess
import shutil
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
except ImportError:
    from vscode_integration import get_vscode_status, configure_vscode, find_code_cli
    import companion_service
    import paths
    import android_sdk
    import android_apk
    import dev_reset

def _broadcast_environment_change():
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
    except Exception:
        pass


def set_user_env(name, value):
    """Sets a User environment variable permanently in the Windows Registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            val_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
            winreg.SetValueEx(key, name, 0, val_type, value)
        _broadcast_environment_change()
    except Exception as e:
        print(f"Error setting registry env {name}: {e}")

def add_to_user_path(new_dir):
    """Atomically adds a folder to the User PATH via Windows Registry without duplicates."""
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
                new_val = new_dir + ";" + val
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_val)
        # Also update os.environ for current runtime
        curr = os.environ.get("PATH", "")
        if new_dir.lower() not in curr.lower():
            os.environ["PATH"] = new_dir + ";" + curr
        # Notify open shells/apps that the environment changed.
        _broadcast_environment_change()
        return True
    except Exception as e:
        print(f"Registry PATH update error: {e}")
        return False

def find_adb():
    return paths.adb_path()

def find_jdk():
    return paths.jdk_home()

def ensure_jdk():
    """Locates or silently installs JDK 21, sets JAVA_HOME and GRADLE_USER_HOME, and registers in PATH."""
    jdk = find_jdk()
    if not jdk:
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            subprocess.run(
                ["winget", "install", "EclipseAdoptium.Temurin.21.JDK", "--silent", "--accept-source-agreements", "--accept-package-agreements", "-h"],
                capture_output=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120
            )
            jdk = find_jdk()
        except Exception as e:
            print("Winget JDK install fallback error:", e)

    if jdk:
        gradle_home = paths.gradle_user_home()
        os.environ["JAVA_HOME"] = jdk
        os.environ["GRADLE_USER_HOME"] = gradle_home
        set_user_env("JAVA_HOME", jdk)
        set_user_env("GRADLE_USER_HOME", gradle_home)
        add_to_user_path(os.path.join(jdk, "bin"))
    return jdk

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
            "setup_error": None
        }

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
                reason = "ميزة المحاكاة (Virtualization) غير مفعلة في معالجك (BIOS). خيار (هاتف USB) هو الأسرع والجاهز للعمل معك فوراً وبدون أي تعقيد أو تجميد للحاسبة!"
            elif ram_gb < 8:
                rec_mode = "usb"
                reason = f"الرام المتاح ({ram_gb}GB) خفيف، والمحاكي سيستهلك نصفه. هاتف USB سيبقي لابتوبك سريعاً وبارداً جداً!"
            else:
                rec_mode = "usb"
                reason = f"لابتوبك بمواصفات جيدة ({ram_gb}GB رام). ننصحك بهاتف USB كخيار أسرع بدون استنزاف للموارد، لكن المحاكي ممكن أيضاً."

            return {
                "success": True,
                "ram_gb": ram_gb,
                "free_disk_gb": free_gb,
                "cpu_cores": cpu_cores,
                "vt_enabled": vt_enabled,
                "recommended_mode": rec_mode,
                "reason": reason,
                "emulator_benchmark": {
                    "ram_cost": "4 إلى 6 GB رام محجوزة بالكامل",
                    "cpu_cost": "85% - 100% ضغط مستمر",
                    "heat_fan": "مراوح عالية وحرارة مرتفعة",
                    "bios_status": "معطلة في BIOS" if not vt_enabled else "مفعلة",
                    "verdict": "المحاكي يستنزف لابتوبك جداً ويسبب بطء شديد" if not vt_enabled or ram_gb < 16 else "مقبول لكن ثقيل"
                },
                "usb_benchmark": {
                    "ram_cost": "0 MB من حاسبتك (يستخدم رام الهاتف نفسه!)",
                    "cpu_cost": "0% ضغط معالج أثناء الاستخدام",
                    "heat_fan": "حاسبتك باردة وهادئة تماماً",
                    "fps": "60 إلى 120 FPS بسلاسة شاشة التلفون الحقيقية",
                    "verdict": "الخيار الذهبي والواقعي لـ 95% من الطلاب والمطورين"
                }
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
                        ps_cmd = 'Get-PnpDevice | Where-Object { ($_.FriendlyName -like "*Android*" -or $_.Class -eq "OtherDevices") -and $_.Status -ne "OK" } | Select-Object -ExpandProperty FriendlyName -First 1'
                        pnp_res = subprocess.run(
                            ['powershell', '-NoProfile', '-Command', ps_cmd],
                            capture_output=True, text=True, startupinfo=startupinfo, creationflags=creationflags, timeout=2
                        )
                        out = pnp_res.stdout.strip()
                        if out:
                            missing_driver = True
                            missing_name = out
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
        if serial and apk_path:
            try:
                subprocess.run(
                    [adb, "-s", serial, "install", "-r", apk_path],
                    capture_output=True, startupinfo=startupinfo, creationflags=creationflags, timeout=35
                )
                subprocess.run(
                    [adb, "-s", serial, "shell", "monkey", "-p", app_id, "-c", "android.intent.category.LAUNCHER", "1"],
                    capture_output=True, startupinfo=startupinfo, creationflags=creationflags, timeout=5
                )
                installed_ok = True
            except Exception as e:
                print("App install/launch error:", e)

        self.state["app_running_on_phone"] = installed_ok

        return {
            "success": installed_ok,
            "device_name": f"{manufacturer} {device_name}".strip(),
            "installed_ok": installed_ok,
            "message": (
                f"تم تشغيل التطبيق بنجاح على {manufacturer} {device_name}!"
                if installed_ok else
                "تعذر تثبيت أو تشغيل التطبيق على الهاتف. راجع اتصال USB وسجل الأخطاء."
            )
        }

    def start_real_gradle_build(self, project_path=None, serial=None):
        """Asynchronously runs the REAL Flutter Gradle build on the selected project,
        streaming live logs to the UI console and installing the fresh APK on the connected device."""
        if project_path and os.path.isdir(project_path):
            self.state["project_path"] = project_path
        win = self.window_holder.get("window")

        # Humorous & empathetic progress messages based on elapsed time
        messages = [
            (0, "🚀 شغلنا محركات الجرادل... دا يتعرف على ملفات المشروع وإعدادات أندرويد.", 1),
            (15, "☕ أول بناء دايماً ثقيل: الجرادل كاعد يجمع حزم SDK ومكتبات أندرويد لأول مرة بحياتك!", 2),
            (45, "🔨 شغال على نار هادئة: المعالج دا يترجم كود Dart وكوتلن للغة الآلة الثنائية (ARM64) الخاصة بجهازك.", 2),
            (85, "😅 حاسبتك مو خارقة بس سباعية وكاعدة تقاتل ويا الجرادل! ترا الجرادل ثقيل حتى على أقوى حواسيب العالم، شوية استراحة وميخالف.", 3),
            (125, "⏳ مرحلة الرزم والـ DEX: كاعد يجمع ملفات الكلاسات ويوقع الـ APK النهائي... هانت!", 3),
            (155, "⚡ اللمسات الأخيرة: كاعد يجهز ملف التثبيت المباشر بالكيبل...", 3),
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

            if target_serial and apk_exists:
                send_log(f"[ADB] جاري نقل وتثبيت التطبيق على {manufacturer} {device_model} ({target_serial})...")
                try:
                    i_res = subprocess.run([adb, "-s", target_serial, "install", "-r", apk_path], capture_output=True, text=True, timeout=90, startupinfo=startupinfo, creationflags=creationflags)
                    send_log(f"[ADB] نتيجة التثبيت: {i_res.stdout.strip() or 'Success'}")

                    send_log(f"[ADB] جاري تشغيل شاشة التطبيق الرئيسية...")
                    subprocess.run(
                        [adb, "-s", target_serial, "shell", "monkey", "-p", app_id, "-c", "android.intent.category.LAUNCHER", "1"],
                        capture_output=True, text=True, timeout=6, startupinfo=startupinfo, creationflags=creationflags
                    )
                    installed_ok = True
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
                "message": build_message
            }

            if win:
                try:
                    win.evaluate_js(f"finishRealBuild({json.dumps(res)});")
                except Exception:
                    pass

        threading.Thread(target=build_worker, daemon=True).start()
        return {"success": True}

    def start_onboarding(self, mode="usb"):
        self.state["selected_mode"] = mode
        self.state["current_step"] = 2
        self.state["setup_error"] = None
        self.state["is_complete"] = False
        print(f"[Onboarding] Starting REAL setup flow with mode: {mode}")

        def worker():
            win = self.window_holder.get("window")

            def fail(message, percent=0):
                self.state["is_complete"] = False
                self.state["setup_error"] = message
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
                self._update_ui(win, 24, "جاري تهيئة بيئة Java ومحرك بناء أندرويد Gradle...", 2)
                jdk_path = ensure_jdk()
                if not jdk_path:
                    fail("تعذر تثبيت JDK 21. تأكد من اتصال الإنترنت أو ثبّت Microsoft OpenJDK 21 يدوياً ثم أعد المحاولة.", 24)
                    return
                self._update_ui(win, 40, "تم تهيئة بيئة Java (JDK 21) ومحرك Gradle بنجاح", 2)
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

                    cmd = ["git", "clone", "--depth", "1", "-b", "stable", "https://github.com/flutter/flutter.git", flutter_target]
                    try:
                        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, startupinfo=startupinfo, creationflags=creationflags)
                        while True:
                            line = proc.stdout.readline()
                            if not line and proc.poll() is not None:
                                break
                            if "Receiving objects:" in line:
                                try:
                                    part = line.split("Receiving objects:")[1].split("%")[0].strip()
                                    p_val = int(part)
                                    scaled = 48 + int(p_val * 0.22)
                                    self._update_ui(win, scaled, f"جاري تنزيل وتجهيز محرك فلاتر ({p_val}%)...", 3)
                                except Exception:
                                    pass
                        proc.wait()
                    except Exception as e:
                        print("Git clone error:", e)

                    if not os.path.exists(flutter_bat):
                        fail("تعذر تنزيل Flutter SDK. تأكد من اتصال الإنترنت ووجود Git، ثم أعد المحاولة.", 48)
                        return

                # Register the Flutter bin directory in the user PATH via the Registry
                self._update_ui(win, 70, "جاري تسجيل مسار فلاتر في بيئة النظام (PATH)...", 3)
                if not add_to_user_path(flutter_bin):
                    self._update_ui(win, 72, "تم تنزيل Flutter، لكن تعذر تسجيله في PATH. سنكمل بالمسار المباشر.", 3)
                else:
                    self._update_ui(win, 75, "تم اكتمال تنزيل وتسجيل محرك فلاتر بنجاح", 3)
                time.sleep(0.4)

                # Stage 3.5: Android SDK (platform-tools, platforms, build-tools)
                self._update_ui(win, 78, "جاري تجهيز Android SDK وأدوات adb...", 3)
                sdk_result = android_sdk.install_android_sdk(
                    progress=lambda message: self._update_ui(win, 80, message, 3)
                )
                if not sdk_result.get("success"):
                    fail(sdk_result.get("error", "تعذر تجهيز Android SDK. تأكد من اتصال الإنترنت ثم أعد المحاولة."), 80)
                    return
                self._update_ui(win, 86, "تم تجهيز Android SDK وأدوات adb بنجاح", 3)
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
                self._update_ui(win, 88, "جاري ربط محرر VS Code وتثبيت إضافات فلاتر...", 4)
                vscode_ok = False
                try:
                    vscode_res = configure_vscode(flutter_target)
                    vscode_ok = bool(vscode_res and vscode_res.get("success"))
                except Exception as e:
                    print("VS Code setup error:", e)

                # Stage 5: Starter Project Setup on Desktop (90% - 100%) -> Checklist Item 4
                self._update_ui(win, 94, "جاري تجهيز أول مشروع فلاتر حقيقي على الديسكتوب...", 4)
                project_path = paths.default_project_path()
                if not self._ensure_starter_project(project_path):
                    fail("تم تثبيت Flutter لكن تعذر إنشاء مشروع البداية. راجع سجل الأخطاء ثم أعد المحاولة.", 92)
                    return

                time.sleep(0.4)
                if vscode_ok:
                    self._update_ui(win, 100, "اكتمل التجهيز! حان وقت فحص وتجربة هاتفك", 4)
                else:
                    self._update_ui(win, 98, "اكتمل Flutter والمشروع، لكن VS Code غير مثبت أو تعذر ضبطه. يمكنك تثبيته لاحقاً.", 4)
                self.state["is_complete"] = True
                self.state["project_path"] = project_path

                # Transition to Step 3: Phone verification
                time.sleep(0.6)
                self.state["current_step"] = 3
                if win:
                    win.evaluate_js("showStep(3);")
            except Exception as e:
                fail(f"خطأ غير متوقع أثناء التجهيز: {e}", 0)

        threading.Thread(target=worker, daemon=True).start()
        return {"success": True}

    def _ensure_starter_project(self, project_path):
        """Ensure a real Flutter project exists; copy a template or run flutter create."""
        os.makedirs(project_path, exist_ok=True)
        pubspec = os.path.join(project_path, "pubspec.yaml")
        if os.path.exists(pubspec):
            return True

        src_template = paths.starter_template_dir()
        if src_template and os.path.exists(src_template) and not os.path.exists(os.path.join(project_path, "android")):
            try:
                shutil.copytree(src_template, project_path, dirs_exist_ok=True)
            except Exception as e:
                print("Starter template copy error:", e)

        if os.path.exists(pubspec):
            return True

        flutter_bat = paths.flutter_bat()
        if not os.path.exists(flutter_bat):
            flutter_bat = shutil.which("flutter.bat") or shutil.which("flutter")
        if not flutter_bat:
            return False

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        try:
            subprocess.run(
                [flutter_bat, "create", "--org", "com.example", "--platforms", "android", "--overwrite", project_path],
                cwd=os.path.dirname(project_path),
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=240,
            )
        except Exception as e:
            print("flutter create error:", e)
        return os.path.exists(pubspec)

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
        return dev_reset.run(action, include_legacy=include_legacy, confirm=confirm)

    def set_build_mode(self, mode):
        """Choose the test-app build mode: release (small), profile, or debug (large, hot reload)."""
        mode = (mode or "").strip().lower()
        if mode not in ("release", "profile", "debug"):
            return {"success": False, "error": "وضع بناء غير معروف"}
        os.environ["FLUTTERWAY_BUILD_MODE"] = mode
        return {"success": True, "mode": mode}

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
    """Developer tools are visible in source runs and in packaged runs launched with --dev."""
    return (
        not getattr(sys, "frozen", False)
        or os.environ.get("FLUTTERWAY_DEV") == "1"
        or "--dev" in sys.argv[1:]
    )


def harness_enabled():
    """Enable the localhost agent harness only when explicitly requested."""
    return os.environ.get("FLUTTERWAY_HARNESS") == "1" or "--harness" in sys.argv[1:]


def main():
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
        background_color="#0b0f19"
    )
    window_holder["window"] = window

    # Run Edge Chromium GUI loop and set native window icon
    webview.start(apply_window_icon, window, gui="edgechromium", debug=False)

if __name__ == "__main__":
    main()
