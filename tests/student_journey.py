"""Student-journey UI test against the real pywebview/WebView2 app.

This is not a unit test. It launches the actual desktop app, connects to its
WebView2 through the Chrome DevTools Protocol, and walks through what a student
would see and click. It is read-only: it never starts onboarding, installs
drivers, resets the environment, builds an APK, or uninstalls anything.

Run from the repository root:
    python tests/student_journey.py

Screenshots and a JSON/Markdown report are written to tmp/student_journey/.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp" / "student_journey"
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"


def wait_for_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.35)
    return False


def launch_app():
    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={CDP_PORT}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "gui.onboarding_app"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)

    if wait_for_port(CDP_PORT, timeout=1):
        print(f"Port {CDP_PORT} is already in use; refusing to attach to an unknown app.")
        return 2

    app = launch_app()
    try:
        if not wait_for_port(CDP_PORT, timeout=35):
            print("The app did not expose the WebView2 CDP port.")
            return 3

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            deadline = time.time() + 20
            page = None
            while time.time() < deadline:
                if context.pages:
                    page = context.pages[0]
                    break
                time.sleep(0.3)
            if not page:
                print("No WebView2 page was found.")
                return 4

            page.set_default_timeout(20000)
            page.wait_for_function("window.pywebview && window.pywebview.api")
            page.wait_for_timeout(800)

            console_errors: list[str] = []
            page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
            page.on("console", lambda msg: console_errors.append(f"console: {msg.text}") if msg.type == "error" else None)

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "app": str(ROOT),
                "viewport": page.evaluate("({width: window.innerWidth, height: window.innerHeight})"),
                "screens": [],
                "metrics": {},
                "findings": [],
            }

            def shot(name: str, note: str):
                path = OUT / f"{name}.png"
                page.screenshot(path=str(path))
                report["screens"].append({"name": name, "note": note, "path": str(path)})

            def finding(severity: str, area: str, note: str):
                report["findings"].append({"severity": severity, "area": area, "note": note})

            # 1. First launch: what a new student sees.
            page.evaluate("switchMainView('wizard'); showStep(1);")
            page.wait_for_timeout(400)
            shot("01_step1_welcome", "أول شاشة: كيف تريد اختبار تطبيقاتك؟")
            viewport = report["viewport"]
            config = page.evaluate("""() => {
                const btn = document.getElementById('btn-start-setup');
                const box = btn ? btn.getBoundingClientRect() : null;
                return {
                    scrollHeight: document.documentElement.scrollHeight,
                    viewportHeight: window.innerHeight,
                    cta: box ? {top: box.top, bottom: box.bottom, height: box.height} : null,
                    hasCheckBanner: !!document.getElementById('btn-check-laptop')
                };
            }""")
            report["metrics"]["step1"] = config
            if config["cta"] and config["cta"]["bottom"] > config["viewportHeight"]:
                finding("medium", "Step 1 layout", "زر (متابعة التجهيز التلقائي) تحت الطية في أول شاشة؛ الطالب لازم ينزل السكرول حتى يشوف الإجراء الأساسي.")
            if config["scrollHeight"] > config["viewportHeight"] + 80:
                finding("low", "Step 1 layout", f"محتوى المستوى 1 أطول من النافذة ({config['scrollHeight']}px مقابل {config['viewportHeight']}px).")

            # 2. Student clicks the laptop check (real read-only Python API).
            page.click("#btn-check-laptop")
            page.wait_for_timeout(1200)
            shot("02_step1_laptop_check", "بعد فحص اللابتوب: النتيجة والمقارنة")
            check = page.evaluate("""() => ({
                ram: document.getElementById('spec-ram')?.innerText,
                disk: document.getElementById('spec-disk')?.innerText,
                vt: document.getElementById('spec-vt')?.innerText,
                resultVisible: !!document.querySelector('#diag-result-box')
            })""")
            report["metrics"]["laptop_check"] = check
            if not check["ram"] or not check["disk"]:
                finding("high", "Step 1 check", "نتيجة فحص اللابتوب لا تعرض الرام/القرص بشكل واضح.")

            # 3. Student selects USB. This is only a UI selection.
            page.evaluate("selectChoice('usb')")
            page.wait_for_timeout(150)
            selected = page.evaluate("document.getElementById('card-usb').classList.contains('selected')")
            if not selected:
                finding("high", "Step 1 selection", "اختيار (هاتف USB) لا يظهر كبطاقة محددة.")

            # 4. Step 2 preview: in-progress and failure states, without running setup.
            page.evaluate("showStep(2); updateProgress(25, 'جاري تهيئة بيئة Java ومحرك بناء أندرويد Gradle...', 2);")
            page.wait_for_timeout(350)
            shot("03_step2_progress", "المستوى 2: شكل التقدم (بدون تشغيل التثبيت)")
            page.evaluate("onboardingFailed('تعذر تنزيل Flutter SDK. تأكد من اتصال الإنترنت ثم أعد المحاولة.')")
            page.wait_for_timeout(250)
            shot("04_step2_error", "المستوى 2: حالة فشل واضحة مع زر إعادة المحاولة")
            error_visible = page.locator("#setup-error-box").is_visible()
            if not error_visible:
                finding("high", "Step 2 error", "حالة الفشل لا تظهر داخل المعالج.")
            page.evaluate("resetSetupError()")

            # 5. Step 3: real device detection via the read-only Python API.
            page.evaluate("showStep(3)")
            device = page.evaluate("""async () => await window.pywebview.api.check_connected_devices()""")
            page.evaluate("(res) => handleDeviceResponse(res)", device)
            page.wait_for_timeout(600)
            shot("05_step3_device", "المستوى 3: كشف الهاتف المتصل")
            status = page.locator("#device-status-text").inner_text()
            report["metrics"]["device"] = {"count": device.get("count"), "status_text": status}
            if device.get("count", 0) > 0 and "تم الاتصال" not in status:
                finding("high", "Step 3 device", "الهاتف متصل لكن شاشة الجهاز لا تعرض حالة الاتصال.")

            page.evaluate("handleDeviceResponse({success: true, devices: []})")
            page.wait_for_timeout(200)
            waiting = page.locator("#device-status-text").inner_text()
            shot("06_step3_waiting", "المستوى 3: حالة انتظار الهاتف")
            if "بانتظار" not in waiting:
                finding("high", "Step 3 device", "فصل الهاتف لا يعيد الواجهة لحالة الانتظار.")
            page.evaluate("stopDevicePolling()")

            # 5b. Build screen: three beginner steps, raw log collapsed until failure.
            page.evaluate("""() => {
                document.getElementById('build-console').style.display = 'block';
                document.getElementById('device-guide-box').style.display = 'none';
            }""")
            page.wait_for_timeout(200)
            shot("05b_build_beginners", "شاشة البناء: ثلاث مراحل والسجل مطوي")
            if page.evaluate("document.getElementById('build-log-details').open"):
                finding("high", "Build screen", "سجل البناء مفتوح افتراضياً؛ يجب أن يبقى مطوياً.")
            page.evaluate("finishRealBuild({success: false, installed_ok: false, message: 'build failed'})")
            page.wait_for_timeout(250)
            shot("05c_build_failure", "شاشة البناء: الفشل يفتح السجل تلقائياً")
            if not page.evaluate("document.getElementById('build-log-details').open"):
                finding("high", "Build screen", "الفشل لا يفتح سجل البناء تلقائياً.")

            # 6. Step 4 preview without opening VS Code.
            page.evaluate("""() => {
                document.querySelectorAll('.step-view').forEach(el => el.classList.remove('active'));
                document.getElementById('step-4').classList.add('active');
            }""")
            page.wait_for_timeout(300)
            shot("07_step4_vscode", "المستوى 4: بطاقة VS Code والمختصرات")

            # 7. Companion dashboard: the returning-student path.
            page.evaluate("switchMainView('companion')")
            page.wait_for_timeout(1200)
            shot("07b_home", "الرئيسية: الخطوة التالية للطالب")
            home_title = page.locator("#home-title").inner_text()
            report["metrics"]["home_title"] = home_title
            if not home_title.strip():
                finding("high", "Home", "الرئيسية لا تعرض خطوة تالية.")
            page.click("#btn-tab-more")
            page.wait_for_timeout(250)
            shot("07c_more_menu", "المزيد: الأدوات الثانوية في قائمة واحدة")
            more_open = page.evaluate("getComputedStyle(document.getElementById('more-menu')).display")
            if more_open != "block":
                finding("high", "More menu", "قائمة المزيد لا تفتح.")
            page.click("#more-menu .more-item:nth-child(4)")
            page.wait_for_timeout(1200)
            hot_active = page.evaluate("document.getElementById('tab-hotreload').classList.contains('active')")
            if not hot_active:
                finding("high", "More menu", "Hot Reload غير قابل للوصول من قائمة المزيد.")
            shot("07d_hot_reload_entry", "الوصول إلى Hot Reload من المزيد")
            page.evaluate("switchCompanionTab('doctor')")
            page.wait_for_timeout(3000)
            shot("08_companion_doctor", "لوحة رفيق الطالب: طبيب فلاتر الذكي")
            doctor = page.evaluate("""() => ({
                score: document.getElementById('doctor-score-display')?.innerText,
                subtitle: document.getElementById('doctor-score-subtitle')?.innerText,
                cards: document.querySelectorAll('#doctor-cards-grid .doc-item-card').length
            })""")
            report["metrics"]["doctor"] = doctor
            if doctor["cards"] < 5:
                finding("high", "Companion / Doctor", f"عدد بطاقات الطبيب قليل ({doctor['cards']}) أو الشبكة لم تُرسم.")
            if doctor["score"] != "100%" and doctor["cards"] == 0:
                finding("medium", "Companion / Doctor", "التقرير لا يعرض تفاصيل عندما لا تكون البيئة مكتملة.")

            page.evaluate("switchCompanionTab('projects')")
            page.wait_for_timeout(800)
            shot("09_companion_projects", "تبويب مشاريع المحاضرات")
            projects = page.evaluate("""() => ({
                count: document.querySelectorAll('#recent-projects-list .recent-item').length,
                active: typeof activeProjPath !== 'undefined' ? activeProjPath : null
            })""")
            report["metrics"]["projects"] = projects
            if projects["count"] == 0:
                finding("low", "Companion / Projects", "لا توجد مشاريع حديثة، والطالب يرى مساحة فارغة بدون زر إنشاء واضح داخل نفس البطاقة.")

            page.evaluate("switchCompanionTab('rescue')")
            page.wait_for_timeout(300)
            shot("10_companion_rescue", "صندوق الإنقاذ السريع")
            rescue = page.evaluate("""() => Array.from(document.querySelectorAll('#tab-rescue button')).map(b => b.innerText.trim()).filter(Boolean)""")
            report["metrics"]["rescue_buttons"] = rescue
            if len(rescue) < 5:
                finding("medium", "Companion / Rescue", f"عدد أزرار الإنقاذ {len(rescue)} بدل 5.")

            page.evaluate("switchCompanionTab('device')")
            page.wait_for_timeout(1800)
            shot("11_companion_device", "استوديو الهاتف المتصل")
            device_studio = page.evaluate("""() => ({
                name: document.getElementById('dev-val-name')?.innerText,
                android: document.getElementById('dev-val-android')?.innerText,
                battery: document.getElementById('dev-val-battery')?.innerText,
                screen: document.getElementById('dev-val-screen')?.innerText
            })""")
            report["metrics"]["device_studio"] = device_studio

            page.evaluate("switchCompanionTab('cheatsheet')")
            page.wait_for_timeout(300)
            shot("12_companion_cheatsheet", "مفكرة الطالب والمختصرات")

            # 8. Theme toggle: the student's first customization.
            page.evaluate("toggleTheme()")
            page.wait_for_timeout(300)
            shot("13_light_theme", "الوضع النهاري")
            page.evaluate("toggleTheme()")
            page.wait_for_timeout(200)

            # 9. Developer modal: inspect only, never execute a destructive reset.
            page.evaluate("openDevModal()")
            page.wait_for_timeout(4500)
            shot("14_dev_modal", "لوحة المطور: معاينة ما يمكن حذفه وإجراءات granular")
            modal = page.evaluate("""() => {
                const m = document.getElementById('dev-modal');
                return {
                    role: m?.getAttribute('role'),
                    modal: m?.getAttribute('aria-modal'),
                    escapeFocus: document.activeElement?.className || ''
                };
            }""")
            report["metrics"]["dev_modal"] = modal
            status_text = page.locator("#dev-status-box").inner_text()
            report["metrics"]["dev_status_preview"] = status_text[:700]
            if "Flutter" not in status_text:
                finding("medium", "Developer reset", "لوحة المطور لا تعرض قائمة المسارات القابلة للحذف.")

            # Safe action: reset the student UI only.
            page.click("#btn-dev-ui-reset")
            page.wait_for_timeout(600)
            ui_reset = page.evaluate("""() => ({
                step1: document.getElementById('step-1').classList.contains('active'),
                pct: document.getElementById('progress-pct')?.innerText,
                errorHidden: !document.getElementById('setup-error-box') || document.getElementById('setup-error-box').style.display === 'none'
            })""")
            report["metrics"]["dev_ui_reset"] = ui_reset
            if not ui_reset["step1"] or ui_reset["pct"] != "0%":
                finding("medium", "Developer reset", "زر إعادة الواجهة لا يرجع الطالب للمستوى 1 بنسبة 0%.")

            # Cancellation guards: none of these may reach the destructive backend.
            page.evaluate("openDevModal()")
            page.wait_for_timeout(1200)
            page.evaluate("window.confirm = () => false; window.prompt = () => 'NO'")
            page.click("#btn-dev-projects-reset")
            page.wait_for_timeout(250)
            page.click("#btn-dev-downloads-all")
            page.wait_for_timeout(250)
            page.click("#btn-dev-all-reset")
            page.wait_for_timeout(250)
            cancel_logs = page.locator("#dev-console-lines").inner_text()
            report["metrics"]["dev_cancel_logs"] = cancel_logs[-500:]
            if "تم الإلغاء" not in cancel_logs:
                finding("high", "Developer reset", "الإجراءات الخطرة لا تُلغى عند رفض التأكيد.")

            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            if page.locator("#dev-modal").is_visible():
                finding("medium", "Developer modal", "Escape لا يغلق نافذة المطور.")

            # 10. Keyboard selection on the mode cards.
            page.evaluate("switchMainView('wizard'); showStep(1); selectChoice('usb')")
            page.locator("#card-emu").focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(150)
            keyboard = page.evaluate("""() => ({
                usb: document.getElementById('card-usb')?.getAttribute('aria-pressed'),
                emu: document.getElementById('card-emu')?.getAttribute('aria-pressed')
            })""")
            report["metrics"]["keyboard"] = keyboard
            if keyboard["emu"] != "true":
                finding("medium", "Accessibility", "اختيار البطاقة بلوحة المفاتيح لا يعمل.")

            # 11. Layout and accessibility metrics.
            a11y = page.evaluate("""() => ({
                aria: document.querySelectorAll('[aria-label], [aria-labelledby], [aria-pressed], [aria-modal]').length,
                roles: document.querySelectorAll('[role]').length,
                mediaRules: Array.from(document.styleSheets).reduce((count, sheet) => {
                    try { return count + Array.from(sheet.cssRules).filter(r => r.type === CSSRule.MEDIA_RULE).length; }
                    catch (e) { return count; }
                }, 0),
                terminalSelect: getComputedStyle(document.getElementById('build-terminal-lines')).userSelect
            })""")
            report["metrics"]["a11y"] = a11y
            if a11y["mediaRules"] == 0:
                finding("medium", "Responsive", "لا توجد @media rules؛ الواجهة لا تتكيف مع الدقة/التكبير.")
            if a11y["terminalSelect"] != "text":
                finding("medium", "Accessibility", "لا يمكن تحديد/نسخ سجل البناء.")

            report["console_errors"] = console_errors
            if console_errors:
                finding("high", "Runtime", f"أخطاء JavaScript أثناء الرحلة: {len(console_errors)}")

            (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            lines = [
                "# Student Journey Report",
                "",
                f"- Date: {report['timestamp']}",
                f"- Viewport: {report['viewport']['width']}x{report['viewport']['height']}",
                f"- Screens: {len(report['screens'])}",
                f"- Findings: {len(report['findings'])}",
                "",
                "## Findings",
            ]
            if report["findings"]:
                lines += [f"- **{f['severity'].upper()}** [{f['area']}] {f['note']}" for f in report["findings"]]
            else:
                lines.append("- No automatic findings.")
            lines += ["", "## Screens"]
            lines += [f"- `{s['path']}` — {s['note']}" for s in report["screens"]]
            (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")

            print(json.dumps({
                "viewport": report["viewport"],
                "screens": len(report["screens"]),
                "findings": report["findings"],
                "console_errors": console_errors,
                "report": str(OUT / "report.md"),
            }, ensure_ascii=False, indent=2))

            browser.close()
            return 0
    finally:
        try:
            app.terminate()
            app.wait(timeout=5)
        except Exception:
            try:
                app.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
