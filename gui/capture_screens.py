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
        context = browser.new_context(viewport={"width": 980, "height": 780})
        page = context.new_page()

        # ========================================================
        # 1. WIZARD VIEWS (STEPS 1 - 4)
        # ========================================================
        page.goto(html_url)
        page.wait_for_timeout(300)
        page.evaluate("switchMainView('wizard');")
        page.wait_for_timeout(200)

        # 1. Step 1 Dark Mode with Hardware Reality Benchmark
        page.click("#btn-check-laptop")
        page.wait_for_timeout(300)
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

        # 3. Step 2 Setup in progress (Level 2)
        page.evaluate("showStep(2); updateProgress(65, 'جاري تنزيل محرك Flutter & Dart الرسمي من السحابة...', 2);")
        page.wait_for_timeout(300)
        p3 = os.path.join(artifact_dir, "step2_progress.png")
        page.screenshot(path=p3)
        print("Captured:", p3)

        # 4. Step 3 Device Detection with Connected Tablet (HONOR JMS-W09)
        page.evaluate("""
        showStep(3);
        handleDeviceResponse({
            success: true,
            devices: [{ serial: 'AJ5EJK5913W00158', status: 'device', model: 'HONOR JMS-W09', is_ready: true }]
        });
        """)
        page.wait_for_timeout(300)
        p5 = os.path.join(artifact_dir, "step3_device_detected.png")
        page.screenshot(path=p5)
        print("Captured:", p5)

        # Step 3 with Live Build Diagnostics Console & Dynamic Commentary
        page.evaluate("""
        document.getElementById('btn-run-test').style.display = 'none';
        document.getElementById('device-guide-box').style.display = 'none';
        document.getElementById('device-ctrl-btns').style.display = 'none';
        document.getElementById('build-console').style.display = 'block';
        updateBuildTicker(28, '🔨 شغال على نار هادئة: المعالج دا يترجم كود Dart للغة الآلة الثنائية (ARM64) الخاصة بجهازك HONOR JMS-W09.', 2);
        """)
        page.wait_for_timeout(300)
        p5_build = os.path.join(artifact_dir, "step3_build_console.png")
        page.screenshot(path=p5_build)
        print("Captured:", p5_build)

        # Step 3 with celebration benchmark card on tablet
        page.evaluate("""
        document.getElementById('build-console').style.display = 'none';
        document.getElementById('benchmark-card').style.display = 'block';
        document.getElementById('benchmark-head-text').innerText = 'التطبيق يعمل الآن بنجاح على شاشة HONOR JMS-W09!';
        document.getElementById('stat-speed').innerText = '1.8 ثانية';
        """)
        page.wait_for_timeout(300)
        p5_bench = os.path.join(artifact_dir, "step3_benchmark_celebration.png")
        page.screenshot(path=p5_bench)
        print("Captured:", p5_bench)

        # Step 4 Cheatsheet & VS Code
        page.evaluate("showStep(4);")
        page.wait_for_timeout(300)
        p6 = os.path.join(artifact_dir, "step4_vscode_cheatsheet.png")
        page.screenshot(path=p6)
        print("Captured:", p6)

        # ========================================================
        # 2. STUDENT COMPANION DASHBOARD VIEWS
        # ========================================================
        # Switch to Companion View
        page.evaluate("switchMainView('companion');")
        page.wait_for_timeout(400)

        # Companion Tab 1: Smart Doctor
        page.evaluate("switchCompanionTab('doctor');")
        page.wait_for_timeout(300)
        c1 = os.path.join(artifact_dir, "companion_doctor.png")
        page.screenshot(path=c1)
        print("Captured:", c1)

        # Companion Tab 2: Lecture Projects Studio
        page.evaluate("""
        switchCompanionTab('projects');
        renderRecentProjects([
            { name: 'lecture_1_basics', path: 'C:\\\\Users\\\\gokoq\\\\Desktop\\\\FlutterProjects\\\\lecture_1_basics' },
            { name: 'lecture_2_widgets', path: 'C:\\\\Users\\\\gokoq\\\\Desktop\\\\FlutterProjects\\\\lecture_2_widgets' },
            { name: 'my_first_app', path: 'C:\\\\Users\\\\gokoq\\\\Desktop\\\\my_first_app' }
        ]);
        """)
        page.wait_for_timeout(300)
        c2 = os.path.join(artifact_dir, "companion_projects.png")
        page.screenshot(path=c2)
        print("Captured:", c2)

        # Companion Tab 3: Emergency Rescue Box
        page.evaluate("switchCompanionTab('rescue');")
        page.wait_for_timeout(300)
        c3 = os.path.join(artifact_dir, "companion_rescue.png")
        page.screenshot(path=c3)
        print("Captured:", c3)

        # Companion Tab 4: Connected Device Studio
        page.evaluate("""
        switchCompanionTab('device');
        document.getElementById('dev-val-name').innerText = 'HONOR JMS-W09';
        document.getElementById('dev-val-android').innerText = 'Android 15 (SDK 35)';
        document.getElementById('dev-val-battery').innerText = '100%';
        document.getElementById('dev-val-screen').innerText = '800x1340';
        document.getElementById('dev-val-abi').innerText = 'arm64-v8a';
        document.getElementById('dev-val-conn').innerText = 'USB عالي السرعة';
        """)
        page.wait_for_timeout(300)
        c4 = os.path.join(artifact_dir, "companion_device.png")
        page.screenshot(path=c4)
        print("Captured:", c4)

        # Companion Tab 5: Student Cheatsheet & Secrets
        page.evaluate("switchCompanionTab('cheatsheet');")
        page.wait_for_timeout(300)
        c5 = os.path.join(artifact_dir, "companion_cheatsheet.png")
        page.screenshot(path=c5)
        print("Captured:", c5)

        # Copy all screenshots to docs/screenshots in the repository
        docs_dir = r"d:\flutterway\docs\screenshots"
        os.makedirs(docs_dir, exist_ok=True)
        import shutil
        all_shots = [
            "step1_dark.png", "step1_light.png", "step2_progress.png",
            "step3_device_detected.png", "step3_build_console.png", "step3_benchmark_celebration.png",
            "step4_vscode_cheatsheet.png",
            "companion_doctor.png", "companion_projects.png", "companion_rescue.png",
            "companion_device.png", "companion_cheatsheet.png"
        ]
        for f in all_shots:
            src = os.path.join(artifact_dir, f)
            dst = os.path.join(docs_dir, f)
            if os.path.exists(src):
                shutil.copy2(src, dst)
        print("All 12 Screenshots synced to docs/screenshots/")

        browser.close()

if __name__ == "__main__":
    capture()
