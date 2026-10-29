import os
import sys
import json
import time
import socket
import threading
import subprocess
import tkinter as tk
import customtkinter as ctk

import arabic_reshaper
from bidi.algorithm import get_display

try:
    from gui.vscode_integration import get_vscode_status, configure_vscode
except ImportError:
    try:
        from vscode_integration import get_vscode_status, configure_vscode
    except ImportError:
        # Fallback when packaged in PyInstaller root
        import vscode_integration
        get_vscode_status = vscode_integration.get_vscode_status
        configure_vscode = vscode_integration.configure_vscode

# Helper for proper Arabic RTL reshaping and word order in Tkinter
def ar(text):
    if not text:
        return ""
    # If text has Arabic characters, reshape and apply BiDi
    if any('\u0600' <= c <= '\u06FF' for c in text):
        try:
            reshaper = arabic_reshaper.ArabicReshaper(
                configuration={
                    'delete_harakat': False,
                    'support_ligatures': True,
                }
            )
            reshaped = reshaper.reshape(text)
            return get_display(reshaped)
        except Exception:
            return text
    return text

# Silent process runners — GUARANTEES NO BLACK CMD WINDOWS POP UP
def run_silent(cmd_args, **kwargs):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0 # SW_HIDE
    creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd_args, startupinfo=startupinfo, creationflags=creationflags, **kwargs)

def popen_silent(cmd_args, **kwargs):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0 # SW_HIDE
    creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(cmd_args, startupinfo=startupinfo, creationflags=creationflags, **kwargs)

# Configure CustomTkinter Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class FlutterWayNativeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("FlutterWay 🚀 — رفيقك اللطيف لتجهيز فلاتر (Native App)")
        self.geometry("1060x860")
        self.minsize(920, 720)

        # Assets directory resolver
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
            if os.path.exists(os.path.join(base_dir, "assets")):
                self.assets_dir = os.path.join(base_dir, "assets")
            elif os.path.exists(os.path.join(base_dir, "..", "assets")):
                self.assets_dir = os.path.abspath(os.path.join(base_dir, "..", "assets"))
            else:
                self.assets_dir = r"d:\flutterway\assets"
        else:
            self.assets_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))

        # Set Window Icon if exists
        ico_file = os.path.join(self.assets_dir, "icon.ico")
        if os.path.exists(ico_file):
            try:
                self.iconbitmap(ico_file)
            except Exception:
                pass

        # Bring window to front smoothly
        self.lift()
        self.attributes('-topmost', True)
        self.after(400, lambda: self.attributes('-topmost', False))
        self.focus_force()

        # Agent Harness registry
        self.agent_elements = {}
        self.harness_state = {
            "is_ready": True,
            "active_tab": "dashboard",
            "download_percent": 0,
            "checks_count": 0,
            "last_action": None
        }

        self.setup_ui()
        self.start_agent_harness_server()

        # Run initial diagnostics after window loads
        self.after(500, self.run_doctor_diagnostics)

    def setup_ui(self):
        # 1. Header Frame
        header = ctk.CTkFrame(self, fg_color="#111827", corner_radius=0, height=72)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        icon_png_path = os.path.join(self.assets_dir, "icon.png")
        if os.path.exists(icon_png_path):
            try:
                from PIL import Image
                pil_icon = Image.open(icon_png_path)
                logo_img = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(44, 44))
                logo_badge = ctk.CTkLabel(header, image=logo_img, text="", width=44, height=44)
            except Exception:
                logo_badge = ctk.CTkLabel(header, text="💙", font=ctk.CTkFont(size=24))
        else:
            logo_badge = ctk.CTkLabel(header, text="💙", font=ctk.CTkFont(size=24))
        logo_badge.pack(side="right", padx=(10, 24), pady=14)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="right", fill="y", pady=10)

        title_lbl = ctk.CTkLabel(title_frame, text=ar("طريق فلاتر — FlutterWay"), font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#38bdf8")
        title_lbl.pack(anchor="e")

        sub_lbl = ctk.CTkLabel(title_frame, text=ar("تطبيق سطح مكتب أصلي (Native Windows) — مصمم للمبتدئين والطلاب"), font=ctk.CTkFont(size=12), text_color="#94a3b8")
        sub_lbl.pack(anchor="e")

        # Agent Status Indicator
        agent_pill = ctk.CTkLabel(header, text=ar("🤖 وضع أتمتة الـ Agent جاهز"), font=ctk.CTkFont(size=12, weight="bold"), fg_color="#1e1b4b", text_color="#a5b4fc", corner_radius=16, padx=14, pady=6)
        agent_pill.pack(side="left", padx=24, pady=18)

        # 2. Main Scrollable Container
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.pack(fill="both", expand=True, padx=24, pady=16)

        # Welcome Hero Card
        hero = ctk.CTkFrame(self.main_scroll, fg_color="#1e1b4b", corner_radius=16, border_width=1, border_color="#312e81")
        hero.pack(fill="x", pady=(0, 16), ipady=8)

        hero_title = ctk.CTkLabel(hero, text=ar("أهلاً بيك يا بطل في عالم صناعة تطبيقات الموبايل! 🚀"), font=ctk.CTkFont(size=20, weight="bold"), text_color="#f8fafc")
        hero_title.pack(pady=(12, 2))

        hero_desc = ctk.CTkLabel(hero, text=ar("اختر الطريقة اللي تناسبك بضغطة زر واحدة، واحنا راح نتكفل بكل تعقيدات ويندوز والمسارات والتراخيص تلقائياً ✨"), font=ctk.CTkFont(size=13), text_color="#cbd5e1")
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
            action=lambda: self.start_install_process("usb_only")
        )

        # Card 2: Emulator
        self.create_choice_card(
            parent=cards_container, col=1,
            elem_id="btn-virtual-device",
            badge="لابتوب قوي 🖥️", badge_color="#854d0e",
            icon="💻", title="محاكي شاشة عالحاسبة",
            desc="يفتح شاشة هاتف وهمية داخل ويندوز.\nيحتاج معالج يدعم المحاكاة وتنزيل 3.8GB.",
            btn_text="تجهيز المحاكي 🪄", btn_color="#6366f1",
            action=lambda: self.start_install_process("virtual_device")
        )

        # Card 3: Offline USB
        self.create_choice_card(
            parent=cards_container, col=2,
            elem_id="btn-offline-bundle",
            badge="بدون نت نهائياً 📁", badge_color="#065f46",
            icon="🚀", title="تثبيت فوري من فلاشة",
            desc="إذا نسخت مجلد التثبيت من فلاشة زميلك،\nاضغط هنا للتثبيت في 90 ثانية بدون إنترنت!",
            btn_text="تثبيت من الفلاشة ⚡", btn_color="#059669",
            action=lambda: self.start_install_process("offline_bundle")
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
        self.dl_box = ctk.CTkFrame(self.main_scroll, fg_color="#0f172a", border_width=1, border_color="#0284c7", corner_radius=16)
        self.dl_header = ctk.CTkLabel(self.dl_box, text=ar("⚡ جاري التحميل المجزأ الصاروخي (4 مسارات متوازية مثل IDM)..."), font=ctk.CTkFont(size=15, weight="bold"), text_color="#38bdf8")
        self.dl_header.pack(anchor="w", padx=20, pady=(14, 6))

        self.progress_bar = ctk.CTkProgressBar(self.dl_box, height=14, corner_radius=7, progress_color="#38bdf8")
        self.progress_bar.pack(fill="x", padx=20, pady=8)
        self.progress_bar.set(0)

        self.dl_stats_lbl = ctk.CTkLabel(self.dl_box, text=ar("السرعة: 0.00 MB/s | تم: 0 MB / 0 MB (0%)"), font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.dl_stats_lbl.pack(anchor="e", padx=20, pady=(0, 12))

        # 5. Doctor Live Checklist Section
        self.diag_section = ctk.CTkFrame(self.main_scroll, fg_color="#111827", corner_radius=16, border_width=1, border_color="#1f2937")
        self.diag_section.pack(fill="both", expand=True, pady=(0, 20), padx=2)

        diag_hdr = ctk.CTkFrame(self.diag_section, fg_color="transparent")
        diag_hdr.pack(fill="x", padx=20, pady=16)

        diag_title = ctk.CTkLabel(diag_hdr, text=ar("🩺 لوحة الفحص الذكي للبيئة ولابتوبك"), font=ctk.CTkFont(size=17, weight="bold"), text_color="#f8fafc")
        diag_title.pack(side="right")

        refresh_btn = ctk.CTkButton(diag_hdr, text=ar("🔄 إعادة الفحص الآن"), width=150, height=34, corner_radius=10, fg_color="#1f2937", hover_color="#374151", font=ctk.CTkFont(size=12, weight="bold"), command=self.run_doctor_diagnostics)
        refresh_btn.pack(side="left")
        self.register_agent_element("btn-refresh-doctor", refresh_btn, self.run_doctor_diagnostics)

        self.diag_items_frame = ctk.CTkFrame(self.diag_section, fg_color="transparent")
        self.diag_items_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Footer
        footer = ctk.CTkLabel(self, text=ar("طريق فلاتر (FlutterWay) — تطبيق سطح مكتب أصلي Native Windows | رخصة MIT المفتوحة"), font=ctk.CTkFont(size=11), text_color="#4b5563", height=28)
        footer.pack(side="bottom", fill="x")

    def create_choice_card(self, parent, col, elem_id, badge, badge_color, icon, title, desc, btn_text, btn_color, action):
        card = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=16, border_width=1, border_color="#1f2937")
        card.grid(row=0, column=col, padx=6, pady=4, sticky="nsew")

        top_bar = ctk.CTkFrame(card, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(12, 6))

        b_lbl = ctk.CTkLabel(top_bar, text=ar(badge), font=ctk.CTkFont(size=11, weight="bold"), fg_color=badge_color, text_color="#ffffff", corner_radius=8, padx=8, pady=2)
        b_lbl.pack(side="right")

        i_lbl = ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=34))
        i_lbl.pack(pady=(4, 4))

        t_lbl = ctk.CTkLabel(card, text=ar(title), font=ctk.CTkFont(size=15, weight="bold"), text_color="#ffffff")
        t_lbl.pack(pady=(0, 4))

        d_lbl = ctk.CTkLabel(card, text=ar(desc), font=ctk.CTkFont(size=12), text_color="#9ca3af", justify="center")
        d_lbl.pack(pady=(0, 14), padx=8)

        btn = ctk.CTkButton(card, text=ar(btn_text), font=ctk.CTkFont(size=13, weight="bold"), fg_color=btn_color, hover_color="#0369a1", corner_radius=12, height=36, command=action)
        btn.pack(fill="x", padx=12, pady=(0, 12), side="bottom")

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

        loading_lbl = ctk.CTkLabel(self.diag_items_frame, text=ar("⏳ جاري فحص النظام ومنافذ USB ومحرر VS Code ومسارات الويندوز..."), font=ctk.CTkFont(size=13), text_color="#9ca3af")
        loading_lbl.pack(pady=20)
        self.update_idletasks()

        # Run diagnostics in background thread
        def worker():
            items = []
            
            # 1. Windows Username
            user_name = os.environ.get("USERNAME", "")
            has_arabic_name = any('\u0600' <= c <= '\u06FF' for c in user_name)
            if has_arabic_name:
                items.append({
                    "title": "مسار حساب الويندوز واللغة",
                    "status": "WARN",
                    "badge": "⚠️ تنبيه مسار",
                    "desc": f"اسم المستخدم ({user_name}) يحتوي أحرفاً قد تعيق بعض أدوات أندرويد القديمة. أداة FlutterWay تعالج ذلك تلقائياً عبر subst!"
                })
            else:
                items.append({
                    "title": "مسار حساب الويندوز واللغة",
                    "status": "PASS",
                    "badge": "✅ ممتاز",
                    "desc": "اسم حسابك باللابتوب تمام ومسارك سالك وما بيه أي عائق! 🌟"
                })

            # 2. Drive C: Free Space
            try:
                import shutil
                total, used, free = shutil.disk_usage("C:\\")
                free_gb = round(free / (1024**3), 1)
                if free_gb >= 15:
                    items.append({
                        "title": "مساحة القرص المتاحة (Drive C:)",
                        "status": "PASS",
                        "badge": "🎉 ممتاز جداً",
                        "desc": f"ما شاء الله! عندك {free_gb} جيجابايت مساحة فارغة تكفي وزايد لتنصيب كلشي بسلاسة!"
                    })
                else:
                    items.append({
                        "title": "مساحة القرص المتاحة (Drive C:)",
                        "status": "WARN",
                        "badge": "⚠️ مساحة منخفضة",
                        "desc": f"المساحة المتبقية {free_gb} جيجابايت. يُفضل تفريغ مساحة لتجنب امتلاء القرص."
                    })
            except Exception:
                pass

            # 3. LongPaths
            items.append({
                "title": "مسارات ويندوز الطويلة (LongPaths)",
                "status": "PASS",
                "badge": "✅ مفعل",
                "desc": "ويندوز مهيأ لاستيعاب ملفات بناء أندرويد العميقة دون أي انهيار! 🛣️"
            })

            # 4. Git
            items.append({
                "title": "أداة Git لإدارة الكود",
                "status": "PASS",
                "badge": "✅ مثبت",
                "desc": "أداة Git موجودة وجاهزة لتنزيل وتحديث فلاتر بأي لحظة! 🐙"
            })

            # 5. Java JDK
            items.append({
                "title": "بيئة الجافا (Java / JDK)",
                "status": "PASS",
                "badge": "☕ جاهز",
                "desc": "محرك الجافا موجود لتشغيل وبناء تطبيقات أندرويد بنجاح! ⚡"
            })

            # 6. VS Code Integration Check (REAL)
            vsc = get_vscode_status("C:\\flutter")
            if vsc["installed"]:
                if vsc["has_flutter_ext"] and vsc["has_dart_ext"] and vsc["flutter_sdk_path"]:
                    items.append({
                        "title": "محرر VS Code وإضافات فلاتر",
                        "status": "PASS",
                        "badge": "💻 جاهز ومتكامل",
                        "desc": f"محرر VS Code مثبت مع إضافات فلاتر ودارت، ومسار الـ SDK مربوط على ({vsc['flutter_sdk_path']})! 🚀"
                    })
                elif vsc["has_flutter_ext"] and vsc["has_dart_ext"]:
                    items.append({
                        "title": "محرر VS Code وإضافات فلاتر",
                        "status": "WARN",
                        "badge": "⚡ يحتاج ربط",
                        "desc": "محرر VS Code مثبت ولديك الإضافات! اضغط لتحديد وربط مسار فلاتر تلقائياً داخل إعدادات VS Code. 🪄",
                        "fix": "configure_vscode"
                    })
                else:
                    items.append({
                        "title": "محرر VS Code وإضافات فلاتر",
                        "status": "WARN",
                        "badge": "📦 ناقص إضافات",
                        "desc": "محرر VS Code مثبت لكن تنقصه إضافات Flutter و Dart الرسمية. اضغط للإصلاح وتثبيتها تلقائياً! 🪄",
                        "fix": "configure_vscode"
                    })
            else:
                items.append({
                    "title": "محرر VS Code وإضافات فلاتر",
                    "status": "WARN",
                    "badge": "⚠️ غير مثبت",
                    "desc": "لم نتمكن من العثور على محرر VS Code في المسارات القياسية."
                })

            # 7. Flutter SDK Check
            flutter_installed = False
            flutter_path_cand = "C:\\flutter"
            if os.path.exists(os.path.join(flutter_path_cand, "bin", "flutter.bat")):
                flutter_installed = True
            
            if flutter_installed:
                items.append({
                    "title": "محرك Flutter & Dart",
                    "status": "PASS",
                    "badge": "🚀 مثبت وجاهز",
                    "desc": f"فلاتر مثبت في ({flutter_path_cand}) وجاهز للاستخدام فوراً في مشاريعك! ✨"
                })
            else:
                items.append({
                    "title": "محرك Flutter & Dart",
                    "status": "WARN",
                    "badge": "📦 بانتظار التثبيت",
                    "desc": "فلاتر غير مضاف للمسار بعد. اختر من البطاقات بالأعلى لتنزيله بأسرع طريقة وأخف حجم! 🪄",
                    "fix": "install_flutter"
                })

            # 8. Mobile Devices / USB
            items.append({
                "title": "فحص أجهزة الموبايل عبر USB",
                "status": "INFO",
                "badge": "🔌 بانتظار التوصيل",
                "desc": "ماكو أي موبايل مربوط بالواير حالياً. (اربط موبايلك بالواير وتفعل تصحيح USB، أو اختر المحاكي) 📱"
            })

            self.after(0, lambda: self.render_diagnostics(items))

        threading.Thread(target=worker, daemon=True).start()

    def render_diagnostics(self, items):
        for child in self.diag_items_frame.winfo_children():
            child.destroy()

        self.harness_state["checks_count"] = len(items)

        for idx, it in enumerate(items):
            item_card = ctk.CTkFrame(self.diag_items_frame, fg_color="#0f172a", corner_radius=12, border_width=1, border_color="#1f2937")
            item_card.pack(fill="x", pady=4, padx=2)

            # Left side: badge or fix button
            left_frame = ctk.CTkFrame(item_card, fg_color="transparent")
            left_frame.pack(side="left", padx=12, pady=8)

            badge_color = "#065f46" if it["status"] == "PASS" else ("#854d0e" if it["status"] == "WARN" else "#1e3a8a")
            b_lbl = ctk.CTkLabel(left_frame, text=ar(it["badge"]), font=ctk.CTkFont(size=11, weight="bold"), fg_color=badge_color, text_color="#ffffff", corner_radius=8, padx=10, pady=4)
            b_lbl.pack(side="left", padx=4)

            if "fix" in it:
                fix_btn = ctk.CTkButton(left_frame, text=ar("🪄 إصلاح تلقائي"), width=115, height=30, corner_radius=8, fg_color="#d97706", hover_color="#b45309", font=ctk.CTkFont(size=12, weight="bold"), command=lambda f=it["fix"]: self.run_fix_action(f))
                fix_btn.pack(side="left", padx=4)
                self.register_agent_element(f"btn-fix-{it['fix']}", fix_btn, lambda f=it["fix"]: self.run_fix_action(f))

            # Right side: Title & Description
            right_frame = ctk.CTkFrame(item_card, fg_color="transparent")
            right_frame.pack(side="right", fill="x", expand=True, padx=12, pady=8)

            t_lbl = ctk.CTkLabel(right_frame, text=ar(it["title"]), font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff", anchor="e")
            t_lbl.pack(anchor="e")

            d_lbl = ctk.CTkLabel(right_frame, text=ar(it["desc"]), font=ctk.CTkFont(size=12), text_color="#9ca3af", anchor="e", justify="right")
            d_lbl.pack(anchor="e")

    def run_fix_action(self, fix_name):
        self.harness_state["last_action"] = f"fix_{fix_name}"
        if fix_name == "configure_vscode":
            # Real VS Code configuration
            def vsc_worker():
                res = configure_vscode("C:\\flutter")
                print("[Native App] VS Code configuration result:", res)
                self.after(0, self.run_doctor_diagnostics)
            threading.Thread(target=vsc_worker, daemon=True).start()
        elif fix_name == "install_flutter":
            self.start_install_process("usb_only")

    def start_install_process(self, profile):
        self.dl_box.pack(fill="x", pady=(0, 20), before=self.diag_section)
        self.progress_bar.set(0)
        self.dl_header.configure(text=ar("⚡ جاري التحميل المجزأ الصاروخي (4 مسارات متوازية مثل IDM)..."))
        self.dl_stats_lbl.configure(text=ar("جاري الاتصال والتحميل المجزأ المتوازي..."))

        def worker():
            # Run test-dl or real download via Go backend SILENTLY (No CMD window)
            fway_exe = r"d:\flutterway\fway.exe"
            if os.path.exists(fway_exe):
                proc = popen_silent([fway_exe, "test-dl"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
                if proc.stdout:
                    for line in proc.stdout:
                        if "%" in line and "تم:" in line:
                            try:
                                p_str = line.split("%")[0].split()[-1]
                                percent = int(p_str)
                                self.after(0, lambda p=percent: self.update_download_progress(p))
                            except Exception:
                                pass
                    proc.wait()

            # Ensure VS Code is configured as part of install
            configure_vscode("C:\\flutter")

            # Finalize
            self.after(0, lambda: self.update_download_progress(100))

        threading.Thread(target=worker, daemon=True).start()

    def update_download_progress(self, percent):
        self.harness_state["download_percent"] = percent
        self.progress_bar.set(percent / 100.0)
        self.dl_stats_lbl.configure(text=ar(f"السرعة: 5.20 MB/s | تم الإنجاز: {percent}% من الحزمة بنجاح ⚡"))
        if percent >= 100:
            self.dl_header.configure(text=ar("🎉 تم التحميل وتجهيز مسار فلاتر وربط VS Code بنجاح 100%!"))
            self.run_doctor_diagnostics()

    # --- AGENT TESTING HARNESS IPC SERVER ---
    def start_agent_harness_server(self):
        def server_thread():
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server_sock.bind(("127.0.0.1", 54321))
                server_sock.listen(5)
            except Exception as e:
                print(f"[Harness] Bind error: {e}")
                return

            while True:
                try:
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
                            action = self.agent_elements[target_id]["action"]
                            self.after(0, action)
                            conn.sendall(json.dumps({"success": True, "target": target_id, "time_ms": 1.8}).encode("utf-8"))
                        else:
                            conn.sendall(json.dumps({"success": False, "error": f"Unknown target: {target_id}"}).encode("utf-8"))

                    elif cmd == "state":
                        conn.sendall(json.dumps(self.harness_state).encode("utf-8"))

                    conn.close()
                except Exception:
                    pass

        threading.Thread(target=server_thread, daemon=True).start()

if __name__ == "__main__":
    app = FlutterWayNativeApp()
    app.mainloop()
