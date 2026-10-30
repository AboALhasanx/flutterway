"""Local diagnostics and opt-in GitHub issue reporting for FlutterWay.

Privacy contract
----------------
* ``logs/local/flutterway.log`` is a raw developer log.  It is **never** put in
  a shareable report, ZIP, clipboard payload, or GitHub body.
* Only redacted, schema-limited data leaves the machine, and only when the
  student explicitly asks for it.
* Redaction is mechanical and cannot be perfect.  Every report says so.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import sys
import threading
import traceback
import urllib.parse
import uuid
import webbrowser
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from gui import paths
    from gui import version
except ImportError:  # pragma: no cover - source layout fallback
    import paths  # type: ignore
    import version  # type: ignore

GITHUB_REPO = "https://github.com/AboALhasanx/flutterway"
MAX_ISSUE_BODY = 3000
MAX_EVENTS = 500
MAX_ZIP_BYTES = 2 * 1024 * 1024
MAX_EXTRA_CHARS = 2000
SCHEMA_VERSION = 2

_last_error = ""
_logger = None
_log_path = None
_hooks_installed = False
_hook_running = False
_previous_excepthook = None
_previous_thread_hook = None
_events_truncated = False

__version__ = version.__version__

# Fields accepted for each shareable event.  Anything else is dropped.
EVENT_FIELDS: dict[str, frozenset[str]] = {
    "app_started": frozenset({"version", "frozen"}),
    "setup_started": frozenset({"mode"}),
    "setup_failed": frozenset({"stage", "code", "percent", "duration_ms"}),
    "setup_finished": frozenset({"duration_ms", "vscode_ok"}),
    "build_started": frozenset({"build_id", "mode"}),
    "build_finished": frozenset({"build_id", "stage", "success", "returncode", "error_code", "duration_ms"}),
    "install_finished": frozenset({"build_id", "success", "returncode", "code"}),
    "launch_finished": frozenset({"build_id", "success", "seconds"}),
    "hot_reload_started": frozenset({"used_prebuilt"}),
    "hot_reload_finished": frozenset({"success", "reload_ms", "code"}),
    "hot_reload_conflict": frozenset({"code"}),
    "webview_error": frozenset({"code", "phase"}),
    "dev_reset": frozenset({"action", "success"}),
    "report_saved": frozenset({"include_events", "bytes"}),
    "app_exit": frozenset({"reason"}),
}

# Extra keys accepted in reports; unknown keys are dropped, not forwarded.
EXTRA_FIELDS = frozenset({
    "client_error", "url", "line", "stage", "error_code", "returncode", "build_id",
})

_SAFE_PATH_ROOTS = (
    "c:\\flutter",
    "c:\\android",
    "c:\\g\\",
    "c:\\windows",
)


# --------------------------------------------------------------------------- paths
def logs_dir() -> Path:
    path = Path(paths.data_dir()) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_log_dir() -> Path:
    path = logs_dir() / "local"
    path.mkdir(parents=True, exist_ok=True)
    return path


def events_dir() -> Path:
    path = logs_dir() / "events"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = logs_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def client_errors_path() -> Path:
    return logs_dir() / "client-errors.jsonl"


# ------------------------------------------------------------------------ logging
def configure_logging() -> Path:
    """Create the *local only* raw log.  This file is never shared."""
    global _logger, _log_path
    if _logger is not None and _log_path is not None:
        return _log_path
    log_path = local_log_dir() / "flutterway.log"
    logger = logging.getLogger("flutterway")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        if log_path.exists() and log_path.stat().st_size == 0:
            try:
                handler.emit(
                    logging.LogRecord(
                        "flutterway", logging.INFO, __file__, 0,
                        "LOCAL ONLY — this raw log is never included in shared reports",
                        None, None,
                    )
                )
            except Exception:
                pass
    _logger = logger
    _log_path = log_path
    return log_path


def log(message: str, level: str = "info") -> None:
    configure_logging()
    if _logger is None:
        return
    getattr(_logger, level, _logger.info)(str(message))


def log_tail(lines: int = 120) -> str:
    """Raw tail for local debugging only.  Never call this for shareable output."""
    configure_logging()
    if not _log_path or not _log_path.exists():
        return ""
    try:
        content = _log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except Exception:
        return ""


# ---------------------------------------------------------------------- redaction
@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    def total(self) -> int:
        return sum(self.counts.values())


_HOME_WINDOWS = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\r\n]+", re.IGNORECASE)
_HOME_POSIX = re.compile(r"/(?:Users|home)/[^/\s\r\n]+")
_ENV_HOME = re.compile(r"%USERPROFILE%", re.IGNORECASE)
_PROGRAM_FILES = re.compile(
    r"[A-Za-z]:[\\/]+Program Files(?: \(x86\))?(?:[\\/][^\"'<>|\r\n]*)?", re.IGNORECASE
)
_UNC_PATH = re.compile(r"\\\\[^\\\s]+\\[^\s\"'<>|]+")
_ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/](?:[^\\/\s\"'<>|:*?\r\n]+[\\/])*[^\\/\s\"'<>|:*?\r\n]+")

_GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
_OTHER_TOKENS = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16})\b"
)
_ASSIGNMENT_SECRET = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token|client[_-]?secret)"
    r"(\s*[=:]\s*)([^\s,;\"']+)"
)
_BEARER = re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s\"']+)")
_CONNECTION = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s\"'<>]+", re.IGNORECASE
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _replace(pattern: re.Pattern, replacement, text: str, counts: dict, key: str) -> str:
    def sub(match):
        _bump(counts, key)
        return replacement(match) if callable(replacement) else replacement

    return pattern.sub(sub, text)


def _redact_path(match: re.Match) -> str:
    value = match.group(0).lower()
    for root in _SAFE_PATH_ROOTS:
        if value.startswith(root):
            return match.group(0)
    return "<path>"


def redact(text: str) -> RedactionResult:
    """Mechanically redact personal data and secrets.  Idempotent by design."""
    result = RedactionResult(str(text or ""))
    counts: dict[str, int] = {}

    # App-owned roots first so they map to stable placeholders.
    try:
        roots = [
            (str(paths.default_project_path()), "<project>"),
            (str(paths.lecture_projects_dir()), "<projects-dir>"),
            (str(paths.data_dir()), "<appdata>"),
        ]
    except Exception:
        roots = []
    for value, placeholder in roots:
        if value and value in result.text:
            counts["paths"] = counts.get("paths", 0) + result.text.count(value)
            result.text = result.text.replace(value, placeholder)

    result.text = _replace(_ENV_HOME, "<home>", result.text, counts, "home")
    result.text = _replace(_HOME_WINDOWS, "<home>", result.text, counts, "home")
    result.text = _replace(_HOME_POSIX, "<home>", result.text, counts, "home")
    result.text = _replace(_PROGRAM_FILES, "<program-files>", result.text, counts, "paths")
    result.text = _replace(_UNC_PATH, "<unc-path>", result.text, counts, "paths")
    result.text = _replace(_ABS_PATH, _redact_path, result.text, counts, "paths")

    result.text = _replace(_GITHUB_TOKEN, "<token>", result.text, counts, "tokens")
    result.text = _replace(_OTHER_TOKENS, "<token>", result.text, counts, "tokens")
    result.text = _replace(_BEARER, lambda m: m.group(1) + "<redacted>", result.text, counts, "secrets")
    result.text = _replace(
        _ASSIGNMENT_SECRET,
        lambda m: f"{m.group(1)}{m.group(2)}<redacted>",
        result.text,
        counts,
        "secrets",
    )
    result.text = _replace(_CONNECTION, "<connection-string>", result.text, counts, "connection_strings")
    result.text = _replace(_EMAIL, "<email>", result.text, counts, "emails")

    result.counts = counts
    return result


def _sanitize_text(text: str) -> str:
    """Backward-compatible helper used across the code base."""
    return redact(text).text


def _sanitize_value(value):
    if isinstance(value, str):
        return redact(value).text
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    return value


# ------------------------------------------------------------------------- events
def _trim_events(path: Path) -> None:
    global _events_truncated
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return
    if len(lines) > MAX_EVENTS * 2:
        path.write_text("\n".join(lines[-MAX_EVENTS:]) + "\n", encoding="utf-8")
        _events_truncated = True


def log_event(event_code: str, **fields) -> bool:
    """Append one allow-listed, redacted event.  Unknown codes are rejected."""
    allowed = EVENT_FIELDS.get(str(event_code))
    if allowed is None:
        return False
    payload = {"ts": datetime.now().isoformat(timespec="seconds"), "event": str(event_code)}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if isinstance(value, str):
            payload[key] = redact(value).text[:200]
        elif isinstance(value, (int, float, bool)) or value is None:
            payload[key] = value
    path = events_dir() / "events.jsonl"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        _trim_events(path)
    except Exception:
        return False
    return True


def read_events(limit: int = MAX_EVENTS) -> list[dict]:
    path = events_dir() / "events.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except Exception:
        return []
    events = []
    for line in lines:
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("event") in EVENT_FIELDS:
            events.append(data)
    return events


# ------------------------------------------------------------------------- report
def system_info() -> dict:
    info = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "locale": os.environ.get("LANG", ""),
    }
    try:
        import webview
        info["webview"] = getattr(webview, "__version__", "unknown")
    except Exception:
        info["webview"] = "unknown"
    return {k: redact(str(v)).text for k, v in info.items()} | {
        "frozen": info["frozen"],
    }


def build_commit() -> str:
    injected = (
        os.environ.get("FLUTTERWAY_COMMIT", "").strip()
        or str(getattr(version, "BUILD_COMMIT", "") or "").strip()
    )
    if injected and injected.lower() != "unknown":
        return injected
    if not getattr(sys, "frozen", False):
        try:
            import subprocess
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(root), capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip() or "unknown"
        except Exception:
            pass
    return "unknown"


def build_date() -> str:
    injected = os.environ.get("FLUTTERWAY_BUILD_DATE", "").strip()
    if injected:
        return injected
    return str(getattr(version, "BUILD_DATE", "unknown") or "unknown")


def app_commit() -> str:
    """Backward-compatible alias."""
    return build_commit()


def _clean_extra(extra: dict | None, counts: dict[str, int]) -> dict:
    cleaned: dict = {}
    for key, value in (extra or {}).items():
        if key not in EXTRA_FIELDS:
            continue
        if isinstance(value, dict):
            nested = {}
            for sub_key, sub_value in value.items():
                if sub_key not in EXTRA_FIELDS and sub_key not in {"message", "stack", "source", "phase"}:
                    continue
                if isinstance(sub_value, str):
                    result = redact(sub_value)
                    nested[sub_key] = result.text[:MAX_EXTRA_CHARS]
                    for name, amount in result.counts.items():
                        counts[name] = counts.get(name, 0) + amount
                elif isinstance(sub_value, (int, float, bool)) or sub_value is None:
                    nested[sub_key] = sub_value
            cleaned[key] = nested
        elif isinstance(value, str):
            result = redact(value)
            cleaned[key] = result.text[:MAX_EXTRA_CHARS]
            for name, amount in result.counts.items():
                counts[name] = counts.get(name, 0) + amount
        elif isinstance(value, (int, float, bool)) or value is None:
            cleaned[key] = value
    return cleaned


def build_report(
    message: str,
    stack: str = "",
    phase: str = "",
    description: str = "",
    include_logs: bool = False,
    source: str = "app",
    extra: dict | None = None,
    include_events: bool = False,
) -> dict:
    """Build a shareable report (schema 2).  Raw logs are never included."""
    counts: dict[str, int] = {}

    def scrub(value: str, limit: int) -> str:
        result = redact(value)
        for name, amount in result.counts.items():
            counts[name] = counts.get(name, 0) + amount
        return result.text[:limit]

    events = read_events() if include_events else []
    report = {
        "schema": SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "build": {
            "version": __version__,
            "commit": build_commit(),
            "date": build_date(),
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "source": str(source)[:40],
        "phase": str(phase or "manual")[:40],
        "message": scrub(message or "خطأ غير معروف", 2000),
        "description": scrub(description, 2000),
        "stack": scrub(stack, 6000),
        "system": system_info(),
        "extra": _clean_extra(extra, counts),
        "events": events,
        "redactions": counts,
        "limits": {
            "events_included": bool(include_events),
            "events_truncated": _events_truncated,
            "max_events": MAX_EVENTS,
        },
    }
    return report


def _redaction_summary(report: dict) -> str:
    counts = report.get("redactions") or {}
    if not counts:
        return "لم تُكتشف بيانات شخصية معروفة."
    labels = {
        "home": "مسارات منزل",
        "paths": "مسارات",
        "tokens": "رموز",
        "secrets": "أسرار",
        "emails": "بريد",
        "connection_strings": "روابط اتصال",
    }
    parts = [f"{labels.get(k, k)}: {v}" for k, v in sorted(counts.items())]
    return "أُخفيت " + "، ".join(parts) + "."


def report_markdown(report: dict) -> str:
    build = report.get("build") or {}
    system = report.get("system") or {}
    lines = [
        "## ملخص",
        report.get("message", ""),
        "",
        "## الوصف",
        report.get("description", "") or "—",
        "",
        "## البيئة",
        f"- الإصدار: `{build.get('version', '?')}`",
        f"- الكوميت: `{build.get('commit', '?')}`",
        f"- المصدر: `{report.get('source', '?')}`",
        f"- المرحلة: `{report.get('phase', '?')}`",
        f"- النظام: `{system.get('os', '?')}`",
        f"- Python: `{system.get('python', '?')}`",
        "",
        "## التنقية",
        _redaction_summary(report),
        "",
        "_التنقية آلية وقد لا تكتشف كل المعلومات الحساسة. راجع المحتوى قبل المشاركة._",
    ]
    stack = report.get("stack", "")
    if stack:
        lines += ["", "## Stack trace", "~~~", stack[-5000:], "~~~"]
    if report.get("extra"):
        lines += [
            "", "## تفاصيل إضافية", "```json",
            json.dumps(report["extra"], ensure_ascii=False, indent=2)[:MAX_EXTRA_CHARS],
            "```",
        ]
    events = report.get("events") or []
    if events:
        lines += ["", f"## أحداث ({len(events)})", "```json",
                  json.dumps(events[-50:], ensure_ascii=False, indent=2)[:4000], "```"]
    lines += ["", "_السجل المحلي الخام غير مرفق بهذا التقرير._"]
    return "\n".join(lines).strip()


def github_issue_url(report: dict) -> str:
    title = f"[Bug] {report.get('message', 'خطأ')[:90]}"
    body = report_markdown(report)
    if len(body) > MAX_ISSUE_BODY:
        body = body[:MAX_ISSUE_BODY] + "\n\n… اقتُطع النص. أرفق ملف ZIP الكامل إن أمكن."
    query = urllib.parse.urlencode({"title": title, "body": body, "labels": "bug"})
    return f"{GITHUB_REPO}/issues/new?{query}"


def _shareable_report(report: dict, include_events: bool) -> dict:
    clean = {
        key: value
        for key, value in report.items()
        if key not in ("logs", "raw_log", "events")
    }
    if include_events:
        clean["events"] = report.get("events") or read_events()
    return clean


def _manifest(entries: dict[str, bytes]) -> dict:
    files = []
    for name, payload in entries.items():
        files.append({
            "name": name,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    return {"schema": 1, "files": files}


def save_report_zip(report: dict, include_events: bool = False) -> str:
    """Write a shareable ZIP atomically.  Never contains the raw log."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = reports_dir() / f"flutterway-report-{stamp}-{uuid.uuid4().hex[:8]}.zip"
    clean = _shareable_report(report, include_events)
    entries: dict[str, bytes] = {
        "report.json": json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8"),
        "report.md": report_markdown(clean).encode("utf-8"),
        "environment.json": json.dumps(
            {
                "os": clean.get("system", {}).get("os", ""),
                "python": clean.get("system", {}).get("python", ""),
                "webview": clean.get("system", {}).get("webview", ""),
                "version": clean.get("build", {}).get("version", ""),
                "commit": clean.get("build", {}).get("commit", ""),
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8"),
    }
    if include_events:
        events = clean.get("events") or []
        entries["events.jsonl"] = "\n".join(
            json.dumps(event, ensure_ascii=False) for event in events[-MAX_EVENTS:]
        ).encode("utf-8")
    entries["manifest.json"] = json.dumps(_manifest(entries), ensure_ascii=False, indent=2).encode("utf-8")

    part = target.with_suffix(".part")
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        if part.stat().st_size > MAX_ZIP_BYTES:
            raise ValueError("التقرير أكبر من الحد المسموح (2 MB).")
        os.replace(part, target)
    finally:
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
    log(f"Saved diagnostics report ({'with' if include_events else 'without'} events): {target}")
    return str(target)


def open_github_issue(report: dict) -> dict:
    url = github_issue_url(report)
    try:
        opened = bool(webbrowser.open(url))
    except Exception as exc:
        log(f"Could not open GitHub issue: {exc}", "error")
        return {"opened": False, "url": url, "error": str(exc)}
    if not opened:
        log("Could not open GitHub issue: browser returned False", "error")
        return {"opened": False, "url": url, "error": "تعذر فتح المتصفح"}
    log(f"Opened GitHub issue URL ({len(url)} chars)")
    return {"opened": True, "url": url, "error": None}


def _rotate_client_errors(path: Path, max_lines: int = 200) -> None:
    try:
        if path.exists() and path.stat().st_size > 512 * 1024:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            path.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def capture_client_error(payload: dict) -> dict:
    """Record a JS error locally without sending anything anywhere."""
    payload = payload or {}
    report = build_report(
        message=payload.get("message") or "JS error",
        stack=payload.get("stack", ""),
        phase=payload.get("phase", "webview"),
        source="webview",
        include_events=False,
        extra={"url": payload.get("url", ""), "line": payload.get("line", "")},
    )
    global _last_error
    _last_error = report["message"]
    log(f"WebView error: {report['message']} @ {report['phase']}", "error")
    log_event("webview_error", code="js_error", phase=str(report.get("phase", "webview")))
    path = client_errors_path()
    _rotate_client_errors(path)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return report


# --------------------------------------------------------------------------- hooks
def _write_crash(report: dict) -> None:
    target = reports_dir() / "last-crash.json"
    part = target.with_suffix(".part")
    try:
        part.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(part, target)
    finally:
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass


def install_exception_hooks() -> None:
    global _hooks_installed, _previous_excepthook, _previous_thread_hook
    if _hooks_installed:
        return
    _hooks_installed = True
    configure_logging()
    _previous_excepthook = sys.excepthook
    _previous_thread_hook = threading.excepthook

    def hook(exc_type, exc_value, exc_tb):
        global _last_error, _hook_running
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            return
        if _hook_running:
            return
        _hook_running = True
        try:
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _last_error = f"{exc_type.__name__}: {exc_value}"
            log("Unhandled exception:\n" + _sanitize_text(text), "error")
            try:
                _write_crash(build_report(
                    message=_last_error,
                    stack=text,
                    phase="unhandled",
                    source="python",
                ))
            except Exception:
                pass
        except Exception:
            pass
        finally:
            _hook_running = False
        try:
            if callable(_previous_excepthook):
                _previous_excepthook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    def thread_hook(args):
        if getattr(args, "exc_type", None) is None:
            return
        hook(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = hook
    threading.excepthook = thread_hook


def uninstall_exception_hooks() -> None:
    """Restore previous hooks (tests and clean shutdown)."""
    global _hooks_installed
    if not _hooks_installed:
        return
    if _previous_excepthook is not None:
        sys.excepthook = _previous_excepthook
    if _previous_thread_hook is not None:
        threading.excepthook = _previous_thread_hook
    _hooks_installed = False


def diagnostics_info() -> dict:
    return {
        "version": __version__,
        "commit": build_commit(),
        "repo": GITHUB_REPO,
        "log_path": _sanitize_text(str(configure_logging())),
        "events_path": _sanitize_text(str(events_dir() / "events.jsonl")),
        "reports_dir": _sanitize_text(str(reports_dir())),
        "last_error": _sanitize_text(_last_error),
    }
