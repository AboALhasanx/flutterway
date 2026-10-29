import os
import sys
import time
from playwright.sync_api import sync_playwright

def capture():
    artifact_dir = r"C:\Users\gokoq\.gemini\antigravity\brain\a38af0e8-6f8b-43e7-9d7e-22497a7da4b0"
    html_url = "file:///d:/flutterway/gui/onboarding/index.html"

    chrome_exe = r"C:\Users\gokoq\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
    if not os.path.exists(chrome_exe):
        chrome_exe = r"C:\Program Files (x86)\Microsoft\EdgeCore\147.0.3912.60\msedge.exe"

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_exe, headless=True)
        context = browser.new_context(viewport={"width": 980, "height": 740})
        page = context.new_page()

        # 1. Step 1 Dark Mode
        page.goto(html_url)
        page.wait_for_timeout(300)
        # Click check laptop
        page.click("#btn-check-laptop")
        page.wait_for_timeout(400)
        p1 = os.path.join(artifact_dir, "step1_dark.png")
        page.screenshot(path=p1)
        print("Captured:", p1)

        # 2. Step 1 Light Mode
        page.click("#btn-theme-toggle")
        page.wait_for_timeout(300)
        p2 = os.path.join(artifact_dir, "step1_light.png")
        page.screenshot(path=p2)
        print("Captured:", p2)

        # Toggle back to dark
        page.click("#btn-theme-toggle")
        page.wait_for_timeout(200)

        # 3. Step 2 Setup in progress
        page.evaluate("showStep(2); updateProgress(65, 'جاري تنزيل محرك Flutter & Dart الرسمي من السحابة...', 2);")
        page.wait_for_timeout(300)
        p3 = os.path.join(artifact_dir, "step2_progress.png")
        page.screenshot(path=p3)
        print("Captured:", p3)

        # 4. Step 3 Phone Connect & Live Test
        page.evaluate("showStep(3);")
        page.wait_for_timeout(300)
        p4 = os.path.join(artifact_dir, "step3_device_connect.png")
        page.screenshot(path=p4)
        print("Captured:", p4)

        # Step 3 with detected phone state
        page.evaluate("""
        handleDeviceResponse({
            success: true,
            devices: [{ serial: 'AJ5EJK5913W00158', status: 'device', model: 'Huawei MatePad (JMS-W09)', is_ready: true }]
        });
        """)
        page.wait_for_timeout(300)
        p5 = os.path.join(artifact_dir, "step3_device_detected.png")
        page.screenshot(path=p5)
        print("Captured:", p5)

        # 5. Step 4 Cheatsheet & VS Code
        page.evaluate("showStep(4);")
        page.wait_for_timeout(300)
        p6 = os.path.join(artifact_dir, "step4_vscode_cheatsheet.png")
        page.screenshot(path=p6)
        print("Captured:", p6)

        browser.close()

if __name__ == "__main__":
    capture()
