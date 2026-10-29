package manifest

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"os"
)

//go:embed embedded_manifest.json
var embeddedManifestBytes []byte

// Load reads the manifest from local file path or falls back to embedded definition.
func Load(customPath string) (*ToolchainManifest, error) {
	var data []byte
	var err error

	if customPath != "" {
		data, err = os.ReadFile(customPath)
		if err != nil {
			return nil, fmt.Errorf("failed to read custom manifest from %s: %w", customPath, err)
		}
	} else if _, err := os.Stat("manifests/toolchain-v1.json"); err == nil {
		data, err = os.ReadFile("manifests/toolchain-v1.json")
		if err != nil {
			data = embeddedManifestBytes
		}
	} else {
		data = embeddedManifestBytes
	}

	var m ToolchainManifest
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("failed to parse manifest json: %w", err)
	}

	return &m, nil
}
