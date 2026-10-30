"""Local diagnostics and opt-in GitHub issue reporting for FlutterWay."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import threading
import traceback
import urllib.parse
import webbrowser
import zipfile
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from gui import paths
    from gui.version import __version__
except ImportError:  # pragma: no cover - source layout fallback
    import paths
    from version import __version__

GITHUB_REPO = "https://github.com/AboALhasanx/flutterway"
MAX_ISSUE_BODY = 3000
_last_error = ""
_logger = None
_log_path = None
_hooks_installed = False


def logs_dir() -> Path:
    path = Path(paths.data_dir()) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = logs_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging() -> Path:
    global _logger, _log_path
    if _logger is not None and _log_path is not None:
        return _log_path
    log_path = logs_dir() / "flutterway.log"
    logger = logging.getLogger("flutterway")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    _logger = logger
    _log_path = log_path
    return log_path


def log(message: str, level: str = "info") -> None:
    configure_logging()
    if _logger is None:
        return
    getattr(_logger, level, _logger.info)(str(message))


def _sanitize_text(text: str) -> str:
    text = str(text or "")
    home = os.path.expanduser("~")
    if home:
        text = text.replace(home, "<home>")
    text = re.sub(r"C:\\Users\\[^\\\s]+", r"C:\\Users\\<user>", text, flags=re.I)
    text = re.sub(r"/Users/[^/\s]+", "/Users/<user>", text)
    text = re.sub(r"/home/[^/\s]+", "/home/<user>", text)
    text = re.sub(r"gh[pousr]_[A-Za-z0-9_]{20,}", "<github-token>", text)
    text = re.sub(r"github_pat_[A-Za-z0-9_]{20,}", "<github-token>", text)
    text = re.sub(r"sk-[A-Za-z0-9]{20,}", "<api-key>", text)
    return text


def _sanitize_value(value):
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    return value


def log_tail(lines: int = 120) -> str:
    configure_logging()
    if not _log_path or not _log_path.exists():
        return ""
    try:
        content = _log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except Exception:
        return ""


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
    return info


def app_commit() -> str:
    override = os.environ.get("FLUTTERWAY_COMMIT", "").strip()
    if override:
        return override
    try:
        import subprocess
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def build_report(
    message: str,
    stack: str = "",
    phase: str = "",
    description: str = "",
    include_logs: bool = True,
    source: str = "app",
    extra: dict | None = None,
) -> dict:
    configure_logging()
    report = {
        "schema": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "version": __version__,
        "commit": app_commit(),
        "source": source,
        "phase": phase,
        "message": _sanitize_text(message or "خطأ غير معروف")[:2000],
        "stack": _sanitize_text(stack)[:6000],
        "description": _sanitize_text(description)[:2000],
        "system": system_info(),
        "logs": _sanitize_text(log_tail()) if include_logs else "",
        "extra": _sanitize_value(extra or {}),
    }
    return report


def report_markdown(report: dict) -> str:
    lines = [
        "## ملخص",
        _sanitize_text(report.get("message", "")),
        "",
        "## الوصف",
        _sanitize_text(report.get("description", "")) or "—",
        "",
        "## البيئة",
        f"- الإصدار: `{report.get('version', '?')}`",
        f"- الكوميت: `{report.get('commit', '?')}`",
        f"- المصدر: `{report.get('source', '?')}`",
        f"- المرحلة: `{report.get('phase', '?')}`",
        f"- النظام: `{report.get('system', {}).get('os', '?')}`",
        f"- Python: `{report.get('system', {}).get('python', '?')}`",
        "",
    ]
    stack = report.get("stack", "")
    if stack:
        lines += ["## Stack trace", "~~~", stack[-5000:], "~~~", ""]
    if report.get("extra"):
        lines += ["## تفاصيل إضافية", "```json", json.dumps(report["extra"], ensure_ascii=False, indent=2)[:2000], "```", ""]
    logs = report.get("logs", "")
    if logs:
        lines += ["## آخر السجل", "~~~", logs[-1500:], "~~~", ""]
    lines += [
        "",
        "_إذا احتجت السجل الكامل، استخدم «حفظ ملف تشخيص» وأرفق ملف ZIP._",
    ]
    return "\n".join(lines).strip()


def github_issue_url(report: dict) -> str:
    title = f"[Bug] {_sanitize_text(report.get('message', 'خطأ'))[:90]}"
    body = report_markdown(report)[:MAX_ISSUE_BODY]
    query = urllib.parse.urlencode({"title": title, "body": body, "labels": "bug"})
    return f"{GITHUB_REPO}/issues/new?{query}"


def save_report_zip(report: dict) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = reports_dir() / f"flutterway-report-{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))
        archive.writestr("report.md", report_markdown(report))
        configure_logging()
        if _log_path and _log_path.exists():
            archive.write(_log_path, "flutterway.log")
    log(f"Saved diagnostics report: {target}")
    return str(target)


def open_github_issue(report: dict) -> bool:
    url = github_issue_url(report)
    try:
        webbrowser.open(url)
        log(f"Opened GitHub issue URL ({len(url)} chars)")
        return True
    except Exception as exc:
        log(f"Could not open GitHub issue: {exc}", "error")
        return False


def capture_client_error(payload: dict) -> dict:
    """Log a JS error locally without sending anything automatically."""
    payload = payload or {}
    message = payload.get("message") or "JS error"
    report = build_report(
        message=message,
        stack=payload.get("stack", ""),
        phase=payload.get("phase", "webview"),
        source="webview",
        include_logs=False,
        extra={"url": payload.get("url", ""), "line": payload.get("line", "")},
    )
    global _last_error
    _last_error = report["message"]
    log(f"WebView error: {report['message']} @ {report['phase']}", "error")
    try:
        with (logs_dir() / "client-errors.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return report


def install_exception_hooks() -> None:
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    configure_logging()

    def hook(exc_type, exc_value, exc_tb):
        global _last_error
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _last_error = f"{exc_type.__name__}: {exc_value}"
        log("Unhandled exception:\n" + _sanitize_text(text), "error")
        try:
            report = build_report(
                message=_last_error,
                stack=text,
                phase="unhandled",
                source="python",
            )
            (reports_dir() / "last-crash.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def thread_hook(args):
        hook(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = hook
    threading.excepthook = thread_hook


def diagnostics_info() -> dict:
    return {
        "version": __version__,
        "commit": app_commit(),
        "repo": GITHUB_REPO,
        "log_path": _sanitize_text(str(configure_logging())),
        "reports_dir": _sanitize_text(str(reports_dir())),
        "last_error": _sanitize_text(_last_error),
    }
