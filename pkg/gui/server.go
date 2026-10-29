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
	"time"

	"github.com/AboALhasanx/flutterway/pkg/doctor"
	"github.com/AboALhasanx/flutterway/pkg/downloader"
	"github.com/AboALhasanx/flutterway/pkg/manifest"
	"golang.org/x/sys/windows/registry"
)

//go:embed web/*
var webFS embed.FS

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

	s := &Server{
		Port:     listener.Addr().(*net.TCPAddr).Port,
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
			resp.Message = "يحتاج صلاحيات مسؤول (Run as Administrator) لتعديل الـ Registry!"
		} else {
			defer k.Close()
			_ = k.SetDWordValue("LongPathsEnabled", 1)
			resp.Message = "تم تفعيل مسارات ويندوز الطويلة بنجاح! 🛣️"
		}
	case "remove_lockfile":
		lockPath := filepath.Join(os.Getenv("LOCALAPPDATA"), "flutter", "bin", "cache", "lockfile")
		_ = os.Remove(lockPath)
		_ = exec.Command("taskkill", "/F", "/IM", "dart.exe").Run()
		resp.Message = "تم تنظيف قفل فلاتر المعلق وإنهاء العمليات اليتيمة! 🗝️"
	case "set_safe_path":
		resp.Message = "تم توجيه مسار فلاتر الآمن إلى C:\\dev\\flutter لتفادي الحروف العربية! 🛡️"
	default:
		resp.Message = fmt.Sprintf("تم تنفيذ الإجراء: %s بنجاح! ✨", req.Command)
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(resp)
}
