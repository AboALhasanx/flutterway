"""Manual check: download the pinned Flutter archive and verify its SHA-256.

Run:
    python tests/verify_flutter_download.py

Used by the `flutter-download` CI job; not part of the unit-test discovery
because it downloads ~1 GB.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import downloads, toolchain  # noqa: E402


def main() -> int:
    release = toolchain.resolve_flutter_release("stable")
    if not release:
        print("No Flutter release resolved.")
        return 2
    target = Path(tempfile.mkdtemp(prefix="fw-flutter-verify-")) / release.archive_name
    url = "https://storage.googleapis.com/flutter_infra_release/releases/" + release.archive
    start = time.time()
    if not toolchain._download(url, str(target), progress=lambda pct: None):
        print("Download failed.")
        return 3
    check = downloads.verify_file(str(target), release.sha256, release.size)
    print("version:", release.version)
    print("archive:", release.archive)
    print("bytes:", check["size"])
    print("seconds:", round(time.time() - start, 1))
    print("sha256:", check["sha256"])
    print("expected:", release.sha256)
    if not check["ok"]:
        print("VERIFY FAILED:", check["reason"])
        return 4
    print("VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
