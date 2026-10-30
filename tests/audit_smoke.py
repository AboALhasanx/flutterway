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
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "gui" / "onboarding_app.py"
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
    print("[static] passed")


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
            "finishRealBuild({success: true, installed_ok: true, device_name: 'Test Phone', build_time: '5s'})"
        )
        page.wait_for_timeout(850)
        assert page.locator("#benchmark-card").is_visible()
        assert "Test Phone" in page.locator("#benchmark-head-text").inner_text()

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
    ui_checks()
    print("All audit smoke checks passed.")
