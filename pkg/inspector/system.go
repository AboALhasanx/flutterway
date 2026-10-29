package inspector

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"unicode"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

// SystemHealth carries user-friendly pre-flight inspection results.
type SystemHealth struct {
	UserProfilePath       string  `json:"user_profile_path"`
	HasNonASCIIInPath     bool    `json:"has_non_ascii_in_path"`
	HasSpacesInPath       bool    `json:"has_spaces_in_path"`
	RecommendedSDKPath    string  `json:"recommended_sdk_path"`
	DriveCFreeGB          float64 `json:"drive_c_free_gb"`
	DriveDFreeGB          float64 `json:"drive_d_free_gb"`
	LongPathsEnabled      bool    `json:"long_paths_enabled"`
	HasMediaFeaturePack   bool    `json:"has_media_feature_pack"`
	VirtualizationEnabled bool    `json:"virtualization_enabled"`
	CPUModel              string  `json:"cpu_model"`
	FriendlyDiskStatus    string  `json:"friendly_disk_status"`
	FriendlyPathStatus    string  `json:"friendly_path_status"`
}

// InspectSystem runs full non-destructive system pre-flight checks.
func InspectSystem() (*SystemHealth, error) {
	health := &SystemHealth{}

	// 1. Inspect User Profile Path
	userProfile := os.Getenv("USERPROFILE")
	health.UserProfilePath = userProfile

	for _, r := range userProfile {
		if r > unicode.MaxASCII {
			health.HasNonASCIIInPath = true
		}
		if unicode.IsSpace(r) {
			health.HasSpacesInPath = true
		}
	}

	if health.HasNonASCIIInPath || health.HasSpacesInPath {
		health.RecommendedSDKPath = `C:\dev\flutter`
		health.FriendlyPathStatus = "⚠️ مسار اسمك بالويندوز بيه حروف عربية أو مسافات، فراح نخلي فلاتر بـ C:\\dev علمود ما تصير أي خربطة! 🛡️"
	} else {
		health.RecommendedSDKPath = filepath.Join(userProfile, "dev", "flutter")
		health.FriendlyPathStatus = "✅ اسم حسابك باللابتوب تمام ومسارك سالك وما بيه أي عائق! 🌟"
	}

	// 2. Inspect Free Disk Space on C: and D:
	health.DriveCFreeGB = getDriveFreeSpaceGB(`C:\`)
	health.DriveDFreeGB = getDriveFreeSpaceGB(`D:\`)

	if health.DriveCFreeGB >= 15.0 {
		health.FriendlyDiskStatus = fmt.Sprintf("🎉 ما شاء الله! عندك %.1f جيجابايت مساحة فارغة، تكفي وزايد لتنصيب كلشي بسلاسة!", health.DriveCFreeGB)
	} else if health.DriveDFreeGB >= 15.0 {
		health.RecommendedSDKPath = `D:\dev\flutter`
		health.FriendlyDiskStatus = fmt.Sprintf("💡 قرص C مساحته قليلة (%.1f GB)، بس قرص D بي مساحة روعة (%.1f GB)، فراح ننصب على D! 🚀", health.DriveCFreeGB, health.DriveDFreeGB)
	} else {
		health.FriendlyDiskStatus = fmt.Sprintf("⚠️ المساحة المتبقية بقرص C هي %.1f GB، نحتاج على الأقل 10GB حتى نشتغل براحتنا 🧹", health.DriveCFreeGB)
	}

	// 3. Inspect Windows LongPaths Registry
	health.LongPathsEnabled = checkLongPathsRegistry()

	// 4. Inspect Media Feature Pack (mfplat.dll)
	sys32 := filepath.Join(os.Getenv("SystemRoot"), "System32", "mfplat.dll")
	if _, err := os.Stat(sys32); err == nil {
		health.HasMediaFeaturePack = true
	}

	// 5. Inspect CPU and Virtualization via WMI / WMIC
	health.VirtualizationEnabled, health.CPUModel = checkVirtualization()

	return health, nil
}

func getDriveFreeSpaceGB(drive string) float64 {
	pathPtr, err := windows.UTF16PtrFromString(drive)
	if err != nil {
		return 0
	}
	var freeBytesAvailable, totalNumberOfBytes, totalNumberOfFreeBytes uint64
	err = windows.GetDiskFreeSpaceEx(pathPtr, &freeBytesAvailable, &totalNumberOfBytes, &totalNumberOfFreeBytes)
	if err != nil {
		return 0
	}
	return float64(freeBytesAvailable) / (1024 * 1024 * 1024)
}

func checkLongPathsRegistry() bool {
	k, err := registry.OpenKey(registry.LOCAL_MACHINE, `SYSTEM\CurrentControlSet\Control\FileSystem`, registry.QUERY_VALUE)
	if err != nil {
		return false
	}
	defer k.Close()

	val, _, err := k.GetIntegerValue("LongPathsEnabled")
	if err != nil {
		return false
	}
	return val == 1
}

func checkVirtualization() (bool, string) {
	// Query PowerShell WMI safely
	cmd := exec.Command("powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Processor | Select-Object -Property Name, VirtualizationFirmwareEnabled | ConvertTo-Json -Compress")
	out, err := cmd.Output()
	if err != nil {
		return false, "Windows Processor"
	}

	strOut := string(out)
	virtEnabled := strings.Contains(strOut, `"VirtualizationFirmwareEnabled":true`)
	cpuName := "Standard Processor"
	if idx := strings.Index(strOut, `"Name":"`); idx != -1 {
		rest := strOut[idx+8:]
		if endIdx := strings.Index(rest, `"`); endIdx != -1 {
			cpuName = strings.TrimSpace(rest[:endIdx])
		}
	}

	return virtEnabled, cpuName
}
