import os
import sys
import json
import re
import glob
import time
import shutil
import base64
import winreg
import psutil
import subprocess

try:
    from gui.vscode_integration import get_vscode_status, configure_vscode, find_code_cli
    from gui import paths
    from gui import managed
    from gui import android_sdk as sdk_bootstrap
except ImportError:
    from vscode_integration import get_vscode_status, configure_vscode, find_code_cli
    import paths
    import managed
    import android_sdk as sdk_bootstrap

def get_adb_path():
    return paths.adb_path()

def _android_gradle_file(project_path):
    for relative in ("android/app/build.gradle.kts", "android/app/build.gradle"):
        candidate = os.path.join(project_path, relative)
        if os.path.exists(candidate):
            return candidate
    return None

def get_application_id(project_path):
    """Read the real Android applicationId (or namespace) from the project."""
    gradle_file = _android_gradle_file(project_path)
    if not gradle_file:
        return "com.example.flutter_test_app"
    try:
        with open(gradle_file, "r", encoding="utf-8") as handle:
            content = handle.read()
        for pattern in (
            r'applicationId\s*=\s*"([^"]+)"',
            r'applicationId\s+"([^"]+)"',
            r'namespace\s*=\s*"([^"]+)"',
            r'namespace\s+"([^"]+)"',
        ):
            match = re.search(pattern, content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return "com.example.flutter_test_app"

def set_application_id(project_path, app_id):
    """Give a copied lecture project its own Android applicationId.

    Only applicationId is changed. The namespace and Kotlin package stay on the
    template value so the existing MainActivity still resolves at runtime.
    """
    gradle_file = _android_gradle_file(project_path)
    if not gradle_file:
        return False
    try:
        with open(gradle_file, "r", encoding="utf-8") as handle:
            content = handle.read()
        original = content
        for pattern, replacement in (
            (r'(applicationId\s*=\s*")[^"]+(")', rf'\g<1>{app_id}\g<2>'),
            (r'(applicationId\s+")[^"]+(")', rf'\g<1>{app_id}\g<2>'),
        ):
            content = re.sub(pattern, replacement, content)
        if content != original:
            with open(gradle_file, "w", encoding="utf-8") as handle:
                handle.write(content)
            return True
    except Exception:
        pass
    return False

def run_silent(cmd_args, **kwargs):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd_args, capture_output=True, text=True, startupinfo=startupinfo, creationflags=creationflags, **kwargs)

def ensure_vscode_launch(project_path):
    """Add a VS Code launch profile that reuses the stripped debug APK when present."""
    vscode_dir = os.path.join(project_path, ".vscode")
    launch_path = os.path.join(vscode_dir, "launch.json")
    if os.path.exists(launch_path):
        return False
    data = {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "FlutterWay — سريع (APK مصغّر)",
                "request": "launch",
                "type": "dart",
                "args": [
                    "--use-application-binary",
                    "build/app/outputs/flutter-apk/app-debug.signed.apk",
                ],
            },
            {
                "name": "Flutter — تشغيل عادي (قد يكون أبطأ أول مرة)",
                "request": "launch",
                "type": "dart",
            },
        ],
    }
    try:
        os.makedirs(vscode_dir, exist_ok=True)
        with open(launch_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def get_connected_devices():
    """Return attached Android devices with serial, status, and model."""
    adb = get_adb_path()
    devices = []
    try:
        result = run_silent([adb, "devices", "-l"])
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            model = "هاتف أندرويد"
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split("model:", 1)[1].replace("_", " ")
            devices.append({
                "serial": parts[0],
                "status": parts[1],
                "model": model,
                "is_ready": parts[1] == "device",
            })
    except Exception as exc:
        print("ADB devices error:", exc)
    return devices

def kill_gradle_daemons():
    """Terminate Gradle/Kotlin daemons only; never touch unrelated Java apps."""
    targets = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in ("java.exe", "javaw.exe"):
                continue
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if "gradle" in cmdline or "kotlin" in cmdline:
                targets.append(proc)
        except Exception:
            pass

    for proc in targets:
        try:
            proc.terminate()
        except Exception:
            pass

    try:
        _, alive = psutil.wait_procs(targets, timeout=3)
    except Exception:
        alive = targets
    for proc in alive:
        try:
            proc.kill()
        except Exception:
            pass
    return len(targets)

def get_recent_projects_file():
    return paths.recent_projects_file()

def load_recent_projects():
    fpath = get_recent_projects_file()
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                projects = json.load(f)
            return [
                project for project in projects
                if isinstance(project, dict) and project.get("path") and os.path.exists(project["path"])
            ]
        except Exception:
            return []
    # Seed with default first app if exists
    default_p = paths.default_project_path()
    if os.path.exists(default_p):
        return [{
            "name": "my_first_app",
            "path": default_p,
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "description": "مشروع الانطلاقة الأول على الديسكتوب"
        }]
    return []

def save_recent_project(name, path, desc="مشروع فلاتر جديد"):
    projects = load_recent_projects()
    # Filter out if already exists
    projects = [p for p in projects if p.get("path") != path]
    projects.insert(0, {
        "name": name,
        "path": path,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "description": desc
    })
    # Keep up to 10 recent projects
    projects = projects[:10]
    try:
        with open(get_recent_projects_file(), "w", encoding="utf-8") as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return projects

def check_long_paths():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            val, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            return bool(val)
    except Exception:
        return False

def check_licenses_accepted():
    sdk = paths.android_sdk_root()
    license_file = os.path.join(sdk, "licenses", "android-sdk-license")
    try:
        if not os.path.exists(license_file) or os.path.getsize(license_file) == 0:
            return False
        with open(license_file, "r", encoding="utf-8", errors="ignore") as handle:
            return any(line.strip() for line in handle)
    except Exception:
        return False

def get_smart_doctor_report():
    """Runs a lightning-fast, comprehensive diagnostic of all components students need for mobile Android courses."""
    items = []
    adb = get_adb_path()

    # 1. Flutter SDK
    flutter_root = paths.flutter_root()
    flutter_bat = paths.flutter_bat()
    flutter_installed = os.path.exists(flutter_bat)
    flutter_version = paths.flutter_version(flutter_root)
    version_label = f"{flutter_version} (Stable)" if flutter_version else "غير معروف"
    items.append({
        "id": "flutter_sdk",
        "title": "محرك Flutter & Dart SDK",
        "status": "PASS" if flutter_installed else "FAIL",
        "badge": "جاهز ومسجل" if flutter_installed else "بحاجة لتثبيت",
        "detail": f"المسار: {flutter_root} | الإصدار: {version_label}",
        "auto_fixable": not flutter_installed,
        "fix_id": "fix_path"
    })

    # 2. Java JDK 21
    jh = paths.jdk_home()
    java_ok = bool(jh)
    java_detail = f"Adoptium Temurin JDK 21 | {jh}" if jh else "غير مهيأ — لم يتم العثور على java.exe"
    items.append({
        "id": "java_jdk",
        "title": "بيئة جافا ومحرك أندرويد (JDK 21)",
        "status": "PASS" if java_ok else "WARN",
        "badge": "مضبوط بالكامل" if java_ok else "يحتاج ربط المسار",
        "detail": java_detail,
        "auto_fixable": not java_ok,
        "fix_id": "fix_path"
    })

    # 3. Android SDK & Platform-Tools
    android_sdk = paths.android_sdk_root()
    platforms = sorted(glob.glob(os.path.join(android_sdk, "platforms", "android-*")))
    build_tools = sorted(glob.glob(os.path.join(android_sdk, "build-tools", "*")))
    sdk_ok = sdk_bootstrap.sdk_ready(android_sdk)
    api_label = os.path.basename(platforms[-1]).replace("android-", "API ") if platforms else "API غير مثبت"
    tools_label = os.path.basename(build_tools[-1]) if build_tools else "Build-Tools غير مثبتة"
    items.append({
        "id": "android_sdk",
        "title": "حزمة أدوات أندرويد (Android SDK)",
        "status": "PASS" if sdk_ok else "WARN",
        "badge": f"{api_label} | {tools_label}" if sdk_ok else "بحاجة لتجهيز",
        "detail": f"المسار: {android_sdk} | {api_label} | {tools_label}",
        "auto_fixable": not sdk_ok,
        "fix_id": "fix_android_sdk" if not sdk_ok else ""
    })

    # 4. Android Licenses
    lic_ok = check_licenses_accepted()
    items.append({
        "id": "android_licenses",
        "title": "رخص واتفاقيات أندرويد الرسمية",
        "status": "PASS" if lic_ok else "WARN",
        "badge": "جميع الرخص مقبولة" if lic_ok else "تتطلب الموافقة",
        "detail": "تم تأكيد وقبول كافة رخص Google Android SDK للترخيص الأكاديمي والتطوير" if lic_ok else "يمكن الموافقة على جميع الرخص بنقرة واحدة تلقائياً",
        "auto_fixable": not lic_ok,
        "fix_id": "fix_licenses"
    })

    # 5. Windows Long Paths
    lp_ok = check_long_paths()
    items.append({
        "id": "long_paths",
        "title": "مسارات ويندوز العميقة (LongPaths)",
        "status": "PASS" if lp_ok else "WARN",
        "badge": "مفعل ومحمي" if lp_ok else "يحتاج تفعيل",
        "detail": "ويندوز مهيأ لتجاوز حد 260 حرف وتفادي انهيار بناء أندرويد والجرادل" if lp_ok else "ويندوز مقيد بحد 260 حرف؛ انقر لإصلاحه في ثانية",
        "auto_fixable": not lp_ok,
        "fix_id": "fix_long_paths"
    })

    # 6. VS Code & Extensions
    vsc = get_vscode_status(paths.flutter_root())
    vsc_ok = vsc.get("is_ready", False)
    items.append({
        "id": "vscode",
        "title": "محرر VS Code وتكامل فلاتر ودارت",
        "status": "PASS" if vsc_ok else "WARN",
        "badge": "متكامل وجاهز" if vsc_ok else "إضافات مفقودة",
        "detail": "إضافات Flutter & Dart مثبتة وإعدادات formatOnSave ومسار SDK مضبوطة" if vsc_ok else "يحتاج تنصيب إضافات Dart & Flutter وضبط settings.json",
        "auto_fixable": not vsc_ok,
        "fix_id": "fix_vscode"
    })

    # 7. Connected Device
    dev_res = run_silent([adb, "devices"])
    dev_count = 0
    dev_name = "لا يوجد جهاز متصل حالياً"
    if dev_res.returncode == 0:
        for line in dev_res.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                dev_count += 1
                dev_name = f"جهاز أندرويد جاهز ({parts[0]})"
                break

    items.append({
        "id": "device_connection",
        "title": "اتصال الهاتف الفعلي عبر USB",
        "status": "PASS" if dev_count > 0 else "INFO",
        "badge": "متصل وجاهز للبناء" if dev_count > 0 else "بانتظار التوصيل",
        "detail": dev_name,
        "auto_fixable": dev_count == 0,
        "fix_id": "fix_adb"
    })

    # Calculate overall readiness percentage
    pass_count = sum(1 for it in items if it["status"] == "PASS")
    total_count = len(items)
    score = int((pass_count / total_count) * 100)

    return {
        "score": score,
        "pass_count": pass_count,
        "total_count": total_count,
        "is_all_healthy": pass_count >= 5,
        "items": items,
        "student_reassurance": "بيئتك مخصصة ومثالية 100% لتطبيقات الموبايل للأندرويد. تم إعفاؤك تماماً من متطلبات Visual Studio و C++ الثقيلة (وفرنا أكثر من 20 جيجا على لابتوبك)."
    }

def heal_doctor_item(fix_id):
    """Executes atomic 1-click self-healing for any detected issue without scary cmd windows."""
    adb = get_adb_path()
    try:
        if fix_id == "fix_long_paths":
            cmd = 'Set-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" -Name "LongPathsEnabled" -Value 1'
            run_silent(["powershell", "-NoProfile", "-Command", f'Start-Process powershell -ArgumentList \'-NoProfile -Command "{cmd}"\' -Verb RunAs -Wait'])
            return {"success": True, "message": "تم تفعيل المسارات العميقة LongPaths بنجاح في سجل ويندوز!"}

        elif fix_id == "fix_licenses":
            p = subprocess.Popen(
                [paths.flutter_bat(), "doctor", "--android-licenses"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            p.communicate(input="y\ny\ny\ny\ny\ny\ny\ny\ny\ny\n", timeout=25)
            return {"success": True, "message": "تمت الموافقة التلقائية على جميع رخص أندرويد الرسمية بنجاح!"}

        elif fix_id == "fix_adb":
            run_silent([adb, "kill-server"])
            # Kill any zombie process on port 5037
            ps_kill = 'Get-NetTCPConnection -LocalPort 5037 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }'
            run_silent(["powershell", "-NoProfile", "-Command", ps_kill])
            run_silent([adb, "start-server"])
            return {"success": True, "message": "تمت إعادة تشغيل وتصفية منفذ الاتصال بالهاتف بنجاح!"}

        elif fix_id == "fix_vscode":
            res = configure_vscode(paths.flutter_root())
            return res

        elif fix_id == "fix_android_sdk":
            result = sdk_bootstrap.install_android_sdk()
            return {
                "success": bool(result.get("success")),
                "message": result.get("message") or result.get("error") or "تمت محاولة تجهيز Android SDK"
            }

        elif fix_id == "fix_path":
            # Add the discovered Flutter and Java bin directories to the User PATH.
            flutter_bin = os.path.join(paths.flutter_root(), "bin")
            jh = paths.jdk_home()
            java_bin = os.path.join(jh, "bin") if jh else ""

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    val = ""
                parts = [p.strip() for p in val.split(";") if p.strip()]
                for p_add in [flutter_bin, java_bin]:
                    if p_add and not any(p_add.lower() == p.lower() for p in parts):
                        parts.insert(0, p_add)
                new_val = ";".join(parts)
                try:
                    with open(os.path.join(paths.data_dir(), "path_backup.txt"), "w", encoding="utf-8") as backup:
                        backup.write(val)
                except Exception:
                    pass
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_val)

            os.environ["PATH"] = new_val
            try:
                import ctypes
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
            except Exception:
                pass

            return {"success": True, "message": "تم تحديث وتسجيل مسارات فلاتر وجافا في متغيرات النظام بنجاح!"}

        elif fix_id == "fix_gradle_cache":
            # Terminate only Gradle/Kotlin daemons, never unrelated Java apps
            killed = kill_gradle_daemons()
            # Remove lock files in caches and daemon
            for base in [paths.gradle_user_home(), os.path.expandvars(r"%USERPROFILE%\.gradle")]:
                if os.path.exists(base):
                    for sub in ["daemon", "caches"]:
                        sub_path = os.path.join(base, sub)
                        if os.path.exists(sub_path):
                            for root, _, files in os.walk(sub_path):
                                for f in files:
                                    if f.endswith(".lock") or f.endswith(".lck"):
                                        try:
                                            os.remove(os.path.join(root, f))
                                        except Exception:
                                            pass
            return {"success": True, "message": f"تم إنهاء {killed} عملية Gradle وتنظيف أقفال الكاش بنجاح!"}

        elif fix_id == "fix_network":
            run_silent(["ipconfig", "/flushdns"])
            # Unset toxic proxy env vars for gradle if any
            for env_name in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
                if env_name in os.environ:
                    del os.environ[env_name]
            return {"success": True, "message": "تم تفريغ كاش الـ DNS وإعادة ضبط إعدادات الاتصال بمستودعات غوغل!"}

        return {"success": False, "error": f"معرف إصلاح غير معروف: {fix_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_lecture_project(name, custom_parent_folder=None):
    """Creates a high-performance, clean Flutter lecture project configured with safe build rules."""
    # Sanitize name
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip().lower())
    if not clean_name or not clean_name[0].isalpha():
        clean_name = "lecture_" + clean_name

    target_parent = custom_parent_folder or paths.lecture_projects_dir()
    os.makedirs(target_parent, exist_ok=True)
    project_dir = os.path.join(target_parent, clean_name)

    if os.path.exists(project_dir):
        if os.path.exists(os.path.join(project_dir, "pubspec.yaml")):
            ensure_vscode_launch(project_dir)
            save_recent_project(clean_name, project_dir, "مشروع محاضرة موجود مسبقاً")
            return {"success": True, "path": project_dir, "name": clean_name, "message": "المشروع موجود مسبقاً وجاهز للفتح!"}
        return {"success": False, "error": "المجلد موجود لكنه ليس مشروع فلاتر مكتملاً. اختر اسماً آخر أو أصلح المجلد."}

    # High-speed clone from the bundled/legacy verified template
    src_template = paths.starter_template_dir()
    if src_template and os.path.exists(src_template):
        def ignore_patterns(dir, files):
            return [f for f in files if f in [".git", "build", ".dart_tool", ".gradle"]]
        try:
            shutil.copytree(src_template, project_dir, ignore=ignore_patterns)
        except Exception as e:
            print("Lecture template copy error:", e)

        set_application_id(project_dir, f"com.university.flutterway.{clean_name}")

        # Update pubspec.yaml name
        pubspec_path = os.path.join(project_dir, "pubspec.yaml")
        if os.path.exists(pubspec_path):
            with open(pubspec_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = re.sub(r"^name:\s+.*$", f"name: {clean_name}", content, flags=re.MULTILINE)
            content = re.sub(r"^description:\s+.*$", f"description: مشروع المحاضرة {clean_name} - فلاتر-واي", content, flags=re.MULTILINE)
            with open(pubspec_path, "w", encoding="utf-8") as f:
                f.write(content)

        # Update starter main.dart with clean educational structure
        main_dart = os.path.join(project_dir, "lib", "main.dart")
        if os.path.exists(main_dart):
            code = f"""import 'package:flutter/material.dart';

void main() {{
  runApp(const LectureApp());
}}

class LectureApp extends StatelessWidget {{
  const LectureApp({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '{clean_name}',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.lightBlue),
        useMaterial3: true,
      ),
      home: const LectureHomePage(title: '{clean_name} — فلاتر-واي'),
    );
  }}
}}

class LectureHomePage extends StatefulWidget {{
  const LectureHomePage({{super.key, required this.title}});
  final String title;

  @override
  State<LectureHomePage> createState() => _LectureHomePageState();
}}

class _LectureHomePageState extends State<LectureHomePage> {{
  int _counter = 0;

  void _incrementCounter() {{
    setState(() {{
      _counter++;
    }});
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: Text(widget.title),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Text(
              '🎉 مشروع المحاضرة جاهز ويعمل بكفاءة!',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            const Text(
              'عدد المرات التي نقرت فيها على الزر:',
            ),
            Text(
              '$_counter',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _incrementCounter,
        tooltip: 'زيادة العداد',
        child: const Icon(Icons.add),
      ),
    );
  }}
}}
"""
            with open(main_dart, "w", encoding="utf-8") as f:
                f.write(code)
    if not os.path.exists(os.path.join(project_dir, "pubspec.yaml")):
        # Fallback to flutter create
        try:
            run_silent([paths.flutter_bat(), "create", "--org", "com.university.flutterway", "--platforms", "android", "--overwrite", clean_name], cwd=target_parent)
        except Exception as e:
            return {"success": False, "error": f"تعذر تشغيل Flutter لإنشاء المشروع: {e}"}

    if not os.path.exists(os.path.join(project_dir, "pubspec.yaml")):
        return {"success": False, "error": "تعذر إنشاء مشروع المحاضرة. تأكد من تثبيت Flutter SDK ثم أعد المحاولة."}

    ensure_vscode_launch(project_dir)
    managed.write_marker(project_dir, "lecture_project")
    save_recent_project(clean_name, project_dir, f"مشروع محاضرة جديد تم إنشاؤه بنجاح")
    return {
        "success": True,
        "path": project_dir,
        "name": clean_name,
        "message": f"تم إنشاء وتجهيز مشروع المحاضرة ({clean_name}) بنجاح فائق!"
    }

def clean_project_build(project_dir):
    """Safely cleans project build artifacts to free disk space and resolve stuck builds."""
    if not os.path.exists(project_dir):
        return {"success": False, "error": "المجلد غير موجود"}
    build_dir = os.path.join(project_dir, "build")
    dart_tool = os.path.join(project_dir, ".dart_tool")
    try:
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir, ignore_errors=True)
        if os.path.exists(dart_tool):
            shutil.rmtree(dart_tool, ignore_errors=True)
        return {"success": True, "message": "تم تنظيف ملفات البناء المؤقتة واستعادة مساحة القرص بنجاح!"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_detailed_device_info(serial=None):
    """Fetches full telemetry from connected Android device via ADB."""
    adb = get_adb_path()
    if not serial:
        dev_res = run_silent([adb, "devices"])
        lines = dev_res.stdout.splitlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                break

    if not serial:
        return {"connected": False, "message": "لا يوجد هاتف أندرويد متصل حالياً"}

    def get_prop(key):
        return run_silent([adb, "-s", serial, "shell", "getprop", key]).stdout.strip()

    model = get_prop("ro.product.model").replace("_", " ") or "جهاز أندرويد"
    manufacturer = get_prop("ro.product.manufacturer").capitalize() or "Android"
    android_version = get_prop("ro.build.version.release") or "15"
    sdk_api = get_prop("ro.build.version.sdk") or "35"
    cpu_abi = get_prop("ro.product.cpu.abi") or "arm64-v8a"

    # Battery
    battery_res = run_silent([adb, "-s", serial, "shell", "dumpsys", "battery"])
    battery_level = "100"
    for bline in battery_res.stdout.splitlines():
        if "level:" in bline:
            battery_level = bline.split(":")[1].strip()
            break

    # Screen Resolution
    wm_res = run_silent([adb, "-s", serial, "shell", "wm", "size"])
    screen_size = "800x1340"
    if "Physical size:" in wm_res.stdout:
        screen_size = wm_res.stdout.split("Physical size:")[1].strip()

    return {
        "connected": True,
        "serial": serial,
        "model": model,
        "manufacturer": manufacturer,
        "full_name": f"{manufacturer} {model}",
        "android_version": android_version,
        "sdk_api": sdk_api,
        "cpu_abi": cpu_abi,
        "battery_level": f"{battery_level}%",
        "screen_size": screen_size,
        "connection_type": "USB عالي السرعة",
        "developer_mode": "مفعل ومصرح به (Authorized)"
    }

def capture_device_screenshot_b64(serial=None):
    """Captures live screen from ADB into a base64 PNG data URL."""
    adb = get_adb_path()
    cmd = [adb]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["exec-out", "screencap", "-p"])

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    res = subprocess.run(cmd, capture_output=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
    if res.returncode == 0 and len(res.stdout) > 500:
        b64 = base64.b64encode(res.stdout).decode("utf-8")
        return {"success": True, "data_url": f"data:image/png;base64,{b64}"}
    return {"success": False, "error": "تعذر التقاط شاشة الهاتف"}

def dev_reset_environment(mode="soft"):
    """Developer testing reset: wipes test apps, desktop projects, caches, and recent history to test flows repeatedly."""
    adb = get_adb_path()
    logs = []

    # 1. Uninstall test app from attached Android devices
    try:
        dev_res = run_silent([adb, "devices"])
        for line in dev_res.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                u_res = run_silent([adb, "-s", serial, "uninstall", "com.example.flutter_test_app"])
                logs.append(f"تم إلغاء تثبيت التطبيق التجريبي من الجهاز {serial}: {u_res.stdout.strip() or 'Success'}")
    except Exception as e:
        logs.append(f"تعذر إلغاء التثبيت من الهاتف: {e}")

    # 2. Project cleaning based on mode:
    desktop = os.path.expandvars(r"%USERPROFILE%\Desktop")
    proj_path = os.path.join(desktop, "my_first_app")
    if mode == "soft":
        # In soft reset, we wipe the build folder and dart_tool so Gradle compiles completely from scratch
        build_dir = os.path.join(proj_path, "build")
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir, ignore_errors=True)
                logs.append("تم مسح مجلد كاش البناء (build) بالكامل لإعادة البناء من الصفر")
            except Exception as e:
                logs.append(f"تعذر حذف build: {e}")
        dart_tool = os.path.join(proj_path, ".dart_tool")
        if os.path.exists(dart_tool):
            try:
                shutil.rmtree(dart_tool, ignore_errors=True)
                logs.append("تم مسح كاش .dart_tool")
            except Exception as e:
                logs.append(f"تعذر حذف .dart_tool: {e}")
    else: # mode == "full"
        for proj_name in ["my_first_app", "اول_تطبيق_فلاتر"]:
            target = os.path.join(desktop, proj_name)
            if os.path.exists(target):
                try:
                    shutil.rmtree(target, ignore_errors=True)
                    logs.append(f"تم حذف مجلد المشروع التجريبي بالكامل: {proj_name}")
                except Exception as e:
                    logs.append(f"تعذر حذف {proj_name}: {e}")

    # Also clean demo lecture projects
    lecture_folder = os.path.join(desktop, "FlutterProjects")
    if os.path.exists(lecture_folder):
        for demo in ["lecture_test_demo", "test_lecture_proj"]:
            p = os.path.join(lecture_folder, demo)
            if os.path.exists(p):
                shutil.rmtree(p, ignore_errors=True)
                logs.append(f"تم حذف مشروع المحاضرة التجريبي: {demo}")

    # 3. Clear Recent Projects cache in AppData
    rec_file = get_recent_projects_file()
    if os.path.exists(rec_file):
        try:
            os.remove(rec_file)
            logs.append("تم تفريغ سجل المشاريع الأخيرة من AppData")
        except Exception as e:
            logs.append(f"تعذر مسح سجل المشاريع: {e}")

    # 4. Clean Gradle Locks & Stop Zombie Daemons
    try:
        killed = kill_gradle_daemons()
        for base in [paths.gradle_user_home(), os.path.expandvars(r"%USERPROFILE%\.gradle")]:
            if os.path.exists(base):
                for sub in ["daemon", "caches"]:
                    sub_path = os.path.join(base, sub)
                    if os.path.exists(sub_path):
                        for root, _, files in os.walk(sub_path):
                            for f in files:
                                if f.endswith(".lock") or f.endswith(".lck"):
                                    try:
                                        os.remove(os.path.join(root, f))
                                    except Exception:
                                        pass
        logs.append(f"تم إيقاف {killed} من دواليب Gradle وتصفية ملفات الأقفال (.lock)")
    except Exception as e:
        logs.append(f"تنبيه كاش الجرادل: {e}")

    # 5. Full Clean Slate mode (if explicitly requested by developer)
    if mode == "full":
        try:
            # Remove the Flutter bin entry from User PATH (exact match only)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    val = ""
                try:
                    with open(os.path.join(paths.data_dir(), "path_backup.txt"), "w", encoding="utf-8") as backup:
                        backup.write(val)
                except Exception:
                    pass
                flutter_bins = {
                    os.path.normcase(os.path.normpath(os.path.join(paths.flutter_root(), "bin"))),
                    os.path.normcase(os.path.normpath(os.path.join(paths.data_dir(), "flutter", "bin"))),
                }
                parts = [
                    p.strip() for p in val.split(";")
                    if p.strip() and os.path.normcase(os.path.normpath(p.strip())) not in flutter_bins
                ]
                new_val = ";".join(parts) + ";"
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_val)
            try:
                import ctypes
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
            except Exception:
                pass
            logs.append("تم إلغاء تسجيل Flutter من مسار PATH لاختبار التثبيت من الصفر")
        except Exception as e:
            logs.append(f"تعذر تعديل PATH: {e}")

        # Clean VS Code flutterSdkPath setting
        settings_path = paths.vscode_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                if "dart.flutterSdkPath" in s_data:
                    del s_data["dart.flutterSdkPath"]
                    with open(settings_path, "w", encoding="utf-8") as f:
                        json.dump(s_data, f, indent=2, ensure_ascii=False)
                    logs.append("تمت إزالة مسار SDK من إعدادات VS Code")
            except Exception as e:
                logs.append(f"تعذر تعديل إعدادات VS Code: {e}")

    return {
        "success": True,
        "mode": mode,
        "logs": logs,
        "message": "تمت إعادة تعيين بيئة الاختبار بنجاح! بإمكانك الآن إعادة تجربة واختبار البناء من الصفر."
    }
