package harness

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/AboALhasanx/flutterway/pkg/doctor"
)

// UIElement represents a node in the agent action table.
type UIElement struct {
	ID          string `json:"id"`
	Role        string `json:"role"`
	Label       string `json:"label"`
	Description string `json:"description"`
}

// ActionTable represents the compact agent action table (like hs ui).
type ActionTable struct {
	ActiveScreen string      `json:"active_screen"`
	Elements     []UIElement `json:"elements"`
}

// HarnessClient connects an agent to the running FlutterWay instance.
type HarnessClient struct {
	BaseURL string
	Client  *http.Client
}

// GetPortFilePath returns the shared IPC file where the active GUI port is stored.
func GetPortFilePath() string {
	return filepath.Join(os.TempDir(), "flutterway-port.txt")
}

// NewClient discovers the active GUI port and connects.
func NewClient() (*HarnessClient, error) {
	portBytes, err := os.ReadFile(GetPortFilePath())
	if err != nil {
		return nil, fmt.Errorf("flutterway is not currently running (port file not found): %w", err)
	}

	portStr := strings.TrimSpace(string(portBytes))
	baseURL := fmt.Sprintf("http://127.0.0.1:%s", portStr)

	return &HarnessClient{
		BaseURL: baseURL,
		Client:  &http.Client{Timeout: 3 * time.Second},
	}, nil
}

// GetActionTable retrieves the compact action table (Text first, pixels last).
func (c *HarnessClient) GetActionTable() (*ActionTable, error) {
	resp, err := c.Client.Get(c.BaseURL + "/api/harness/ui")
	if err != nil {
		return nil, fmt.Errorf("failed to fetch action table: %w", err)
	}
	defer resp.Body.Close()

	var table ActionTable
	if err := json.NewDecoder(resp.Body).Decode(&table); err != nil {
		return nil, err
	}
	return &table, nil
}

// Tap triggers an action by ID or label (single-digit-ms verb).
func (c *HarnessClient) Tap(targetID string) (bool, error) {
	payload, _ := json.Marshal(map[string]string{"target": targetID})
	resp, err := c.Client.Post(c.BaseURL+"/api/harness/tap", "application/json", bytes.NewReader(payload))
	if err != nil {
		return false, fmt.Errorf("tap failed: %w", err)
	}
	defer resp.Body.Close()

	var res map[string]interface{}
	_ = json.NewDecoder(resp.Body).Decode(&res)
	success, _ := res["success"].(bool)
	return success, nil
}

// GetDoctorReport fetches the current diagnostics via harness.
func (c *HarnessClient) GetDoctorReport() (*doctor.DoctorReport, error) {
	resp, err := c.Client.Get(c.BaseURL + "/api/doctor")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var rep doctor.DoctorReport
	if err := json.NewDecoder(resp.Body).Decode(&rep); err != nil {
		return nil, err
	}
	return &rep, nil
}

// PrintActionTable formats the table into a compact view (like hs ui).
func PrintActionTable(table *ActionTable) {
	fmt.Printf("\n--- [FlutterWay Action Table | Screen: %s] ---\n", table.ActiveScreen)
	fmt.Printf("%-24s | %-10s | %s\n", "TARGET_ID", "ROLE", "LABEL / PURPOSE")
	fmt.Println(strings.Repeat("-", 70))
	for _, el := range table.Elements {
		fmt.Printf("%-24s | %-10s | %s\n", el.ID, el.Role, el.Label)
	}
	fmt.Println(strings.Repeat("-", 70))
	fmt.Println("Total actionable elements:", len(table.Elements))
}
