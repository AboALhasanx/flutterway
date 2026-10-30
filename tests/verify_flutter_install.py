"""Manual check: install the pinned Flutter SDK and run it.

Downloads the pinned archive, verifies it, extracts it with the production
code path (``toolchain.install_flutter_archive``) and runs ``flutter --version``.

Run:
    python tests/verify_flutter_install.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import toolchain  # noqa: E402


def main() -> int:
    release = toolchain.resolve_flutter_release("stable")
    if not release:
        print("No Flutter release resolved.")
        return 2
    work = Path(tempfile.mkdtemp(prefix="fw-flutter-install-"))
    target = work / "flutter"
    print("installing", release.version, "into", target, flush=True)
    started = time.time()
    result = toolchain.install_flutter_archive(str(target), release)
    print("install:", result, flush=True)
    if not result.get("success"):
        return 3
    flutter = target / "bin" / "flutter.bat"
    if not flutter.exists():
        print("flutter.bat missing after install")
        return 4

    env = os.environ.copy()
    env["CI"] = "true"
    env["FLUTTER_SUPPRESS_ANALYTICS"] = "true"
    print("running flutter --version", flush=True)
    try:
        proc = subprocess.run(
            [str(flutter), "--version"],
            capture_output=True, text=True, timeout=900, env=env,
        )
    except subprocess.TimeoutExpired:
        print("flutter --version timed out")
        return 5
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print("exit:", proc.returncode, flush=True)
    print(output[-3000:], flush=True)
    if proc.returncode != 0:
        return 6
    if release.version not in output:
        print(f"expected version {release.version} not found in output")
        return 7
    print(f"total seconds: {round(time.time() - started, 1)}")
    print("FLUTTER_VERSION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
