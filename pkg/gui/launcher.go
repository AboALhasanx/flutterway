package gui

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// LaunchWindow opens the visual app window.
func LaunchWindow(url string) (*exec.Cmd, error) {
	browserPath := findChromiumBrowser()

	if browserPath != "" {
		tempProfile := filepath.Join(os.TempDir(), "flutterway-gui-profile")
		appArg := fmt.Sprintf("--app=%s", url)
		winSize := "--window-size=1120,760"
		userDir := fmt.Sprintf("--user-data-dir=%s", tempProfile)

		cmd := exec.Command(browserPath, appArg, winSize, userDir)
		if err := cmd.Start(); err == nil {
			return cmd, nil
		}
	}

	// Fallback to default system browser
	cmd := exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to open browser: %w", err)
	}

	return cmd, nil
}

func findChromiumBrowser() string {
	localAppData := os.Getenv("LOCALAPPDATA")
	progFiles := os.Getenv("ProgramFiles")
	progFiles86 := os.Getenv("ProgramFiles(x86)")

	candidates := []string{
		// Thorium
		filepath.Join(localAppData, `Thorium\Application\thorium.exe`),
		// Microsoft Edge
		filepath.Join(progFiles86, `Microsoft\Edge\Application\msedge.exe`),
		filepath.Join(progFiles, `Microsoft\Edge\Application\msedge.exe`),
		filepath.Join(localAppData, `Microsoft\Edge\Application\msedge.exe`),
		// Google Chrome
		filepath.Join(progFiles, `Google\Chrome\Application\chrome.exe`),
		filepath.Join(progFiles86, `Google\Chrome\Application\chrome.exe`),
		filepath.Join(localAppData, `Google\Chrome\Application\chrome.exe`),
		// Brave
		filepath.Join(progFiles, `BraveSoftware\Brave-Browser\Application\brave.exe`),
		filepath.Join(localAppData, `BraveSoftware\Brave-Browser\Application\brave.exe`),
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
