"""Persistent Flutter hot-reload session for the desktop app.

Uses the prebuilt, stripped debug APK produced by the normal FlutterWay build
pipeline:

    flutter run -d <serial> --debug --use-application-binary <signed.apk>

Then writes lib/main.dart and sends `r` on stdin for hot reload, `R` for hot
restart, and `q` to stop. No Enter key is required from the student.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque

try:
    from gui import paths
except ImportError:
    import paths

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
RELOAD_RE = re.compile(r"Reloaded .*? in ([\d,]+)ms")
VM_RE = re.compile(r"A Dart VM Service.*?(http://\S+)")


class HotReloadSession:
    def __init__(self):
        self.proc = None
        self.reader_thread = None
        self.lock = threading.RLock()
        self.logs = deque(maxlen=600)
        self.running = False
        self.ready = False
        self.last_reload_ms = None
        self.last_error = None
        self.project_path = None
        self.serial = None
        self.vm_service = None
        self.used_prebuilt = False
        self._last_request = 0.0
        self._stop_reader = False
        self._base_hash = None
        self._main_bom = False
        self._main_newline = "\n"
        atexit.register(self.stop)

    # ------------------------------------------------------------------ helpers
    def _command(self, serial: str, apk: str | None) -> list[str]:
        command = [paths.flutter_bat(), "run", "-d", serial, "--debug"]
        if apk:
            command.extend(["--use-application-binary", apk])
        return command

    def _append(self, raw_line: str) -> None:
        line = ANSI_RE.sub("", raw_line).rstrip()
        if not line:
            return
        with self.lock:
            self.logs.append(line)
            if "Flutter run key commands" in line or "r Hot reload." in line:
                self.ready = True
            match = RELOAD_RE.search(line)
            if match:
                try:
                    self.last_reload_ms = int(match.group(1).replace(",", ""))
                except Exception:
                    pass
            vm = VM_RE.search(line)
            if vm:
                self.vm_service = vm.group(1)
                self.ready = True
            if ("Error" in line or "Exception" in line or "FAILURE" in line) and "Error" in line:
                self.last_error = line

    def _reader(self) -> None:
        try:
            for line in self.proc.stdout:
                self._append(line)
        except Exception:
            pass
        with self.lock:
            self.running = False
            self.ready = False

    def _send(self, command: str) -> bool:
        with self.lock:
            if not self.proc or not self.proc.stdin or self.proc.poll() is not None:
                return False
            try:
                self.proc.stdin.write(command + "\n")
                self.proc.stdin.flush()
                self._last_request = time.time()
                return True
            except Exception as exc:
                self.last_error = str(exc)
                return False

    def _signed_apk(self):
        if not self.project_path:
            return None
        base = os.path.join(self.project_path, "build", "app", "outputs", "flutter-apk")
        for name in ("app-debug.signed.apk",):
            candidate = os.path.join(base, name)
            if os.path.exists(candidate):
                return candidate
        return None

    def _environment(self):
        env = os.environ.copy()
        jdk = paths.jdk_home()
        if jdk:
            env["JAVA_HOME"] = jdk
            env["PATH"] = os.path.join(jdk, "bin") + ";" + env.get("PATH", "")
        flutter_bin = os.path.dirname(paths.flutter_bat())
        if os.path.isdir(flutter_bin):
            env["PATH"] = flutter_bin + ";" + env.get("PATH", "")
        adb_dir = os.path.dirname(paths.adb_path())
        if adb_dir and os.path.isdir(adb_dir):
            env["PATH"] = adb_dir + ";" + env.get("PATH", "")
        return env

    # ------------------------------------------------------------------- public
    def start(self, project_path, serial=None):
        with self.lock:
            if self.running:
                return {"success": True, **self.status()}
            project_path = os.path.abspath(project_path or "")
            main_dart = os.path.join(project_path, "lib", "main.dart")
            if not os.path.exists(main_dart):
                return {"success": False, "error": "المشروع لا يحتوي lib/main.dart"}
            if not serial:
                return {"success": False, "error": "لم يتم العثور على هاتف متصل"}
            apk = None
            base = os.path.join(project_path, "build", "app", "outputs", "flutter-apk")
            for name in ("app-debug.signed.apk",):
                candidate = os.path.join(base, name)
                if os.path.exists(candidate):
                    apk = candidate
                    break
            if not apk:
                full_apk = os.path.join(base, "app-debug.apk")
                if os.path.exists(full_apk):
                    try:
                        try:
                            from gui import android_apk
                        except ImportError:
                            import android_apk
                        apk = android_apk.optimize_apk(full_apk)
                    except Exception:
                        apk = full_apk

            self.project_path = project_path
            self.serial = serial
            self.logs.clear()
            self.last_error = None
            self.last_reload_ms = None
            self.ready = False
            try:
                raw_main = self._read_bytes(main_dart)
                self._base_hash = self._sha(raw_main)
                self._main_bom = raw_main.startswith(b"\xef\xbb\xbf")
                self._main_newline = "\r\n" if b"\r\n" in raw_main else "\n"
            except Exception:
                self._base_hash = None
            self.used_prebuilt = bool(apk)
            self.running = True
            command = self._command(serial, apk)
            if not apk:
                self._append("لا يوجد APK جاهز — سنبني المشروع الآن. أول مرة قد تأخذ دقائق.")
            try:
                self.proc = subprocess.Popen(
                    command,
                    cwd=project_path,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace",
                    env=self._environment(),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self.reader_thread = threading.Thread(target=self._reader, daemon=True)
                self.reader_thread.start()
            except Exception as exc:
                self.running = False
                return {"success": False, "error": f"تعذر تشغيل flutter run: {exc}"}

        deadline = time.time() + (300 if not self.used_prebuilt else 150)
        while time.time() < deadline:
            with self.lock:
                if self.ready:
                    return {"success": True, **self.status()}
                if self.proc and self.proc.poll() is not None:
                    tail = "\n".join(list(self.logs)[-8:])
                    self.stop()
                    return {"success": False, "error": "انتهت جلسة Flutter قبل الاتصال.\n" + tail}
            time.sleep(0.25)

        self.stop()
        return {"success": False, "error": "انتهت المهلة قبل أن تستجيب جلسة Flutter."}

    def _main_path(self) -> str:
        return os.path.join(self.project_path, "lib", "main.dart")

    @staticmethod
    def _sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _read_bytes(path: str) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def _rotate_backup(self, path: str, data: bytes) -> None:
        """Keep the last three versions as main.dart.bak / .bak.1 / .bak.2."""
        try:
            bak = path + ".bak"
            if os.path.exists(bak):
                for index in (2, 1):
                    older = f"{path}.bak.{index}"
                    newer = f"{path}.bak.{index - 1}" if index > 1 else bak
                    if os.path.exists(newer):
                        os.replace(newer, older)
            with open(bak, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            pass

    def _atomic_write(self, path: str, data: bytes) -> None:
        part = f"{path}.tmp-{uuid.uuid4().hex[:8]}"
        try:
            with open(part, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(part, path)
        finally:
            if os.path.exists(part):
                try:
                    os.unlink(part)
                except Exception:
                    pass

    def read_main(self):
        if not self.project_path:
            return {"success": False, "error": "لم تبدأ جلسة Hot Reload بعد"}
        path = self._main_path()
        try:
            raw = self._read_bytes(path)
            self._base_hash = self._sha(raw)
            self._main_bom = raw.startswith(b"\xef\xbb\xbf")
            self._main_newline = "\r\n" if b"\r\n" in raw else "\n"
            text = raw.decode("utf-8-sig", "replace")
            return {"success": True, "content": text, "path": path, "hash": self._base_hash}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def save(self, content, force_new: bool = False):
        with self.lock:
            if not self.project_path:
                return {"success": False, "error": "لم تبدأ جلسة Hot Reload بعد"}
            path = self._main_path()
            text = content or ""
            max_bytes = 2 * 1024 * 1024
            if len(text.encode("utf-8")) > max_bytes:
                return {"success": False, "code": "too_large",
                        "error": "الملف أكبر من 2 MB؛ لن نحفظه تلقائياً."}

            if self._main_bom and not text.startswith("\ufeff"):
                text = "\ufeff" + text
            if self._main_newline == "\r\n":
                text = text.replace("\r\n", "\n").replace("\n", "\r\n")
            data = text.encode("utf-8")

            try:
                current = self._read_bytes(path)
            except FileNotFoundError:
                current = None
            except Exception as exc:
                return {"success": False, "error": f"تعذر قراءة الملف: {exc}"}

            if force_new:
                copy_path = os.path.join(self.project_path, "lib", "main.flutterway.dart")
                try:
                    self._atomic_write(copy_path, data)
                except Exception as exc:
                    return {"success": False, "error": f"تعذر حفظ النسخة: {exc}"}
                return {"success": True, "saved": True, "reload_sent": False,
                        "path": copy_path, "code": "saved_copy",
                        "message": "حُفظت نسختك في main.flutterway.dart بدون لمس الأصل."}

            current_hash = self._sha(current) if current is not None else None
            if self._base_hash and current_hash != self._base_hash:
                return {
                    "success": False,
                    "code": "external_change",
                    "message": "الملف تغيّر من خارج FlutterWay. لم نحفظ فوق تعديلك.",
                    "current_hash": current_hash,
                    "base_hash": self._base_hash,
                }

            try:
                if current is not None:
                    self._rotate_backup(path, current)
                self._atomic_write(path, data)
                if self._read_bytes(path) != data:
                    raise OSError("read-back mismatch")
            except Exception as exc:
                return {"success": False, "error": f"تعذر حفظ الملف: {exc}"}

            self._base_hash = self._sha(data)
            sent = False
            if self.running and self.ready:
                sent = self._send("r")
            return {
                "success": True,
                "saved": True,
                "reload_sent": sent,
                "hash": self._base_hash,
                "message": "تم الحفظ وإرسال Hot Reload" if sent else "تم الحفظ؛ الجلسة غير جاهزة بعد",
            }

    def action(self, action):
        action = (action or "").lower()
        if action == "reload":
            return {"success": self._send("r"), "message": "تم إرسال Hot Reload"}
        if action == "restart":
            return {"success": self._send("R"), "message": "تم إرسال Hot Restart"}
        if action == "stop":
            self.stop()
            return {"success": True, "message": "تم إيقاف الجلسة"}
        return {"success": False, "error": f"إجراء غير معروف: {action}"}

    def status(self):
        with self.lock:
            return {
                "running": self.running and self.proc is not None and self.proc.poll() is None,
                "ready": self.ready,
                "project_path": self.project_path,
                "serial": self.serial,
                "last_reload_ms": self.last_reload_ms,
                "last_error": self.last_error,
                "vm_service": self.vm_service,
                "used_prebuilt": self.used_prebuilt,
                "logs": list(self.logs)[-80:],
            }

    def stop(self):
        with self.lock:
            proc = self.proc
            self.proc = None
            self.running = False
            self.ready = False
        if not proc:
            return
        try:
            if proc.stdin and proc.poll() is None:
                proc.stdin.write("q\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
