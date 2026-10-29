package inspector

import (
	"fmt"
	"net"
	"os/exec"
	"strings"
	"time"
)

// DeviceInfo represents an Android device attached via USB or emulator.
type DeviceInfo struct {
	Serial string `json:"serial"`
	State  string `json:"state"` // "device", "unauthorized", "offline"
	Model  string `json:"model"`
}

// ADBHealth reports the status of ADB and attached devices.
type ADBHealth struct {
	Port5037InUse     bool         `json:"port_5037_in_use"`
	ConflictDetected  bool         `json:"conflict_detected"`
	ConflictDetails   string       `json:"conflict_details"`
	Devices           []DeviceInfo `json:"devices"`
	FriendlyStatus    string       `json:"friendly_status"`
	HasReadyDevice    bool         `json:"has_ready_device"`
	RecommendedAction string       `json:"recommended_action"`
}

// InspectADB examines port 5037 and enumerates connected devices.
func InspectADB() *ADBHealth {
	health := &ADBHealth{}

	// 1. Check if port 5037 is actively listening
	conn, err := net.DialTimeout("tcp", "127.0.0.1:5037", 300*time.Millisecond)
	if err == nil {
		health.Port5037InUse = true
		conn.Close()
	}

	// 2. Check for port 5037 conflicts with emulators (BlueStacks / Nox)
	checkPortOwner(health)

	// 3. Try running `adb devices -l`
	cmd := exec.Command("adb", "devices", "-l")
	out, err := cmd.CombinedOutput()
	if err != nil {
		health.FriendlyStatus = "🔌 خادم ADB غير مفعل حالياً أو غير مضاف للـ PATH (راح نشغله الك تلقائياً أول ما نثبت أدوات أندرويد! 🚀)"
		return health
	}

	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "List of devices") || strings.HasPrefix(line, "*") {
			continue
		}

		fields := strings.Fields(line)
		if len(fields) >= 2 {
			dev := DeviceInfo{
				Serial: fields[0],
				State:  fields[1],
			}
			for _, f := range fields[2:] {
				if strings.HasPrefix(f, "model:") {
					dev.Model = strings.TrimPrefix(f, "model:")
				}
			}
			if dev.Model == "" {
				dev.Model = dev.Serial
			}
			health.Devices = append(health.Devices, dev)
		}
	}

	// 4. Formulate kid-friendly status message
	if len(health.Devices) == 0 {
		health.FriendlyStatus = "🔌 ماكو أي موبايل مربوط بالواير حالياً. (تكدر تربط موبايلك بالواير وتفعل تصحيح USB، أو تختار وضع المحاكي) 📱"
	} else {
		for _, d := range health.Devices {
			if d.State == "device" {
				health.HasReadyDevice = true
				health.FriendlyStatus = fmt.Sprintf("🎉 عاشت إيدك! لكيت جهازك البطل (%s) متصل ومستعد فوراً لبناء وتشغيل التطبيق! ⚡📱", d.Model)
				break
			} else if d.State == "unauthorized" {
				health.FriendlyStatus = fmt.Sprintf("⚠️ موبايلك (%s) متصل، بس باوع ع شاشة الموبايل هسه واضغط (سماح دائماً / Allow) علمود اللابتوب يكدر يشوفه! 📲", d.Model)
				health.RecommendedAction = "افتح قفل شاشة هاتفك واضغط موافق على رسالة تصحيح أخطاء USB"
				break
			}
		}
	}

	return health
}

func checkPortOwner(health *ADBHealth) {
	// Query netstat to see what PID owns 5037
	cmd := exec.Command("powershell", "-NoProfile", "-Command", "Get-NetTCPConnection -LocalPort 5037 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1")
	out, err := cmd.Output()
	if err != nil || strings.TrimSpace(string(out)) == "" {
		return
	}

	pid := strings.TrimSpace(string(out))
	pCmd := exec.Command("powershell", "-NoProfile", "-Command", fmt.Sprintf("(Get-Process -Id %s -ErrorAction SilentlyContinue).ProcessName", pid))
	pOut, _ := pCmd.Output()
	procName := strings.ToLower(strings.TrimSpace(string(pOut)))

	if strings.Contains(procName, "bluestacks") || strings.Contains(procName, "hd-player") || strings.Contains(procName, "nox") {
		health.ConflictDetected = true
		health.ConflictDetails = fmt.Sprintf("محاكي الألعاب (%s) محتجز منفذ ADB بالخلفية!", procName)
		health.FriendlyStatus = "🚨 انتبه: محاكي الألعاب (BlueStacks/Nox) شغال بالخلفية وحابس منفذ الموبايل! راح نطرد النسخة القديمة ونشغل نسختنا الحديثة! 🔓"
	}
}
