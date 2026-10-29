package doctor

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/AboALhasanx/flutterway/pkg/inspector"
)

// DiagnosticItem represents a friendly check result.
type DiagnosticItem struct {
	Title       string `json:"title"`
	Status      string `json:"status"` // "PASS", "WARN", "FAIL"
	Badge       string `json:"badge"`
	Explanation string `json:"explanation"`
	AutoFixable bool   `json:"auto_fixable"`
	FixCommand  string `json:"fix_command"`
}

// DoctorReport contains all items for the final diagnostic screen.
type DoctorReport struct {
	OverallStatus string           `json:"overall_status"`
	CheerMessage  string           `json:"cheer_message"`
	Items         []DiagnosticItem `json:"items"`
}

// RunDiagnostics executes the full diagnostic suite.
func RunDiagnostics() *DoctorReport {
	report := &DoctorReport{
		OverallStatus: "HEALTHY",
		Items:         []DiagnosticItem{},
	}

	// 1. Check System and Paths
	sys, _ := inspector.InspectSystem()
	if sys != nil {
		if sys.HasNonASCIIInPath || sys.HasSpacesInPath {
			report.Items = append(report.Items, DiagnosticItem{
				Title:       "مسار حساب الويندوز واللغة",
				Status:      "WARN",
				Badge:       "💡 نصيحة ذكية",
				Explanation: sys.FriendlyPathStatus,
				AutoFixable: true,
				FixCommand:  "set_safe_path",
			})
		} else {
			report.Items = append(report.Items, DiagnosticItem{
				Title:       "مسار حساب الويندوز",
				Status:      "PASS",
				Badge:       "✅ ممتاز",
				Explanation: sys.FriendlyPathStatus,
			})
		}

		// Disk space
		if sys.DriveCFreeGB >= 10.0 {
			report.Items = append(report.Items, DiagnosticItem{
				Title:       "مساحة القرص المتاحة",
				Status:      "PASS",
				Badge:       "🎉 ممتاز جداً",
				Explanation: sys.FriendlyDiskStatus,
			})
		} else {
			report.Items = append(report.Items, DiagnosticItem{
				Title:       "مساحة القرص المتاحة",
				Status:      "WARN",
				Badge:       "⚠️ انتبه للمساحة",
				Explanation: sys.FriendlyDiskStatus,
			})
		}

		// LongPaths
		if sys.LongPathsEnabled {
			report.Items = append(report.Items, DiagnosticItem{
				Title:       "مسارات ويندوز الطويلة (LongPaths)",
				Status:      "PASS",
				Badge:       "✅ مفعل",
				Explanation: "ويندوز مهيأ لاستيعاب ملفات بناء أندرويد العميقة دون أي انهيار! 🛣️",
			})
		} else {
			report.Items = append(report.Items, DiagnosticItem{
				Title:       "مسارات ويندوز الطويلة (LongPaths)",
				Status:      "WARN",
				Badge:       "🛠️ يحتاج تفعيل",
				Explanation: "ويندوز مقيد بمسار 260 حرف، ننصح بتفعيل المسارات الطويلة لتفادي أخطاء Gradle 📜",
				AutoFixable: true,
				FixCommand:  "enable_long_paths",
			})
		}
	}

	// 2. Check Git
	if isCommandAvailable("git") {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "أداة Git لإدارة الكود",
			Status:      "PASS",
			Badge:       "✅ مثبت",
			Explanation: "أداة Git موجودة وجاهزة لتنزيل وتحديث فلاتر بأي لحظة! 🐙",
		})
	} else {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "أداة Git لإدارة الكود",
			Status:      "WARN",
			Badge:       "🔍 غير متوفر",
			Explanation: "Git غير مثبت في النظام. الأداة ستقوم بتنزيله أو استخدام نسخة مدمجة خفيفة 🧰",
			AutoFixable: true,
			FixCommand:  "install_git",
		})
	}

	// 3. Check Java / JDK
	if isCommandAvailable("java") || os.Getenv("JAVA_HOME") != "" {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "بيئة الجافا (Java / JDK)",
			Status:      "PASS",
			Badge:       "☕ جاهز",
			Explanation: "محرك الجافا موجود لتشغيل وبناء تطبيقات أندرويد بنجاح! ⚡",
		})
	} else {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "بيئة الجافا (Java / JDK)",
			Status:      "WARN",
			Badge:       "🛠️ سنجهزه لك",
			Explanation: "سنقوم بتركيب OpenJDK 17 المعتمد وتوجيهه تلقائياً دون أي تضارب ☕",
			AutoFixable: true,
			FixCommand:  "install_jdk",
		})
	}

	// 4. Check Flutter SDK
	if isCommandAvailable("flutter") {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "محرك Flutter & Dart",
			Status:      "PASS",
			Badge:       "💙 فلاتر يرفرف",
			Explanation: "فلاتر مثبت ومعرف بالويندوز وجاهز لكتابة وتشغيل كودك الجميل! 🚀",
		})
	} else {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "محرك Flutter & Dart",
			Status:      "WARN",
			Badge:       "📦 بانتظار الإشارة",
			Explanation: "فلاتر غير مضاف للمسار بعد. اختر من القائمة لتنزيله بأسرع طريقة وأخف حجم! 🪄",
			AutoFixable: true,
			FixCommand:  "install_flutter",
		})
	}

	// 5. Check Startup Lockfile Deadlock
	lockPath := filepath.Join(os.Getenv("LOCALAPPDATA"), "flutter", "bin", "cache", "lockfile")
	if _, err := os.Stat(lockPath); err == nil {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "قفل بدء التشغيل (Startup Lock)",
			Status:      "WARN",
			Badge:       "🔒 قفل عالق",
			Explanation: "تم رصد ملف قفل عالق يمنع فلاتر من العمل. بإمكاننا حذفه بضغطة زر 🗝️",
			AutoFixable: true,
			FixCommand:  "remove_lockfile",
		})
	}

	// 6. Check ADB and Mobile Devices
	adb := inspector.InspectADB()
	if adb.ConflictDetected {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "منفذ أجهزة الموبايل (ADB Port 5037)",
			Status:      "WARN",
			Badge:       "🚨 تضارب برامج",
			Explanation: adb.FriendlyStatus,
			AutoFixable: true,
			FixCommand:  "fix_adb_port",
		})
	} else if adb.HasReadyDevice {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "الهاتف المتصل عبر USB",
			Status:      "PASS",
			Badge:       "📱 جاهز 100%",
			Explanation: adb.FriendlyStatus,
		})
	} else {
		report.Items = append(report.Items, DiagnosticItem{
			Title:       "فحص أجهزة الموبايل عبر USB",
			Status:      "INFO",
			Badge:       "🔌 بانتظار التوصيل",
			Explanation: adb.FriendlyStatus,
		})
	}

	report.CheerMessage = fmt.Sprintf("فحصنا كل تفاصيل حاسبتك بدقة! عندك %d نقاط فحص جاهزة تماماً 🌟", len(report.Items))
	return report
}

func isCommandAvailable(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}
