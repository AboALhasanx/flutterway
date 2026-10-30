"""Aggressive failure/state tests for the FlutterWay UI.

Loads the real HTML in Chromium and stubs the pywebview bridge to force
failures. No device, no real build, no repository writes.

Run:
    python tests/reliability_faults.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "gui" / "onboarding" / "index.html"
CHROMIUM = Path.home() / "AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def new_page(browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(HTML.as_uri(), wait_until="domcontentloaded")
    page.wait_for_timeout(250)
    # Every test starts from a clean no-bridge state.
    page.evaluate("window.pywebview = { api: {} }")
    return page


def test_progress_smooth_and_rotating(browser) -> None:
    page = new_page(browser)
    page.evaluate("""() => {
        switchMainView('wizard'); showStep(2); resetProgressDisplay();
        updateProgress(10, 'نبدأ التجهيز...', 1);
        updateProgress(80, 'جاري تنزيل أدوات Android SDK... 57%', 3);
    }""")
    page.wait_for_timeout(250)
    shown = page.evaluate("parseInt(document.getElementById('progress-pct').innerText)")
    check("progress: not an instant jump", shown < 80, f"shown={shown}")
    main = page.locator("#progress-text").inner_text()
    detail = page.locator("#progress-detail").inner_text()
    check("progress: stage percent separated", "57" not in main and "57" in detail, f"main={main} detail={detail}")
    page.wait_for_timeout(350)
    wait_text = page.locator("#progress-wait").inner_text()
    check("progress: rotating wait message", bool(wait_text.strip()), f"text={wait_text}")
    check("progress: slide-in class", "slide-in" in (page.locator("#progress-wait").get_attribute("class") or ""))
    page.close()


def test_setup_guard_and_error_details(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.__setupCalls = 0;
        window.pywebview.api.start_onboarding = async () => {
            window.__setupCalls += 1;
            await new Promise(r => setTimeout(r, 80));
            return {success: true};
        };
        switchMainView('wizard'); showStep(1);
        await Promise.all([startSetup(), startSetup()]);
    }""")
    calls = page.evaluate("window.__setupCalls")
    check("setup-guard: one start call", calls == 1, f"calls={calls}")
    page.evaluate("""showStep(2); onboardingFailed('تعذر إنشاء المشروع.\\nError: pub get failed\\nline two')""")
    check("setup-error: summary only", "تعذر إنشاء المشروع" in page.locator("#setup-error-text").inner_text())
    check("setup-error: details visible", page.locator("#setup-error-details").is_visible())
    check("setup-error: real log shown", "pub get failed" in page.locator("#setup-error-details").inner_text())
    page.close()


def test_driver_alert_truth(browser) -> None:
    page = new_page(browser)
    page.evaluate("switchMainView('wizard'); showStep(3);")
    page.evaluate("handleDeviceResponse({success:true, devices:[], missing_driver:false})")
    check("driver-alert: hidden when no driver issue", not page.locator("#missing-driver-alert").is_visible())
    page.evaluate("handleDeviceResponse({success:true, devices:[], missing_driver:true, missing_name:'Android'})")
    check("driver-alert: shown for real Android", page.locator("#missing-driver-alert").is_visible())
    page.evaluate("handleDeviceResponse({success:true, devices:[{is_ready:true, model:'Phone'}], missing_driver:true})")
    check("driver-alert: hidden when device is ready", not page.locator("#missing-driver-alert").is_visible())
    page.close()


def test_build_success_loop(browser) -> None:
    page = new_page(browser)
    page.evaluate("switchMainView('wizard'); showStep(3);")
    page.evaluate("handleDeviceResponse({success:true, devices:[{is_ready:true, model:'Phone'}]})")
    page.evaluate("finishRealBuild({success:true, installed_ok:true, device_name:'Phone', build_time:'9s', apk_size:'71 MB'})")
    page.wait_for_timeout(850)
    check("build-success: benchmark visible", page.locator("#benchmark-card").is_visible())
    check("build-success: rebuild CTA hidden", not page.locator("#btn-run-test").is_visible())
    page.evaluate("handleDeviceResponse({success:true, devices:[{is_ready:true, model:'Phone'}]})")
    check("build-success: poll keeps CTA hidden", not page.locator("#btn-run-test").is_visible())
    page.close()


def test_build_double_start(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.__calls = 0;
        window.pywebview.api.start_real_gradle_build = async () => {
            window.__calls += 1;
            await new Promise(r => setTimeout(r, 50));
            return {success: true};
        };
        switchMainView('wizard'); showStep(3);
        await Promise.all([runRealGradleBuild(), runRealGradleBuild()]);
    }""")
    calls = page.evaluate("window.__calls")
    check("build-double: one backend call", calls == 1, f"calls={calls}")
    page.close()


def test_build_retry_resets(browser) -> None:
    page = new_page(browser)
    page.evaluate("""() => {
        switchMainView('wizard'); showStep(3);
        finishRealBuild({success:false, installed_ok:false, message:'boom'});
    }""")
    assert page.locator("#build-elapsed-timer").inner_text() == "00:00"
    page.evaluate("""async () => {
        window.pywebview.api.start_real_gradle_build = async () => ({success: true});
        await runRealGradleBuild();
    }""")
    check("build-retry: timer reset", page.locator("#build-elapsed-timer").inner_text() == "00:00")
    check("build-retry: step1 active", "active" in (page.locator("#bstep-1").get_attribute("class") or ""))
    check("build-retry: step3 cleared", "error" not in (page.locator("#bstep-3").get_attribute("class") or ""))
    check("build-retry: benchmark hidden", not page.locator("#benchmark-card").is_visible())
    check("build-retry: CTA hidden", not page.locator("#btn-run-test").is_visible())
    page.close()


def test_build_start_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.pywebview.api.start_real_gradle_build = async () => ({success:false, error:'lock busy'});
        switchMainView('wizard'); showStep(3);
        await runRealGradleBuild();
    }""")
    check("build-start-fail: state failed", page.evaluate("buildState") == "failed")
    check("build-start-fail: retry CTA visible", page.locator("#btn-run-test").is_visible())
    check("build-start-fail: retry label", "أعد المحاولة" in page.locator("#btn-run-test").inner_text())
    check("build-start-fail: log visible", page.locator("#build-console").is_visible())
    check("build-start-fail: no benchmark", not page.locator("#benchmark-card").is_visible())
    page.close()


def test_build_exception(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.pywebview.api.start_real_gradle_build = async () => { throw new Error('bridge dead'); };
        switchMainView('wizard'); showStep(3);
        await runRealGradleBuild();
    }""")
    check("build-exception: error logged", "bridge dead" in page.locator("#build-terminal-lines").inner_text())
    check("build-exception: retry CTA visible", page.locator("#btn-run-test").is_visible())
    page.close()


def test_create_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.pywebview.api.create_lecture_project = async () => ({success:false, error:'disk full'});
        document.getElementById('input-lecture-name').value = 'broken';
        await createNewLectureProject();
    }""")
    check("create-fail: no undefined name", page.locator("#active-proj-name").inner_text() != "undefined")
    check("create-fail: no undefined path", page.locator("#active-proj-path").inner_text() != "undefined")
    check("create-fail: error status", "disk full" in page.locator("#project-action-status").inner_text())
    page.wait_for_timeout(1800)
    check("create-fail: button restored", "أنشئ مشروعي" in page.locator("#btn-create-lecture-proj").inner_text())
    page.close()


def test_clean_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        selectActiveProject('demo', 'C:\\\\tmp\\\\demo');
        window.pywebview.api.clean_project = async () => ({success:false, error:'folder locked'});
        await cleanActiveProject();
    }""")
    check("clean-fail: no false success", "تم التنظيف" not in page.locator("#btn-clean-project").inner_text())
    check("clean-fail: error status", "folder locked" in page.locator("#project-action-status").inner_text())
    page.wait_for_timeout(1800)
    check("clean-fail: button restored", "تنظيف البناء" in page.locator("#btn-clean-project").inner_text())
    page.close()


def test_heal_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.pywebview.api.heal_all_doctor_items = async () => ({success:false, error:'cannot heal'});
        await healAllDoctorIssues();
    }""")
    check("heal-fail: no false success", "تم الإصلاح" not in page.locator("#doctor-summary-line").inner_text())
    check("heal-fail: error shown", "cannot heal" in page.locator("#doctor-summary-line").inner_text())
    page.close()


def test_laptop_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        switchMainView('wizard'); showStep(1);
        window.pywebview.api.check_laptop_compatibility = async () => { throw new Error('probe failed'); };
        await checkLaptopSpecs();
    }""")
    check("laptop-fail: error box visible", page.locator("#laptop-check-error").is_visible())
    check("laptop-fail: button restored", "أعد المحاولة" in page.locator("#btn-check-laptop").inner_text())
    check("laptop-fail: button enabled", page.locator("#btn-check-laptop").is_enabled())
    page.close()


def test_vscode_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        selectActiveProject('demo', 'C:\\\\tmp\\\\demo');
        window.pywebview.api.open_project_in_vscode = async () => ({success:false, error:'code missing'});
        await openActiveProjectVSCode();
    }""")
    check("vscode-fail: error status", "code missing" in page.locator("#project-action-status").inner_text())
    page.close()


def test_driver_and_adb_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.pywebview.api.install_usb_drivers = async () => ({success:false});
        await installDrivers();
    }""")
    check("drivers-fail: error label", "تعذر التثبيت" in page.locator("#btn-install-drivers").inner_text())
    page.evaluate("""async () => {
        window.pywebview.api.restart_adb = async () => ({success:false});
        await restartAdb();
    }""")
    check("adb-fail: error label", "تعذر" in page.locator("#btn-fix-adb").inner_text())
    page.close()


def test_projects_load_failure(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        switchMainView('companion'); switchCompanionTab('projects');
        window.pywebview.api.get_recent_projects = async () => { throw new Error('io error'); };
        await loadRecentProjectsList();
    }""")
    check("projects-load-fail: error state", page.locator("#recent-projects-list .state-box.error").is_visible())
    check("projects-load-fail: retry button", page.locator("#recent-projects-list button").count() >= 1)
    page.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not CHROMIUM.exists():
        print(f"Chromium not found: {CHROMIUM}")
        return 2
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(CHROMIUM))
        tests = [
            test_driver_alert_truth,
            test_setup_guard_and_error_details,
            test_progress_smooth_and_rotating,
            test_build_success_loop,
            test_build_double_start,
            test_build_retry_resets,
            test_build_start_failure,
            test_build_exception,
            test_create_failure,
            test_clean_failure,
            test_heal_failure,
            test_laptop_failure,
            test_vscode_failure,
            test_driver_and_adb_failure,
            test_projects_load_failure,
        ]
        for test in tests:
            try:
                test(browser)
            except Exception as exc:
                check(test.__name__, False, f"exception: {exc}")
        browser.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    for name, ok, detail in RESULTS:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\n{passed}/{len(RESULTS)} checks passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
