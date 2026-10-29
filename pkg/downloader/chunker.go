package downloader

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"
)

// ProgressReport carries real-time download telemetry.
type ProgressReport struct {
	DownloadedBytes int64
	TotalBytes      int64
	SpeedMBps       float64
	Percent         int
	ActiveStreams   int
	IsResumed       bool
}

type ProgressCallback func(p ProgressReport)

// Downloader manages segmented multi-threaded downloads (like IDM / AB Download Manager).
type Downloader struct {
	Client      *http.Client
	Concurrency int
}

// New creates a new Downloader with custom concurrency.
func New(concurrency int) *Downloader {
	if concurrency <= 0 {
		concurrency = 4
	}
	return &Downloader{
		Client: &http.Client{
			Timeout: 0, // Handled per request with context
		},
		Concurrency: concurrency,
	}
}

// Download performs a resumable segmented download.
func (d *Downloader) Download(ctx context.Context, url, destPath string, expectedSHA256 string, callback ProgressCallback) error {
	// Step 1: If file already exists, check hash and skip download!
	if info, err := os.Stat(destPath); err == nil && info.Size() > 0 {
		if match, _ := VerifyFileSHA256(destPath, expectedSHA256); match {
			if callback != nil {
				callback(ProgressReport{
					DownloadedBytes: info.Size(),
					TotalBytes:      info.Size(),
					Percent:         100,
					IsResumed:       true,
				})
			}
			return nil
		}
	}

	// Ensure destination directory exists
	if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	// Step 2: Query file metadata via HEAD or Range GET
	req, err := http.NewRequestWithContext(ctx, "HEAD", url, nil)
	if err != nil {
		return err
	}
	resp, err := d.Client.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		// Fallback to GET 0-0 range check if HEAD is blocked
		req, _ = http.NewRequestWithContext(ctx, "GET", url, nil)
		req.Header.Set("Range", "bytes=0-0")
		resp, err = d.Client.Do(req)
		if err != nil {
			return fmt.Errorf("failed to reach server: %w", err)
		}
	}
	defer resp.Body.Close()

	contentLength := resp.ContentLength
	acceptRanges := resp.Header.Get("Accept-Ranges") == "bytes" || resp.StatusCode == http.StatusPartialContent

	// If server does not support ranges or length is unknown, do single-stream download
	if !acceptRanges || contentLength <= 0 || d.Concurrency <= 1 {
		return d.singleStreamDownload(ctx, url, destPath, expectedSHA256, callback)
	}

	// Step 3: Segmented multi-chunk download
	numChunks := d.Concurrency
	chunkSize := contentLength / int64(numChunks)

	partFiles := make([]string, numChunks)
	partDownloaded := make([]int64, numChunks)
	var initialDownloaded int64

	for i := 0; i < numChunks; i++ {
		partFiles[i] = fmt.Sprintf("%s.part.%d", destPath, i)
		if fi, err := os.Stat(partFiles[i]); err == nil {
			partDownloaded[i] = fi.Size()
			initialDownloaded += fi.Size()
		}
	}

	var totalDownloaded atomic.Int64
	totalDownloaded.Store(initialDownloaded)

	// Speed calculation ticker
	stopTicker := make(chan struct{})
	defer close(stopTicker)

	if callback != nil {
		go func() {
			var lastDownloaded = totalDownloaded.Load()
			ticker := time.NewTicker(500 * time.Millisecond)
			defer ticker.Stop()

			for {
				select {
				case <-ticker.C:
					current := totalDownloaded.Load()
					delta := current - lastDownloaded
					speedMBps := float64(delta) / (1024 * 1024 * 0.5)
					lastDownloaded = current
					percent := int(float64(current) / float64(contentLength) * 100)
					if percent > 100 {
						percent = 100
					}
					callback(ProgressReport{
						DownloadedBytes: current,
						TotalBytes:      contentLength,
						SpeedMBps:       speedMBps,
						Percent:         percent,
						ActiveStreams:   numChunks,
						IsResumed:       initialDownloaded > 0,
					})
				case <-stopTicker:
					return
				}
			}
		}()
	}

	var wg sync.WaitGroup
	errChan := make(chan error, numChunks)

	for i := 0; i < numChunks; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()

			start := int64(idx) * chunkSize
			end := start + chunkSize - 1
			if idx == numChunks-1 {
				end = contentLength - 1
			}

			// Adjust for resumed bytes
			alreadyGot := partDownloaded[idx]
			if start+alreadyGot > end {
				return // Chunk already completed!
			}
			resumeStart := start + alreadyGot

			req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
			if err != nil {
				errChan <- err
				return
			}
			req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", resumeStart, end))

			resp, err := d.Client.Do(req)
			if err != nil {
				errChan <- fmt.Errorf("chunk %d download failed: %w", idx, err)
				return
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusPartialContent && resp.StatusCode != http.StatusOK {
				errChan <- fmt.Errorf("chunk %d server returned %d", idx, resp.StatusCode)
				return
			}

			flag := os.O_CREATE | os.O_WRONLY
			if alreadyGot > 0 {
				flag |= os.O_APPEND
			}
			out, err := os.OpenFile(partFiles[idx], flag, 0644)
			if err != nil {
				errChan <- err
				return
			}
			defer out.Close()

			buf := make([]byte, 64*1024)
			for {
				select {
				case <-ctx.Done():
					return
				default:
				}

				n, rErr := resp.Body.Read(buf)
				if n > 0 {
					if _, wErr := out.Write(buf[:n]); wErr != nil {
						errChan <- wErr
						return
					}
					totalDownloaded.Add(int64(n))
				}
				if rErr != nil {
					if rErr == io.EOF {
						break
					}
					errChan <- rErr
					return
				}
			}
		}(i)
	}

	wg.Wait()
	close(errChan)

	if len(errChan) > 0 {
		return <-errChan
	}

	// Step 4: Assemble parts into final target file
	finalFile, err := os.Create(destPath)
	if err != nil {
		return fmt.Errorf("failed to create final assembled file: %w", err)
	}
	defer finalFile.Close()

	for i := 0; i < numChunks; i++ {
		part, err := os.Open(partFiles[i])
		if err != nil {
			return fmt.Errorf("missing part file %s: %w", partFiles[i], err)
		}
		_, err = io.Copy(finalFile, part)
		part.Close()
		if err != nil {
			return fmt.Errorf("error assembling part %d: %w", i, err)
		}
		_ = os.Remove(partFiles[i]) // Clean part
	}

	// Step 5: Verify SHA256
	if expectedSHA256 != "" {
		match, err := VerifyFileSHA256(destPath, expectedSHA256)
		if err != nil || !match {
			_ = os.Remove(destPath)
			return fmt.Errorf("checksum mismatch: downloaded file is corrupted")
		}
	}

	if callback != nil {
		callback(ProgressReport{
			DownloadedBytes: contentLength,
			TotalBytes:      contentLength,
			Percent:         100,
			ActiveStreams:   0,
		})
	}

	return nil
}

func (d *Downloader) singleStreamDownload(ctx context.Context, url, destPath, expectedSHA256 string, callback ProgressCallback) error {
	tmpPath := destPath + ".tmp"
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}

	resp, err := d.Client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	out, err := os.Create(tmpPath)
	if err != nil {
		return err
	}
	defer out.Close()

	total := resp.ContentLength
	var downloaded int64
	buf := make([]byte, 32*1024)

	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			_, _ = out.Write(buf[:n])
			downloaded += int64(n)
			if callback != nil && total > 0 {
				callback(ProgressReport{
					DownloadedBytes: downloaded,
					TotalBytes:      total,
					Percent:         int(float64(downloaded) / float64(total) * 100),
				})
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
	}

	out.Close()
	_ = os.Rename(tmpPath, destPath)

	if expectedSHA256 != "" {
		match, err := VerifyFileSHA256(destPath, expectedSHA256)
		if err != nil || !match {
			_ = os.Remove(destPath)
			return fmt.Errorf("checksum mismatch in single-stream download")
		}
	}

	return nil
}
