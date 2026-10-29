package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/AboALhasanx/flutterway/pkg/doctor"
	"github.com/AboALhasanx/flutterway/pkg/downloader"
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
		runInteractiveMenu()
		return
	}

	switch args[0] {
	case "doctor":
		runDoctor()
	case "test-dl":
		runDownloadTest()
	case "version":
		fmt.Printf("FlutterWay CLI (fway) v1.0.0-prototype | Windows x64\n")
	case "help", "--help", "-h":
		printHelp()
	default:
		fmt.Printf("أمر غير معروف: %s. استخدم 'fway help' لمعرفة الأوامر.\n", args[0])
	}
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
	fmt.Println("  " + ColorRed + "[5] 🚪 خروج مع ابتسامة 😊" + ColorReset)
	fmt.Println()

	fmt.Print("  👉 اكتب رقم الخيار ثم اضغط Enter: ")
	var choice string
	fmt.Scanln(&choice)
	choice = strings.TrimSpace(choice)

	switch choice {
	case "1":
		fmt.Println()
		fmt.Println(ColorGreen + "  🌟 اختيار ذكي جداً! الربط بالواير يوفر عليك ساعات تحميل وما يستهلك رام جهازك أبداً!" + ColorReset)
		fmt.Println("  جاري فحص اتصال الهاتف وتشغيل الفاحص...")
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
	fmt.Println("    fway             تشغيل القائمة التفاعلية اللطيفة للمبتدئين")
	fmt.Println("    fway doctor      فحص لابتوبك ومسار بناء الموبايل وتشخيص الأخطاء")
	fmt.Println("    fway test-dl     تجربة محرك التحميل المتعدد المجزأ ومطابقة الهاش")
	fmt.Println("    fway version     عرض إصدار الأداة")
	fmt.Println()
}
