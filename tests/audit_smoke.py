"""Repeatable smoke checks for the P0 audit fixes.

Run from the repository root:
    python tests/audit_smoke.py

The UI checks use Playwright with the system Edge/Chromium. They do not
start the real pywebview app; they load the HTML and exercise the same
global functions the app calls.
"""

from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = ROOT / "gui" / "onboarding_app.py"
COMPANION = ROOT / "gui" / "companion_service.py"
VSCODE = ROOT / "gui" / "vscode_integration.py"
SPEC = ROOT / "FlutterWayNative.spec"
CLEAN = ROOT / "clean_slate.py"
HTML = ROOT / "gui" / "onboarding" / "index.html"


def static_checks() -> None:
    app_src = APP.read_text(encoding="utf-8")
    html_src = HTML.read_text(encoding="utf-8")

    tree = ast.parse(app_src)
    top_level_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "shutil" in top_level_imports, "shutil must be imported at module level"
    assert "def harness_enabled()" in app_src, "harness must be explicitly gated"
    assert "if harness_enabled():" in app_src, "main() must gate the harness"

    assert "res.success === true && res.installed_ok === true" in html_src, (
        "finishRealBuild must require both build and install success"
    )
    assert "rep.score || 100" not in html_src, "the 0% -> 100% falsy bug must stay fixed"
    assert "if not jdk_path:" in app_src, "onboarding must stop when JDK setup fails"
    assert "if not self._ensure_starter_project(project_path):" in app_src, (
        "onboarding must stop when the starter project fails"
    )
    assert "flutter_bat, \"create\"" in app_src, "starter project must fall back to flutter create"
    assert "function onboardingFailed" in html_src, "UI must expose a setup failure state"
    assert 'id="setup-error-box"' in html_src, "step 2 must render a setup error box"

    for source_path in (APP, COMPANION, VSCODE):
        source = source_path.read_text(encoding="utf-8")
        assert r"d:\flutterway" not in source.lower(), f"hardcoded project path in {source_path.name}"
        assert r"C:\flutter" not in source, f"hardcoded Flutter path in {source_path.name}"
        assert r"C:\Android" not in source, f"hardcoded SDK path in {source_path.name}"
        assert r"C:\g" not in source, f"hardcoded Gradle home in {source_path.name}"
        assert r"C:\flutter_test_app" not in source, f"hardcoded template path in {source_path.name}"

    assert "gui.paths" in SPEC.read_text(encoding="utf-8"), "PyInstaller must bundle gui.paths"
    assert "gui.android_sdk" in SPEC.read_text(encoding="utf-8"), "PyInstaller must bundle gui.android_sdk"
    assert "def install_android_sdk" in (ROOT / "gui" / "android_sdk.py").read_text(encoding="utf-8")
    assert "fix_android_sdk" in COMPANION.read_text(encoding="utf-8")
    companion_src = COMPANION.read_text(encoding="utf-8")
    assert "taskkill" not in companion_src, "must not kill every java.exe process"
    assert "def kill_gradle_daemons" in companion_src
    assert "ram_usage" not in app_src, "fake RAM metric must stay removed"
    assert 'id="stat-size"' in html_src, "success card must show the real APK size"
    assert "زمن بناء Gradle" in html_src, "build time must be labelled honestly"
    assert "item.innerHTML" not in html_src, "recent project names must not use innerHTML"
    assert "activeProjPath" in html_src, "selected project path must be tracked"
    assert "start_real_gradle_build(projectPath || null)" in html_src
    assert "setInterval(checkDeviceNow, 5000)" in html_src, "device polling must be slower"
    assert "_last_pnp_check" in app_src, "PowerShell PnP probe must be cached"
    assert "path_backup.txt" in app_src, "PATH changes must be backed up"
    assert "path_backup.txt" in companion_src, "PATH changes must be backed up"
    assert "flutter_bins" in companion_src, "full reset must match Flutter PATH exactly"
    assert "android-sdk-license" in companion_src, "license check must verify the real license file"
    clean_src = CLEAN.read_text(encoding="utf-8")
    assert "--uninstall-extensions" in clean_src, "extension removal must be opt-in"
    assert '"flutter" in lower' not in clean_src, "clean slate must not delete unrelated PATH entries"
    print("[static] passed")


def paths_checks() -> None:
    import shutil
    import tempfile

    from gui import paths
    from gui import android_sdk as sdk_bootstrap

    assert os.path.exists(paths.onboarding_html()), "onboarding HTML must resolve"
    assert os.path.exists(paths.driver_inf_path()), "USB driver INF must resolve"
    assert os.path.exists(paths.icon_path()), "window icon must resolve"
    assert paths.flutter_version(), "Flutter version must be readable"
    assert paths.flutter_bat(), "Flutter launcher must resolve"
    assert paths.adb_path(), "ADB path must resolve"
    assert paths.jdk_home(), "JDK must be discoverable on this host"
    assert os.path.isdir(paths.gradle_user_home()), "Gradle home must exist"
    assert os.path.isdir(paths.android_sdk_root()), "Android SDK must resolve"

    if sdk_bootstrap.sdk_ready():
        installed = sdk_bootstrap.install_android_sdk(persist=False)
        assert installed.get("success"), installed
        print("[sdk] ready path passed")
    else:
        print("[sdk] skipped download path (SDK is not fully installed on this host)")

    original = {
        "FLUTTERWAY_FLUTTER_ROOT": os.environ.get("FLUTTERWAY_FLUTTER_ROOT"),
        "ANDROID_SDK_ROOT": os.environ.get("ANDROID_SDK_ROOT"),
        "GRADLE_USER_HOME": os.environ.get("GRADLE_USER_HOME"),
    }
    temp_flutter = tempfile.mkdtemp(prefix="fw_flutter_")
    temp_sdk = tempfile.mkdtemp(prefix="fw_sdk_")
    temp_gradle = tempfile.mkdtemp(prefix="fw_gradle_")
    try:
        os.environ["FLUTTERWAY_FLUTTER_ROOT"] = temp_flutter
        os.environ["ANDROID_SDK_ROOT"] = temp_sdk
        os.environ["GRADLE_USER_HOME"] = temp_gradle
        assert os.path.abspath(temp_flutter) == paths.flutter_root()
        assert os.path.abspath(temp_sdk) == paths.android_sdk_root()
        assert os.path.abspath(temp_gradle) == paths.gradle_user_home()
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(temp_flutter, ignore_errors=True)
        shutil.rmtree(temp_sdk, ignore_errors=True)
        shutil.rmtree(temp_gradle, ignore_errors=True)
    print("[paths] passed")


def python_checks() -> None:
    """Exercise start_onboarding's failure path without touching the host."""
    import inspect

    import gui.onboarding_app as app

    params = inspect.signature(app.OnboardingApi.start_real_gradle_build).parameters
    assert "project_path" in params, "build API must accept the selected project path"

    class FakeWindow:
        def __init__(self):
            self.calls = []

        def evaluate_js(self, script):
            self.calls.append(script)

    api = app.OnboardingApi({"window": None})
    original = app.ensure_jdk
    app.ensure_jdk = lambda: None
    try:
        api.start_onboarding("usb")
        deadline = time.time() + 5
        while time.time() < deadline and not api.state.get("setup_error"):
            time.sleep(0.05)
        assert api.state.get("setup_error"), "JDK failure must stop onboarding with an error"
        assert api.state.get("is_complete") is False, "JDK failure must not mark setup complete"

        # The UI must receive the failure hook, not a fake 100% success.
        fake = FakeWindow()
        api2 = app.OnboardingApi({"window": fake})
        api2.start_onboarding("usb")
        deadline = time.time() + 5
        while time.time() < deadline and not any("onboardingFailed" in call for call in fake.calls):
            time.sleep(0.05)
        assert any("onboardingFailed" in call for call in fake.calls), (
            "start_onboarding must call onboardingFailed in the UI"
        )
    finally:
        app.ensure_jdk = original
    print("[python] onboarding failure path passed")


def launch_browser(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:
        pass
    try:
        return playwright.chromium.launch(channel="msedge")
    except Exception:
        pass

    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright\chromium-1243\chrome-win64\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return playwright.chromium.launch(executable_path=candidate)
    raise RuntimeError("No Chromium/Edge executable found for Playwright")


def ui_checks() -> None:
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(HTML.as_uri(), wait_until="domcontentloaded")
        page.wait_for_timeout(400)

        # 1) Doctor score: zero must render zero, not the falsy default 100.
        page.evaluate("renderDoctorReport({score: 0, items: []})")
        assert page.locator("#doctor-score-display").inner_text().strip() == "0%"
        assert "غير مكتملة" in page.locator("#doctor-score-subtitle").inner_text()

        # 2) Healthy score remains 100%.
        page.evaluate("renderDoctorReport({score: 100, items: []})")
        assert page.locator("#doctor-score-display").inner_text().strip() == "100%"

        # 2b) A setup failure must be visible and retryable, not a silent 100%.
        page.evaluate(
            "switchMainView('wizard'); showStep(2); onboardingFailed('تعذر تنزيل Flutter SDK')"
        )
        assert page.locator("#setup-error-box").is_visible()
        assert "تعذر تنزيل Flutter SDK" in page.locator("#setup-error-text").inner_text()
        page.evaluate("resetSetupError()")
        assert not page.locator("#setup-error-box").is_visible()

        # 2c) Recent-project names/paths must be rendered as text, never HTML.
        import json

        xss_project = {
            "name": "<img src=x onerror=window.__fw_xss=1>",
            "path": r"C:\Users\O'Brien\proj",
        }
        page.evaluate("switchMainView('companion'); switchCompanionTab('projects');")
        page.evaluate("renderRecentProjects(" + json.dumps([xss_project]) + ")")
        assert page.evaluate("window.__fw_xss || 0") == 0
        assert page.locator("#recent-projects-list img").count() == 0
        assert "O'Brien" in page.locator("#recent-projects-list").inner_text()
        page.locator("#recent-projects-list button").first.click()
        assert page.evaluate("activeProjPath") == r"C:\Users\O'Brien\proj"

        # Activate the wizard build screen for the build-state checks.
        page.evaluate("switchMainView('wizard'); showStep(3);")
        page.wait_for_timeout(200)

        # 3) A failed build must not show the success card.
        page.evaluate(
            "finishRealBuild({success: false, installed_ok: false, message: 'build failed'})"
        )
        assert page.locator("#build-console").is_visible()
        assert not page.locator("#benchmark-card").is_visible()
        assert "error" in (page.locator("#bstep-3").get_attribute("class") or "")
        assert "[ERROR] build failed" in page.locator("#build-terminal-lines").inner_text()

        # 4) A successful build with a failed install must also fail.
        page.evaluate(
            "finishRealBuild({success: true, installed_ok: false, message: 'install failed'})"
        )
        assert not page.locator("#benchmark-card").is_visible()
        assert "[ERROR] install failed" in page.locator("#build-terminal-lines").inner_text()

        # 5) Only a successful build + install shows the celebration card.
        page.evaluate(
            "finishRealBuild({success: true, installed_ok: true, device_name: 'Test Phone', build_time: '5s', apk_size: '12.3 MB'})"
        )
        page.wait_for_timeout(850)
        assert page.locator("#benchmark-card").is_visible()
        assert "Test Phone" in page.locator("#benchmark-head-text").inner_text()
        assert page.locator("#stat-size").inner_text().strip() == "12.3 MB"

        # 6) Disconnecting the phone must reset the device card.
        page.evaluate("handleDeviceResponse({success: true, devices: []})")
        assert "بانتظار" in page.locator("#device-status-text").inner_text()
        assert not page.locator("#btn-run-test").is_visible()

        # 7) A ready device must show the run button.
        page.evaluate(
            "handleDeviceResponse({success: true, devices: [{is_ready: true, model: 'Pixel'}]})"
        )
        assert "تم الاتصال" in page.locator("#device-status-text").inner_text()
        assert page.locator("#btn-run-test").is_visible()

        # 8) An unauthorized device must hide the run button.
        page.evaluate(
            "handleDeviceResponse({success: true, devices: [{is_ready: false, status: 'unauthorized'}]})"
        )
        assert "يتطلب الموافقة" in page.locator("#device-status-text").inner_text()
        assert not page.locator("#btn-run-test").is_visible()

        browser.close()
    print("[ui] passed")


if __name__ == "__main__":
    static_checks()
    paths_checks()
    python_checks()
    ui_checks()
    print("All audit smoke checks passed.")
