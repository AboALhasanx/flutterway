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


def test_report_modal(browser) -> None:
    page = new_page(browser)
    page.evaluate("""() => {
        window.__clientErrors = 0;
        window.pywebview.api.report_client_error = async () => { window.__clientErrors += 1; return {success: true}; };
        window.pywebview.api.get_report_preview = async (payload) => ({
            success: true,
            markdown: '## معاينة\\n' + (payload.description || 'بدون وصف'),
            manifest: ['report.json', 'report.md', 'environment.json', 'manifest.json'],
            redactions: {paths: 2, emails: 1},
            warnings: ['التنقية آلية'],
            events_included: false
        });
        window.pywebview.api.open_error_report = async (payload) => ({
            success: true, opened: false,
            github_url: 'https://github.com/AboALhasanx/flutterway/issues/new?title=test',
            zip_path: '', markdown: 'report'
        });
        openReportModal('setup', 'تعذر التجهيز', 'Error: pub get failed');
    }""")
    page.wait_for_timeout(250)
    check("report-modal: visible", page.locator("#report-modal").is_visible())
    check("report-modal: error summary", "تعذر التجهيز" in page.locator("#report-summary").inner_text())
    check("report-modal: preview matches backend", "## معاينة" in page.locator("#report-preview-text").inner_text())
    check("report-modal: preview lists files", "report.json" in page.locator("#report-preview-files").inner_text())
    check("report-modal: preview shows redactions", "paths: 2" in page.locator("#report-preview-redactions").inner_text())
    check("report-modal: actions disabled before consent", page.locator("#btn-report-github").is_disabled())
    page.fill("#report-description", "ضغطت ابدأ التجهيز")
    page.wait_for_timeout(700)
    check("report-modal: preview follows description", "ضغطت ابدأ التجهيز" in page.locator("#report-preview-text").inner_text())
    check("report-modal: still disabled without consent", page.locator("#btn-report-github").is_disabled())
    page.check("#report-consent")
    check("report-modal: consent enables actions", page.locator("#btn-report-github").is_enabled())
    page.click("#btn-report-github")
    page.wait_for_timeout(300)
    check("report-modal: github result", page.locator("#report-result").is_visible())
    check("report-modal: result link", "issues/new" in (page.locator("#report-result-link a").get_attribute("href") or ""))
    page.keyboard.press("Escape")
    check("report-modal: escape closes", not page.locator("#report-modal").is_visible())
    page.evaluate("window.dispatchEvent(new ErrorEvent('error', {message:'boom', error:new Error('boom')}))")
    page.wait_for_timeout(150)
    check("report-modal: client error logged", page.evaluate("window.__clientErrors") == 1)
    page.close()


def test_build_stage_truth(browser) -> None:
    page = new_page(browser)
    page.evaluate("""() => {
        switchMainView('wizard'); showStep(3); resetBuildUi();
        finishRealBuild({success: false, stages: {build: 'failed', install: 'skipped', launch: 'skipped'}, message: 'gradle failed'});
    }""")
    step2 = page.locator("#bstep-2").get_attribute("class") or ""
    step3 = page.locator("#bstep-3").get_attribute("class") or ""
    check("build-stage: build failure marks build step", "error" in step2, step2)
    check("build-stage: build failure leaves install neutral", "error" not in step3, step3)

    page.evaluate("""() => {
        resetBuildUi();
        finishRealBuild({success: true, stages: {build: 'success', install: 'failed', launch: 'skipped'}, message: 'install failed'});
    }""")
    step3 = page.locator("#bstep-3").get_attribute("class") or ""
    check("build-stage: install failure marks install step", "error" in step3, step3)
    check("build-stage: install failure shows retry", page.locator("#btn-run-test").is_visible())

    page.evaluate("""() => {
        resetBuildUi();
        finishRealBuild({success: true, installed_ok: true, launched_ok: false,
            stages: {build: 'success', install: 'success', launch: 'unknown'}, device_name: 'Tab'});
    }""")
    page.wait_for_timeout(850)
    head = page.locator("#benchmark-head-text").inner_text()
    check("build-stage: launch unknown is partial", "تم تثبيت التطبيق" in head and "لم نتحقق" in head, head)
    report_display = page.locator("#btn-build-report").evaluate("el => el.style.display")
    check("build-stage: partial keeps report button", report_display == "inline-flex", report_display)
    page.close()


def test_hot_reload_conflict_ui(browser) -> None:
    page = new_page(browser)
    page.evaluate("""async () => {
        window.pywebview.api.hot_reload_save = async () => ({
            success: false, code: 'external_change', message: 'الملف تغيّر من خارج FlutterWay.'
        });
        document.getElementById('hr-advanced').open = true;
        switchMainView('companion'); switchCompanionTab('hotreload');
        const editor = document.getElementById('hr-editor');
        editor.value = 'changed';
        hrLastContent = 'old';
        await saveHotReload();
    }""")
    check("hot-reload-conflict: box visible", page.locator("#hr-conflict-box").is_visible())
    check("hot-reload-conflict: explains the file changed", "تغيّر" in page.locator("#hr-conflict-text").inner_text())
    check("hot-reload-conflict: offers both choices",
          page.locator("#hr-conflict-box button").count() == 2)
    page.close()


def test_progress_smooth_and_rotating(browser) -> None:
    page = new_page(browser)
    page.evaluate("""() => {
        switchMainView('wizard'); showStep(2); resetProgressDisplay();
        updateProgress(10, 'نبدأ التجهيز...', 1);
        updateProgress(80, 'جاري تنزيل أدوات Android SDK... 57%', 3);
    }""")
    page.wait_for_timeout(250)
    visible_state = page.evaluate("""() => ({
        shown: parseInt(document.getElementById('progress-pct').innerText),
        aria: document.getElementById('progress-bar').getAttribute('aria-valuenow')
    })""")
    shown = visible_state["shown"]
    check("progress: not an instant jump", shown < 80, f"shown={shown}")
    aria = visible_state["aria"]
    check("progress: visible percentage matches ARIA", aria == str(shown), f"shown={shown} aria={aria}")
    main = page.locator("#progress-text").inner_text()
    detail = page.locator("#progress-detail").inner_text()
    check("progress: stage percent separated", "57" not in main and "57" in detail, f"main={main} detail={detail}")
    page.wait_for_timeout(350)
    wait_text = page.locator("#progress-wait").inner_text()
    check("progress: rotating wait message", bool(wait_text.strip()), f"text={wait_text}")
    check("progress: slide-in class", "slide-in" in (page.locator("#progress-wait").get_attribute("class") or ""))
    stalled = page.evaluate("""() => {
        displayedProgress = targetProgress;
        lastProgressAt = Date.now() - 10000;
        paintProgress();
        const before = document.getElementById('progress-pct').innerText;
        progressTick();
        return {before, after: document.getElementById('progress-pct').innerText};
    }""")
    check("progress: stalled state does not invent percentage", stalled["after"] == stalled["before"], f"before={stalled['before']} after={stalled['after']}")
    page.close()


def test_progress_reduced_motion(browser) -> None:
    page = new_page(browser)
    page.emulate_media(reduced_motion="reduce")
    page.evaluate("switchMainView('wizard'); showStep(2); resetProgressDisplay(); updateProgress(64, 'جاري التجهيز...', 2); progressTick()")
    shown = page.evaluate("parseInt(document.getElementById('progress-pct').innerText)")
    aria = page.locator("#progress-bar").get_attribute("aria-valuenow")
    transition = page.locator("#progress-fill").evaluate("el => getComputedStyle(el).transitionDuration")
    check("progress: reduced motion jumps to truthful value", shown == 64, f"shown={shown}")
    check("progress: reduced motion ARIA matches", aria == str(shown), f"shown={shown} aria={aria}")
    check("progress: reduced motion disables fill transition", transition == "0s", f"duration={transition}")
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


def test_build_progress_mapping(browser) -> None:
    page = new_page(browser)
    page.evaluate("""() => {
        switchMainView('wizard'); showStep(3); resetBuildUi();
        appendLiveBuildLog('> Task :app:compileFlutterBuildDebug');
    }""")
    page.wait_for_timeout(350)
    visible_state = page.evaluate("""() => ({
        shown: parseInt(document.getElementById('build-progress-pct').innerText),
        aria: document.getElementById('build-progress-bar').getAttribute('aria-valuenow')
    })""")
    first = visible_state["shown"]
    label = page.locator("#build-progress-label").inner_text()
    check("build-progress: moves from Gradle task", first > 0, f"pct={first}")
    check("build-progress: estimated label", "تقديري" in label, label)
    aria = visible_state["aria"]
    check("build-progress: visible percentage matches ARIA", aria == str(first), f"pct={first} aria={aria}")
    page.evaluate("appendLiveBuildLog('[ADB] Installing on device...')")
    page.wait_for_timeout(450)
    second = page.evaluate("parseInt(document.getElementById('build-progress-pct').innerText)")
    check("build-progress: install milestone", second > first, f"first={first} second={second}")
    stalled = page.evaluate("""() => {
        buildProgressShown = buildProgressTarget;
        buildProgressLastAt = Date.now() - 20000;
        paintBuildProgress();
        const before = document.getElementById('build-progress-pct').innerText;
        buildProgressTick();
        return {before, after: document.getElementById('build-progress-pct').innerText};
    }""")
    check("build-progress: stalled estimate does not creep", stalled["after"] == stalled["before"], f"before={stalled['before']} after={stalled['after']}")
    page.evaluate("finishRealBuild({success:true, installed_ok:true, device_name:'Phone', build_time:'1s', apk_size:'71 MB'})")
    page.wait_for_timeout(650)
    final = page.evaluate("parseInt(document.getElementById('build-progress-pct').innerText)")
    check("build-progress: completes at 100", final == 100, f"final={final}")
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
            test_report_modal,
            test_setup_guard_and_error_details,
            test_build_stage_truth,
            test_hot_reload_conflict_ui,
            test_progress_smooth_and_rotating,
            test_progress_reduced_motion,
            test_build_progress_mapping,
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
