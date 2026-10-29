package gui

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// LaunchWindow opens the visual app window reliably on the user's desktop.
func LaunchWindow(url string) (*exec.Cmd, error) {
	// First: Try opening dedicated app-mode window
	browserPath := findChromiumBrowser()

	if browserPath != "" {
		// Launch without conflicting profile lock, dedicated app window
		appArg := fmt.Sprintf("--app=%s", url)
		winSize := "--window-size=1120,760"

		cmd := exec.Command(browserPath, appArg, winSize)
		if err := cmd.Start(); err == nil {
			return cmd, nil
		}
	}

	// Reliable Windows Shell Launcher: Always brings the window to the foreground!
	cmd := exec.Command("cmd", "/c", "start", "", url)
	if err := cmd.Start(); err != nil {
		// Ultimate fallback
		fallbackCmd := exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
		return fallbackCmd, fallbackCmd.Start()
	}

	return cmd, nil
}

func findChromiumBrowser() string {
	localAppData := os.Getenv("LOCALAPPDATA")
	progFiles := os.Getenv("ProgramFiles")
	progFiles86 := os.Getenv("ProgramFiles(x86)")

	candidates := []string{
		// Microsoft Edge (Standard on Windows)
		filepath.Join(progFiles86, `Microsoft\Edge\Application\msedge.exe`),
		filepath.Join(progFiles, `Microsoft\Edge\Application\msedge.exe`),
		filepath.Join(localAppData, `Microsoft\Edge\Application\msedge.exe`),
		// Google Chrome
		filepath.Join(progFiles, `Google\Chrome\Application\chrome.exe`),
		filepath.Join(progFiles86, `Google\Chrome\Application\chrome.exe`),
		filepath.Join(localAppData, `Google\Chrome\Application\chrome.exe`),
		// Thorium
		filepath.Join(localAppData, `Thorium\Application\thorium.exe`),
		// Brave
		filepath.Join(progFiles, `BraveSoftware\Brave-Browser\Application\brave.exe`),
	}

	for _, c := range candidates {
		if c != "" {
			if _, err := os.Stat(c); err == nil {
				return c
			}
		}
	}

	return ""
}
