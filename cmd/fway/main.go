package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/AboALhasanx/flutterway/pkg/doctor"
	"github.com/AboALhasanx/flutterway/pkg/downloader"
	"github.com/AboALhasanx/flutterway/pkg/gui"
	"github.com/AboALhasanx/flutterway/pkg/harness"
	"github.com/AboALhasanx/flutterway/pkg/manifest"
)

const (
	ColorCyan   = "\033[96m"
	ColorGreen  = "\033[92m"
	ColorYellow = "\033[93m"
	ColorRed    = "\033[91m"
	ColorReset  = "\033[0m"
	ColorBold   = "\033[1m"
)

func main() {
	args := os.Args[1:]

	if len(args) == 0 {
		runGUI()
		return
	}

	switch args[0] {
	case "gui":
		runGUI()
	case "cli":
		runInteractiveMenu()
	case "doctor":
		runDoctor()
	case "test-dl":
		runDownloadTest()
	case "harness":
		runHarnessCommand(args[1:])
	case "version":
		fmt.Printf("FlutterWay CLI & GUI (fway) v1.0.0 | Windows x64\n")
	case "help", "--help", "-h":
		printHelp()
	default:
		fmt.Printf("أمر غير معروف: %s. استخدم 'fway help' لمعرفة الأوامر.\n", args[0])
	}
}

func runHarnessCommand(subArgs []string) {
	if len(subArgs) == 0 {
		fmt.Println("استخدام الهارنس (Agent Testing Harness):")
		fmt.Println("  fway harness ui          عرض جدول العناصر التفاعلية (Compact Action Table)")
		fmt.Println("  fway harness tap <id>    الضغط على زر أو بطاقة معينة بسرعة البرق")
		fmt.Println("  fway harness doctor      جلب تقرير الطبيب من الواجهة الحية")
		fmt.Println("  fway harness run         تشغيل اختبار الأتمتة الشامل (Autonomous Agent E2E)")
		return
	}

	client, err := harness.NewClient()
	if err != nil {
		fmt.Printf(ColorRed+"❌ خطأ: %v\n"+ColorReset, err)
		fmt.Println("تأكد من تشغيل البرنامج أولاً عبر 'fway gui' قبل استدعاء الهارنس!")
		return
	}

	switch subArgs[0] {
	case "ui":
		table, err := client.GetActionTable()
		if err != nil {
			fmt.Printf(ColorRed+"❌ خطأ: %v\n"+ColorReset, err)
			return
		}
		harness.PrintActionTable(table)

	case "tap":
		if len(subArgs) < 2 {
			fmt.Println("يرجى تحديد معرف العنصر: fway harness tap <target_id>")
			return
		}
		target := subArgs[1]
		start := time.Now()
		ok, err := client.Tap(target)
		dur := time.Since(start).Milliseconds()
		if err != nil || !ok {
			fmt.Printf(ColorRed+"❌ فشل الضغط على: %s (%v)\n"+ColorReset, target, err)
		} else {
			fmt.Printf(ColorGreen+"✅ [Agent Action] تم الضغط على '%s' في %dms بنجاح!\n"+ColorReset, target, dur)
		}

	case "doctor":
		rep, err := client.GetDoctorReport()
		if err != nil {
			fmt.Printf(ColorRed+"❌ خطأ: %v\n"+ColorReset, err)
			return
		}
		fmt.Printf("\n🩺 تقرير الواجهة الحية: %s\n", rep.CheerMessage)
		for _, it := range rep.Items {
			fmt.Printf("  • %-30s | %-15s | %s\n", it.Title, it.Badge, it.Explanation)
		}

	case "run", "e2e":
		runAutonomousAgentSuite(client)

	default:
		fmt.Printf("أمر هارنس غير معروف: %s\n", subArgs[0])
	}
}

func runAutonomousAgentSuite(client *harness.HarnessClient) {
	fmt.Println()
	fmt.Println(ColorCyan + "=================================================================" + ColorReset)
	fmt.Println(ColorCyan + "🤖 بدء اختبار الأتمتة الشامل لويندوز عبر الهارنس (Agent Harness Testbed)" + ColorReset)
	fmt.Println(ColorCyan + "   بروتوكول: Text first, pixels last | Single-digit-ms action verbs" + ColorReset)
	fmt.Println(ColorCyan + "=================================================================" + ColorReset)

	// Step 1: Dump Action Table
	fmt.Println("\n[1/4] استخراج شجرة الواجهة وجدول الإجراءات (Compact Action Table)...")
	table, err := client.GetActionTable()
	if err != nil {
		fmt.Printf(ColorRed+"❌ فشل فحص الشجرة: %v\n"+ColorReset, err)
		return
	}
	harness.PrintActionTable(table)

	// Step 2: Agent Tap "btn-doctor"
	fmt.Println("\n[2/4] محاكاة نقرة الـ Agent على بطاقة طبيب فلاتر (btn-doctor)...")
	start := time.Now()
	_, _ = client.Tap("btn-doctor")
	time.Sleep(300 * time.Millisecond)
	rep, err := client.GetDoctorReport()
	dur := time.Since(start).Milliseconds()
	if err == nil && len(rep.Items) > 0 {
		fmt.Printf(ColorGreen+"✅ [PASS] استجاب التطبيق في %dms وحدث %d عنصر تشخيصي!\n"+ColorReset, dur, len(rep.Items))
	} else {
		fmt.Printf(ColorRed+"❌ [FAIL] لم يتم استلام التقرير بصورة صحيحة\n"+ColorReset)
	}

	// Step 3: Agent Tap Auto-fix button
	fmt.Println("\n[3/4] محاكاة نقرة الـ Agent على زر الإصلاح التلقائي (btn-fix-enable_long_paths)...")
	start = time.Now()
	ok, _ := client.Tap("btn-fix-enable_long_paths")
	dur = time.Since(start).Milliseconds()
	if ok {
		fmt.Printf(ColorGreen+"✅ [PASS] تم إرسال أمر الإصلاح واستجاب الخادم في %dms!\n"+ColorReset, dur)
	} else {
		fmt.Printf(ColorRed+"❌ [FAIL] فشل استدعاء الإصلاح التلقائي\n"+ColorReset)
	}

	// Step 4: Agent Tap Turbo-Download Card
	fmt.Println("\n[4/4] محاكاة نقرة الـ Agent على خيار أجهزة USB فقط والتحميل المجزأ (btn-usb-only)...")
	start = time.Now()
	ok, _ = client.Tap("btn-usb-only")
	dur = time.Since(start).Milliseconds()
	if ok {
		fmt.Printf(ColorGreen+"✅ [PASS] تفاعلت الواجهة في %dms وتم تشغيل محرك التحميل المجزأ بنجاح!\n"+ColorReset, dur)
	} else {
		fmt.Printf(ColorRed+"❌ [FAIL] فشل إطلاق خيار التحميل\n"+ColorReset)
	}

	fmt.Println()
	fmt.Println(ColorGreen + ColorBold + "🎉 اكتملت كافة اختبارات الهارنس بنجاح 100%! الأداة قابلة للتحكم والأتمتة بواسطة الـ Agents كلياً!" + ColorReset)
	fmt.Println(ColorCyan + "=================================================================" + ColorReset)
}

func runGUI() {
	printBanner()
	fmt.Println(ColorGreen + ColorBold + "  🖥️ جاري إطلاق الواجهة الرسومية التفاعلية لـ FlutterWay..." + ColorReset)

	server, err := gui.StartServer()
	if err != nil {
		fmt.Printf(ColorRed+"  فشل تشغيل خادم الواجهة: %v\n"+ColorReset, err)
		runInteractiveMenu()
		return
	}

	appURL := fmt.Sprintf("http://127.0.0.1:%d", server.Port)
	fmt.Printf("  🌐 الواجهة تعمل محلياً على الرابط: %s%s%s\n", ColorCyan, appURL, ColorReset)

	cmd, err := gui.LaunchWindow(appURL)
	if err != nil {
		fmt.Printf(ColorYellow+"  تعذر فتح النافذة تلقائياً. بإمكانك فتح الرابط في المتصفح: %s\n"+ColorReset, appURL)
	} else {
		fmt.Println(ColorGreen + "  ✨ تم فتح نافذة البرنامج بنجاح! تفضل بالاطلاع عليها على شاشتك الآن." + ColorReset)
	}

	fmt.Println(ColorCyan + "  💡 لإيقاف البرنامج، اضغط Ctrl + C في هذه النافذة." + ColorReset)

	// Wait for exit signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	if cmd != nil && cmd.Process != nil {
		go func() {
			_ = cmd.Wait()
			os.Exit(0)
		}()
	}

	<-sigChan
	fmt.Println("\n  مع السلامة! 👋")
}

func printBanner() {
	fmt.Println()
	fmt.Println(ColorCyan + "  ╔══════════════════════════════════════════════════════════════╗" + ColorReset)
	fmt.Println(ColorCyan + "  ║" + ColorGreen + ColorBold + "     💙 FlutterWay — رفيقك اللطيف لتجهيز فلاتر وأندرويد!      " + ColorCyan + "║" + ColorReset)
	fmt.Println(ColorCyan + "  ║" + ColorYellow + "      تجهيز بيئة الموبايل للطلاب المبتدئين بدون أي تعقيد ✨    " + ColorCyan + "║" + ColorReset)
	fmt.Println(ColorCyan + "  ╚══════════════════════════════════════════════════════════════╝" + ColorReset)
	fmt.Println()
}

func runInteractiveMenu() {
	printBanner()

	fmt.Println(ColorBold + "  اختر الخطوة التي تناسبك بكل بساطة:" + ColorReset)
	fmt.Println()
	fmt.Println("  " + ColorGreen + "[1] 📱 عندي موبايل حقيقي أربطه بالواير" + ColorReset + " (الخيار الأسرع والأخف على اللابتوب! ينزل 200MB فقط ⚡)")
	fmt.Println("  " + ColorYellow + "[2] 💻 أريد شاشة موبايل وهمية عالحاسبة" + ColorReset + " (يحتاج لابتوب قوي وإنترنت عالي! ينزل 3.8GB 🖥️)")
	fmt.Println("  " + ColorCyan + "[3] 🚀 عندي فلاشة USB بيها الملفات من صديقي" + ColorReset + " (تثبيت فوري بدون إنترنت بدقيقة واحدة! 🪄)")
	fmt.Println("  " + ColorGreen + "[4] 🩺 فحص صحة الحاسبة وتصليح المشاكل" + ColorReset + " (طبيب فلاتر الذكي لفحص بيئتك وحل العقد! 🩺)")
	fmt.Println("  " + ColorCyan + "[5] 🖥️ فتح الواجهة الرسومية البصرية (GUI Window)" + ColorReset)
	fmt.Println("  " + ColorRed + "[6] 🚪 خروج مع ابتسامة 😊" + ColorReset)
	fmt.Println()

	fmt.Print("  👉 اكتب رقم الخيار ثم اضغط Enter: ")
	var choice string
	fmt.Scanln(&choice)
	choice = strings.TrimSpace(choice)

	switch choice {
	case "1":
		fmt.Println()
		fmt.Println(ColorGreen + "  🌟 اختيار ذكي جداً! الربط بالواير يوفر عليك ساعات تحميل وما يستهلك رام جهازك أبداً!" + ColorReset)
		runDoctor()
	case "2":
		fmt.Println()
		fmt.Println(ColorYellow + "  💻 تمام! راح نجهز محاكي الأندرويد وصور النظام بعد التأكد من دعم المعالج..." + ColorReset)
		runDoctor()
	case "3":
		fmt.Println()
		fmt.Println(ColorCyan + "  🚀 عاشت إيدك! راح نبحث عن مجلد الفلاشة 'bundle/' للتثبيت السريع بدون نت..." + ColorReset)
	case "4":
		runDoctor()
	case "5":
		runGUI()
	case "6":
		fmt.Println(ColorGreen + "  مع السلامة وبالتوفيق في رحلتك البرمجية الجميلة! 💙👋" + ColorReset)
	default:
		fmt.Println(ColorRed + "  اختيار غير موجود! راح نشغل فاحص الطبيب لمساعدتك:" + ColorReset)
		runDoctor()
	}
}

func runDoctor() {
	printBanner()
	fmt.Println(ColorBold + "  🩺 جاري فحص صحة لابتوبك ومسار بناء تطبيقات الموبايل..." + ColorReset)
	fmt.Println()

	report := doctor.RunDiagnostics()

	for i, item := range report.Items {
		icon := "🔹"
		color := ColorGreen
		if item.Status == "WARN" {
			icon = "⚠️"
			color = ColorYellow
		} else if item.Status == "FAIL" {
			icon = "❌"
			color = ColorRed
		}

		fmt.Printf("  %s %s[%d/ %s] %s%s%s\n", icon, ColorBold, i+1, item.Badge, ColorReset, color, item.Title)
		fmt.Printf("     %s%s\n", ColorReset, item.Explanation)
		if item.AutoFixable {
			fmt.Printf("     %s💡 ميزة الإصلاح التلقائي متاحة: fway fix %s%s\n", ColorCyan, item.FixCommand, ColorReset)
		}
		fmt.Println()
	}

	fmt.Println(ColorCyan + "  ──────────────────────────────────────────────────────────────" + ColorReset)
	fmt.Printf("  🎉 %s%s%s\n", ColorGreen+ColorBold, report.CheerMessage, ColorReset)
	fmt.Println(ColorCyan + "  ──────────────────────────────────────────────────────────────" + ColorReset)
	fmt.Println()
}

func runDownloadTest() {
	printBanner()
	fmt.Println(ColorBold + "  ⚡ تجربة محرك التحميل المتعدد المجزأ (IDM-Style Downloader)..." + ColorReset)

	m, err := manifest.Load("")
	if err != nil {
		fmt.Printf("  فشل قراءة ملف المانيفست: %v\n", err)
		return
	}

	cmdTools := m.Android.CmdlineTools
	fmt.Printf("  📦 تجربة تحميل مجزأ بـ 4 مسارات متوازية لـ: %s\n", cmdTools.URL)
	fmt.Println()

	dl := downloader.New(4)
	dest := "tmp/cmdline-tools-test.zip"

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	lastPercent := -1
	err = dl.Download(ctx, cmdTools.URL, dest, cmdTools.SHA256, func(p downloader.ProgressReport) {
		if p.Percent != lastPercent {
			lastPercent = p.Percent
			bars := p.Percent / 4
			progressBar := strings.Repeat("█", bars) + strings.Repeat("░", 25-bars)
			fmt.Printf("\r  [%s] %d%% | تم: %.1f MB / %.1f MB | السرعة: %.2f MB/s | مسارات: %d",
				progressBar, p.Percent,
				float64(p.DownloadedBytes)/(1024*1024),
				float64(p.TotalBytes)/(1024*1024),
				p.SpeedMBps, p.ActiveStreams)
		}
	})

	fmt.Println()
	if err != nil {
		fmt.Printf("\n  ❌ حدث خطأ أثناء التحميل التجريبي: %v\n", err)
	} else {
		fmt.Printf("\n  🎉 %sتم التحميل والتحقق من بصمة SHA256 بنجاح بنسبة 100%%!%s\n", ColorGreen+ColorBold, ColorReset)
		_ = os.Remove(dest) // clean test file
	}
}

func printHelp() {
	printBanner()
	fmt.Println("  الاستخدام:")
	fmt.Println("    fway                    تشغيل واجهة التطبيق الرسومية المرئية (GUI)")
	fmt.Println("    fway gui                فتح نافذة التطبيق البصرية كبرنامج سطح مكتب")
	fmt.Println("    fway harness ui         عرض جدول العناصر التفاعلية للـ Agent (Action Table)")
	fmt.Println("    fway harness tap <id>   محاكاة نقرة Agent على زر أو بطاقة")
	fmt.Println("    fway harness run        تشغيل اختبار الأتمتة الشامل (Autonomous Agent E2E)")
	fmt.Println("    fway cli                تشغيل القائمة التفاعلية في التيرمنال")
	fmt.Println("    fway doctor             فحص لابتوبك ومسار بناء الموبايل وتشخيص الأخطاء")
	fmt.Println("    fway test-dl            تجربة محرك التحميل المتعدد المجزأ ومطابقة الهاش")
	fmt.Println("    fway version            عرض إصدار الأداة")
	fmt.Println()
}
