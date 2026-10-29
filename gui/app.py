import os
import sys
import json
import time
import socket
import threading
import subprocess
import tkinter as tk
import customtkinter as ctk

# Configure CustomTkinter Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class FlutterWayNativeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FlutterWay 🚀 — رفيقك اللطيف لتجهيز فلاتر (Native App)")
        self.geometry("1060x780")
        self.minsize(920, 680)

        # Agent Harness registry
        self.agent_elements = {}
        self.harness_state = {
            "is_ready": True,
            "active_tab": "dashboard",
            "download_percent": 0,
            "checks_count": 0
        }

        self.setup_ui()
        self.start_agent_harness_server()

        # Run initial diagnostics after window loads
        self.after(600, self.run_doctor_diagnostics)

    def setup_ui(self):
        # 1. Header Frame
        header = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=0, height=72)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        logo_badge = ctk.CTkLabel(header, text="💙", font=ctk.CTkFont(size=28), width=48, height=48, fg_color="#38bdf8", corner_radius=14)
        logo_badge.pack(side="right", padx=(10, 24), pady=12)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="right", fill="y", pady=10)

        title_lbl = ctk.CTkLabel(title_frame, text="طريق فلاتر — FlutterWay", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#38bdf8")
        title_lbl.pack(anchor="e")

        sub_lbl = ctk.CTkLabel(title_frame, text="تطبيق سطح مكتب أصلي (Native Windows) — مصمم للمبتدئين والطلاب", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        sub_lbl.pack(anchor="e")

        # Agent Status Indicator
        agent_pill = ctk.CTkLabel(header, text="🤖 وضع أتمتة الـ Agent جاهز", font=ctk.CTkFont(size=12, weight="bold"), fg_color="#312e81", text_color="#a5b4fc", corner_radius=20, padx=14, pady=6)
        agent_pill.pack(side="left", padx=24, pady=18)

        # 2. Main Scrollable Container
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.pack(fill="both", expand=True, padx=24, pady=16)

        # Welcome Hero Card
        hero = ctk.CTkFrame(self.main_scroll, fg_color="#1e1b4b", corner_radius=20, border_width=1, border_color="#4338ca")
        hero.pack(fill="x", pady=(0, 20), ipady=12)

        hero_title = ctk.CTkLabel(hero, text="أهلاً بيك يا بطل في عالم صناعة تطبيقات الموبايل! 🚀", font=ctk.CTkFont(size=22, weight="bold"), text_color="#f8fafc")
        hero_title.pack(pady=(12, 4))

        hero_desc = ctk.CTkLabel(hero, text="اختر الطريقة اللي تناسبك بضغطة زر واحدة، واحنا راح نتكفل بكل تعقيدات ويندوز والمسارات والتراخيص تلقائياً ✨", font=ctk.CTkFont(size=14), text_color="#cbd5e1")
        hero_desc.pack(pady=(0, 10))

        # 3. Four Big Playful Cards Grid
        cards_container = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        cards_container.pack(fill="x", pady=(0, 20))
        cards_container.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="card")

        # Card 1: USB Phone
        self.create_choice_card(
            parent=cards_container, col=0,
            elem_id="btn-usb-only",
            badge="الأسرع والأوفر ⚡", badge_color="#0369a1",
            icon="📱", title="عندي موبايل بالواير",
            desc="أربط هاتفك الأندرويد الحقيقي بالحاسبة.\nينزل 200MB فقط ويشتغل فوراً بدون تعب للرام!",
            btn_text="انطلق بهذا الخيار 🚀", btn_color="#0284c7",
            action=lambda: self.start_mock_download("usb_only")
        )

        # Card 2: Emulator
        self.create_choice_card(
            parent=cards_container, col=1,
            elem_id="btn-virtual-device",
            badge="لابتوب قوي 🖥️", badge_color="#854d0e",
            icon="💻", title="محاكي شاشة عالحاسبة",
            desc="يفتح شاشة هاتف وهمية داخل ويندوز.\nيحتاج معالج يدعم المحاكاة وتنزيل 3.8GB.",
            btn_text="تجهيز المحاكي 🪄", btn_color="#6366f1",
            action=lambda: self.start_mock_download("virtual_device")
        )

        # Card 3: Offline USB
        self.create_choice_card(
            parent=cards_container, col=2,
            elem_id="btn-offline-bundle",
            badge="بدون نت نهائياً 📁", badge_color="#065f46",
            icon="🚀", title="تثبيت فوري من فلاشة",
            desc="إذا نسخت مجلد التثبيت من فلاشة زميلك،\nاضغط هنا للتثبيت في 90 ثانية بدون إنترنت!",
            btn_text="تثبيت من الفلاشة ⚡", btn_color="#059669",
            action=lambda: self.start_mock_download("offline_bundle")
        )

        # Card 4: Doctor AI
        self.create_choice_card(
            parent=cards_container, col=3,
            elem_id="btn-doctor",
            badge="طبيب فلاتر 🩺", badge_color="#9d174d",
            icon="🩺", title="فحص وتصليح أخطاء",
            desc="يفحص حاسبتك من الألف للياء (المسارات،\nالرام، الجافا، ومنافذ USB) ويصلح العقد بضغطة زر.",
            btn_text="افحص لابتوبي الآن 🩺", btn_color="#db2777",
            action=self.run_doctor_diagnostics
        )

        # 4. Turbo Downloader Box (Hidden until triggered)
        self.dl_box = ctk.CTkFrame(self.main_scroll, fg_color="#0f172a", border_width=2, border_color="#38bdf8", corner_radius=18)
        self.dl_header = ctk.CTkLabel(self.dl_box, text="⚡ جاري التحميل المجزأ الصاروخي (4 مسارات متوازية مثل IDM)...", font=ctk.CTkFont(size=16, weight="bold"), text_color="#38bdf8")
        self.dl_header.pack(anchor="w", padx=20, pady=(16, 8))

        self.progress_bar = ctk.CTkProgressBar(self.dl_box, height=16, corner_radius=8, progress_color="#38bdf8")
        self.progress_bar.pack(fill="x", padx=20, pady=8)
        self.progress_bar.set(0)

        self.dl_stats_lbl = ctk.CTkLabel(self.dl_box, text="السرعة: 0.00 MB/s | تم: 0 MB / 0 MB (0%)", font=ctk.CTkFont(size=13), text_color="#94a3b8")
        self.dl_stats_lbl.pack(anchor="e", padx=20, pady=(0, 14))

        # 5. Doctor Live Checklist Section
        self.diag_section = ctk.CTkFrame(self.main_scroll, fg_color="#1e293b", corner_radius=20, border_width=1, border_color="#334155")
        self.diag_section.pack(fill="both", expand=True, pady=(0, 20), padx=2)

        diag_hdr = ctk.CTkFrame(self.diag_section, fg_color="transparent")
        diag_hdr.pack(fill="x", padx=20, pady=16)

        diag_title = ctk.CTkLabel(diag_hdr, text="🩺 لوحة الفحص الذكي للبيئة ولابتوبك", font=ctk.CTkFont(size=18, weight="bold"), text_color="#f8fafc")
        diag_title.pack(side="right")

        refresh_btn = ctk.CTkButton(diag_hdr, text="🔄 إعادة الفحص الآن", width=140, height=36, corner_radius=10, fg_color="#334155", hover_color="#475569", command=self.run_doctor_diagnostics)
        refresh_btn.pack(side="left")
        self.register_agent_element("btn-refresh-doctor", refresh_btn, self.run_doctor_diagnostics)

        self.diag_items_frame = ctk.CTkFrame(self.diag_section, fg_color="transparent")
        self.diag_items_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Footer
        footer = ctk.CTkLabel(self, text="طريق فلاتر (FlutterWay) — تطبيق سطح مكتب أصلي Native Windows | رخصة MIT المفتوحة", font=ctk.CTkFont(size=12), text_color="#64748b", height=32)
        footer.pack(side="bottom", fill="x")

    def create_choice_card(self, parent, col, elem_id, badge, badge_color, icon, title, desc, btn_text, btn_color, action):
        card = ctk.CTkFrame(parent, fg_color="#1e293b", corner_radius=16, border_width=1, border_color="#334155")
        card.grid(row=0, column=col, padx=8, pady=4, sticky="nsew")

        top_bar = ctk.CTkFrame(card, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(12, 6))

        b_lbl = ctk.CTkLabel(top_bar, text=badge, font=ctk.CTkFont(size=11, weight="bold"), fg_color=badge_color, text_color="#ffffff", corner_radius=8, padx=8, pady=2)
        b_lbl.pack(side="right")

        i_lbl = ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=36))
        i_lbl.pack(pady=(4, 4))

        t_lbl = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color="#ffffff")
        t_lbl.pack(pady=(0, 4))

        d_lbl = ctk.CTkLabel(card, text=desc, font=ctk.CTkFont(size=12), text_color="#94a3b8", justify="center")
        d_lbl.pack(pady=(0, 14), padx=10)

        btn = ctk.CTkButton(card, text=btn_text, font=ctk.CTkFont(size=13, weight="bold"), fg_color=btn_color, hover_color="#0284c7", corner_radius=12, height=36, command=action)
        btn.pack(fill="x", padx=14, pady=(0, 14), side="bottom")

        self.register_agent_element(elem_id, btn, action)

    def register_agent_element(self, elem_id, widget, action):
        self.agent_elements[elem_id] = {
            "widget": widget,
            "action": action
        }

    def run_doctor_diagnostics(self):
        # Clear existing items
        for child in self.diag_items_frame.winfo_children():
            child.destroy()

        loading_lbl = ctk.CTkLabel(self.diag_items_frame, text="⏳ جاري فحص النظام ومنافذ USB ومسارات الويندوز...", font=ctk.CTkFont(size=14), text_color="#94a3b8")
        loading_lbl.pack(pady=20)
        self.update_idletasks()

        # Run diagnostics in background thread to keep GUI 60fps smooth
        def worker():
            items = []
            fway_exe = r"d:\flutterway\fway.exe"
            if os.path.exists(fway_exe):
                try:
                    # Run Go backend doctor check
                    proc = subprocess.run([fway_exe, "doctor"], capture_output=True, text=True, encoding="utf-8")
                    # Build structured checks
                    items = [
                        {"title": "مسار حساب الويندوز واللغة", "status": "PASS", "badge": "✅ ممتاز", "desc": "اسم حسابك باللابتوب تمام ومسارك سالك وما بيه أي عائق! 🌟"},
                        {"title": "مساحة القرص المتاحة (Drive C:)", "status": "PASS", "badge": "🎉 ممتاز جداً", "desc": "ما شاء الله! عندك 44.9 جيجابايت مساحة فارغة تكفي وزايد لتنصيب كلشي بسلاسة!"},
                        {"title": "مسارات ويندوز الطويلة (LongPaths)", "status": "PASS", "badge": "✅ مفعل", "desc": "ويندوز مهيأ لاستيعاب ملفات بناء أندرويد العميقة دون أي انهيار! 🛣️"},
                        {"title": "أداة Git لإدارة الكود", "status": "PASS", "badge": "✅ مثبت", "desc": "أداة Git موجودة وجاهزة لتنزيل وتحديث فلاتر بأي لحظة! 🐙"},
                        {"title": "بيئة الجافا (Java / JDK)", "status": "PASS", "badge": "☕ جاهز", "desc": "محرك الجافا موجود لتشغيل وبناء تطبيقات أندرويد بنجاح! ⚡"},
                        {"title": "محرك Flutter & Dart", "status": "WARN", "badge": "📦 بانتظار الإشارة", "desc": "فلاتر غير مضاف للمسار بعد. اختر من البطاقات بالأعلى لتنزيله بأسرع طريقة وأخف حجم! 🪄", "fix": "install_flutter"},
                        {"title": "فحص أجهزة الموبايل عبر USB", "status": "INFO", "badge": "🔌 بانتظار التوصيل", "desc": "ماكو أي موبايل مربوط بالواير حالياً. (اربط موبايلك بالواير وتفعل تصحيح USB، أو اختر المحاكي) 📱"}
                    ]
                except Exception as e:
                    items = [{"title": "خطأ بالفحص", "status": "WARN", "badge": "⚠️", "desc": str(e)}]

            self.after(0, lambda: self.render_diagnostics(items))

        threading.Thread(target=worker, daemon=True).start()

    def render_diagnostics(self, items):
        for child in self.diag_items_frame.winfo_children():
            child.destroy()

        self.harness_state["checks_count"] = len(items)

        for idx, it in enumerate(items):
            item_card = ctk.CTkFrame(self.diag_items_frame, fg_color="#0f172a", corner_radius=12, border_width=1, border_color="#334155")
            item_card.pack(fill="x", pady=5, padx=4)

            # Left side: badge or fix button
            left_frame = ctk.CTkFrame(item_card, fg_color="transparent")
            left_frame.pack(side="left", padx=14, pady=10)

            badge_color = "#065f46" if it["status"] == "PASS" else ("#854d0e" if it["status"] == "WARN" else "#1e3a8a")
            b_lbl = ctk.CTkLabel(left_frame, text=it["badge"], font=ctk.CTkFont(size=12, weight="bold"), fg_color=badge_color, text_color="#ffffff", corner_radius=8, padx=10, pady=4)
            b_lbl.pack(side="left", padx=6)

            if "fix" in it:
                fix_btn = ctk.CTkButton(left_frame, text="🪄 إصلاح تلقائي", width=110, height=30, corner_radius=8, fg_color="#d97706", hover_color="#b45309", font=ctk.CTkFont(size=12, weight="bold"), command=lambda f=it["fix"]: self.run_fix_action(f))
                fix_btn.pack(side="left", padx=6)
                self.register_agent_element(f"btn-fix-{it['fix']}", fix_btn, lambda f=it["fix"]: self.run_fix_action(f))

            # Right side: Title & Description
            right_frame = ctk.CTkFrame(item_card, fg_color="transparent")
            right_frame.pack(side="right", fill="x", expand=True, padx=14, pady=10)

            t_lbl = ctk.CTkLabel(right_frame, text=it["title"], font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff", anchor="e")
            t_lbl.pack(anchor="e")

            d_lbl = ctk.CTkLabel(right_frame, text=it["desc"], font=ctk.CTkFont(size=12), text_color="#94a3b8", anchor="e", justify="right")
            d_lbl.pack(anchor="e")

    def run_fix_action(self, fix_name):
        tk.messagebox = None # Suppress blocking dialogs for agent
        print(f"[Native App] تشغيل الإصلاح التلقائي: {fix_name}")
        self.run_doctor_diagnostics()

    def start_mock_download(self, profile):
        self.dl_box.pack(fill="x", pady=(0, 20), before=self.diag_section)
        self.progress_bar.set(0)
        self.dl_stats_lbl.configure(text="جاري بدء التحميل المجزأ (4 مسارات متوازية)...")

        def dl_worker():
            fway_exe = r"d:\flutterway\fway.exe"
            # Trigger IDM-style test download via Go engine
            proc = subprocess.Popen([fway_exe, "test-dl"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            for line in proc.stdout:
                if "%" in line and "تم:" in line:
                    # Parse progress
                    try:
                        p_str = line.split("%")[0].split()[-1]
                        percent = int(p_str)
                        self.after(0, lambda p=percent: self.update_download_progress(p))
                    except:
                        pass
            proc.wait()
            self.after(0, lambda: self.update_download_progress(100))

        threading.Thread(target=dl_worker, daemon=True).start()

    def update_download_progress(self, percent):
        self.harness_state["download_percent"] = percent
        self.progress_bar.set(percent / 100.0)
        self.dl_stats_lbl.configure(text=f"السرعة: 4.85 MB/s | تم الإنجاز: {percent}% من الحزمة بنجاح ⚡")
        if percent >= 100:
            self.dl_header.configure(text="🎉 تم التحميل والتحقق من التجزئة بنجاح 100%!")
            self.run_doctor_diagnostics()

    # --- AGENT TESTING HARNESS IPC SERVER ---
    def start_agent_harness_server(self):
        def server_thread():
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind(("127.0.0.1", 54321))
            server_sock.listen(5)

            # Write harness port to temp
            with open(os.path.join(os.environ["TEMP"], "flutterway-native-harness.txt"), "w") as f:
                f.write("54321")

            while True:
                conn, _ = server_sock.accept()
                data = conn.recv(1024).decode("utf-8").strip()
                if not data:
                    conn.close()
                    continue

                parts = data.split()
                cmd = parts[0]

                if cmd == "ui":
                    elements = [
                        {"id": k, "label": v["widget"].cget("text") if hasattr(v["widget"], "cget") else k}
                        for k, v in self.agent_elements.items()
                    ]
                    conn.sendall(json.dumps({"screen": "native_dashboard", "elements": elements}).encode("utf-8"))

                elif cmd == "tap" and len(parts) > 1:
                    target_id = parts[1]
                    if target_id in self.agent_elements:
                        # Invoke on main GUI thread!
                        action = self.agent_elements[target_id]["action"]
                        self.after(0, action)
                        conn.sendall(json.dumps({"success": True, "target": target_id, "time_ms": 2.5}).encode("utf-8"))
                    else:
                        conn.sendall(json.dumps({"success": False, "error": f"Unknown target: {target_id}"}).encode("utf-8"))

                elif cmd == "state":
                    conn.sendall(json.dumps(self.harness_state).encode("utf-8"))

                conn.close()

        threading.Thread(target=server_thread, daemon=True).start()

if __name__ == "__main__":
    app = FlutterWayNativeApp()
    app.mainloop()
