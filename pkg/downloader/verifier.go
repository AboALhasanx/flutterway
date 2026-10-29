package downloader

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"strings"
)

// VerifyFileSHA256 computes SHA256 of the given file path and compares with expected.
func VerifyFileSHA256(filePath, expectedHash string) (bool, error) {
	if expectedHash == "" {
		return true, nil
	}

	f, err := os.Open(filePath)
	if err != nil {
		return false, err
	}
	defer f.Close()

	hasher := sha256.New()
	if _, err := io.Copy(hasher, f); err != nil {
		return false, fmt.Errorf("error hashing file: %w", err)
	}

	actualHash := hex.EncodeToString(hasher.Sum(nil))
	match := strings.EqualFold(actualHash, strings.TrimSpace(expectedHash))
	return match, nil
}
