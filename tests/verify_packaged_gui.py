"""Smoke-test that a packaged FlutterWay GUI creates its real main window."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    if os.name != "nt":
        raise SystemExit("This smoke test requires Windows.")
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/verify_packaged_gui.py <FlutterWayNative.exe>")

    executable = Path(sys.argv[1]).resolve(strict=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_windows = user32.EnumWindows
    enum_windows.argtypes = (ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p), ctypes.c_void_p)
    enum_windows.restype = ctypes.c_bool
    get_window_thread_process_id = user32.GetWindowThreadProcessId
    get_window_thread_process_id.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    get_window_thread_process_id.restype = ctypes.c_ulong
    is_window_visible = user32.IsWindowVisible
    is_window_visible.argtypes = (ctypes.c_void_p,)
    is_window_visible.restype = ctypes.c_bool
    get_window_text_length = user32.GetWindowTextLengthW
    get_window_text_length.argtypes = (ctypes.c_void_p,)
    get_window_text_length.restype = ctypes.c_int
    get_window_text = user32.GetWindowTextW
    get_window_text.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
    get_window_text.restype = ctypes.c_int

    with tempfile.TemporaryDirectory(prefix="flutterway-gui-smoke-") as data_dir:
        env = os.environ.copy()
        env["FLUTTERWAY_DATA_DIR"] = data_dir
        process = subprocess.Popen([str(executable)], cwd=str(executable.parent), env=env)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"FlutterWay exited before showing its window (exit={process.returncode}).")

                matching_windows: list[str] = []

                @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                def visit(hwnd: int, _lparam: int) -> bool:
                    pid = ctypes.c_ulong()
                    get_window_thread_process_id(hwnd, ctypes.byref(pid))
                    if pid.value == process.pid and is_window_visible(hwnd):
                        size = get_window_text_length(hwnd)
                        buffer = ctypes.create_unicode_buffer(size + 1)
                        get_window_text(hwnd, buffer, len(buffer))
                        if buffer.value:
                            matching_windows.append(buffer.value)
                    return True

                enum_windows(visit, None)
                if any(title.startswith("FlutterWay") for title in matching_windows):
                    title = next(t for t in matching_windows if t.startswith("FlutterWay"))
                    print(f"GUI startup verified: pid={process.pid}, title={title.encode('ascii', 'backslashreplace').decode('ascii')!r}")
                    return 0

                time.sleep(0.25)

            raise TimeoutError("FlutterWay process remained alive but did not create a visible FlutterWay main window within 30 seconds.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Packaged GUI smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
