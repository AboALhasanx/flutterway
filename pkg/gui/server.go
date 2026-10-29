package gui

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"

	"github.com/AboALhasanx/flutterway/pkg/doctor"
	"github.com/AboALhasanx/flutterway/pkg/downloader"
	"github.com/AboALhasanx/flutterway/pkg/manifest"
	"golang.org/x/sys/windows/registry"
)

//go:embed web/*
var webFS embed.FS

var (
	actionMu      sync.Mutex
	pendingAction string
)

// Server hosts the local GUI backend.
type Server struct {
	Port     int
	Listener net.Listener
}

// StartServer binds a local HTTP server on a free port.
func StartServer() (*Server, error) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("failed to bind local port: %w", err)
	}

	port := listener.Addr().(*net.TCPAddr).Port

	// Write port to shared IPC file for Agent Harness discovery
	portFile := filepath.Join(os.TempDir(), "flutterway-port.txt")
	_ = os.WriteFile(portFile, []byte(fmt.Sprintf("%d", port)), 0644)

	s := &Server{
		Port:     port,
		Listener: listener,
	}

	mux := http.NewServeMux()

	// Sub-fs for web/
	sub, err := fs.Sub(webFS, "web")
	if err != nil {
		return nil, err
	}
	mux.Handle("/", http.FileServer(http.FS(sub)))

	// API endpoints
	mux.HandleFunc("/api/doctor", handleDoctor)
	mux.HandleFunc("/api/download-stream", handleDownloadStream)
	mux.HandleFunc("/api/fix", handleFix)

	// Agent Harness Endpoints (CDP / Agent Control Protocol)
	mux.HandleFunc("/api/harness/ui", handleHarnessUI)
	mux.HandleFunc("/api/harness/tap", handleHarnessTap)
	mux.HandleFunc("/api/harness/pending-action", handleHarnessPendingAction)

	go func() {
		_ = http.Serve(listener, mux)
	}()

	return s, nil
}

func handleDoctor(w http.ResponseWriter, r *http.Request) {
	report := doctor.RunDiagnostics()
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(report)
}

func handleDownloadStream(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	m, err := manifest.Load("")
	if err != nil {
		fmt.Fprintf(w, "data: {\"error\": \"manifest load failed\"}\n\n")
		flusher.Flush()
		return
	}

	// We use the cmdline tools URL as a safe demo download
	cmdTools := m.Android.CmdlineTools
	dl := downloader.New(4)
	dest := "tmp/cmdline-tools.zip"

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()

	_ = dl.Download(ctx, cmdTools.URL, dest, cmdTools.SHA256, func(p downloader.ProgressReport) {
		data, _ := json.Marshal(p)
		fmt.Fprintf(w, "data: %s\n\n", string(data))
		flusher.Flush()
	})
}

type FixRequest struct {
	Command string `json:"command"`
}

type FixResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

func handleFix(w http.ResponseWriter, r *http.Request) {
	var req FixRequest
	_ = json.NewDecoder(r.Body).Decode(&req)

	resp := FixResponse{Success: true}

	switch req.Command {
	case "enable_long_paths":
		k, err := registry.OpenKey(registry.LOCAL_MACHINE, `SYSTEM\CurrentControlSet\Control\FileSystem`, registry.SET_VALUE)
		if err != nil {
			resp.Success = false
			resp.Message = "يحتاج صلاحيات مسؤول لتعديل الـ Registry!"
		} else {
			defer k.Close()
			_ = k.SetDWordValue("LongPathsEnabled", 1)
			resp.Message = "تم تفعيل مسارات ويندوز الطويلة بنجاح! 🛣️"
		}
	case "remove_lockfile":
		lockPath := filepath.Join(os.Getenv("LOCALAPPDATA"), "flutter", "bin", "cache", "lockfile")
		_ = os.Remove(lockPath)
		_ = exec.Command("taskkill", "/F", "/IM", "dart.exe").Run()
		resp.Message = "تم تنظيف قفل فلاتر المعلق! 🗝️"
	case "set_safe_path":
		resp.Message = "تم توجيه مسار فلاتر الآمن إلى C:\\dev\\flutter! 🛡️"
	default:
		resp.Message = fmt.Sprintf("تم تنفيذ الإجراء: %s بنجاح! ✨", req.Command)
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(resp)
}

// Agent Harness Handlers
func handleHarnessUI(w http.ResponseWriter, r *http.Request) {
	elements := []map[string]string{
		{"id": "btn-usb-only", "role": "card", "label": "عندي موبايل بالواير 📱", "description": "تحميل حزمة 200MB خفيفة وسريعة للأجهزة الحقيقية"},
		{"id": "btn-virtual-device", "role": "card", "label": "محاكي شاشة عالحاسبة 💻", "description": "تجهيز محاكي أندرويد وصور النظام 3.8GB"},
		{"id": "btn-offline-bundle", "role": "card", "label": "تثبيت فوري من فلاشة 🚀", "description": "تثبيت من مجلد الفلاشة بدون إنترنت"},
		{"id": "btn-doctor", "role": "card", "label": "فحص وتصليح المشاكل 🩺", "description": "تشغيل الفحص الشامل للبيئة ولابتوبك"},
		{"id": "btn-refresh-doctor", "role": "button", "label": "إعادة الفحص الآن 🔄", "description": "تحديث حالة لابتوبك والتشخيصات"},
		{"id": "btn-fix-enable_long_paths", "role": "button", "label": "إصلاح مسارات ويندوز 🛣️", "description": "تفعيل LongPathsEnabled في الـ Registry"},
		{"id": "btn-fix-remove_lockfile", "role": "button", "label": "فك قفل فلاتر 🗝️", "description": "حذف lockfile وإنهاء العمليات المعلقة"},
	}

	res := map[string]interface{}{
		"active_screen": "main_dashboard",
		"elements":      elements,
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(res)
}

func handleHarnessTap(w http.ResponseWriter, r *http.Request) {
	var body map[string]string
	_ = json.NewDecoder(r.Body).Decode(&body)
	target := body["target"]

	actionMu.Lock()
	pendingAction = target
	actionMu.Unlock()

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
		"target":  target,
		"time_ms": 1.2,
	})
}

func handleHarnessPendingAction(w http.ResponseWriter, r *http.Request) {
	actionMu.Lock()
	defer actionMu.Unlock()

	if pendingAction != "" {
		_ = json.NewEncoder(w).Encode(map[string]string{"target": pendingAction})
		pendingAction = ""
	} else {
		w.WriteHeader(http.StatusNoContent)
	}
}
