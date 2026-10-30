"""Pinned Flutter SDK releases with checksum verification.

The setup flow must not depend on a moving `stable` branch.  This module reads
the official release manifest, picks the channel's current release, downloads
its archive once, verifies the SHA-256, extracts safely and swaps it into place
only after the new SDK proves usable.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from gui import downloads, paths
except ImportError:  # pragma: no cover
    import downloads  # type: ignore
    import paths  # type: ignore

RELEASES_URL = "https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json"
# Shipped with the app so a blocked/offline network cannot break setup.
_MANIFEST_NAME = os.path.join("data", "flutter_releases_windows.json")
BUNDLED_MANIFEST_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), _MANIFEST_NAME),
    os.path.join(getattr(__import__("sys"), "_MEIPASS", os.path.dirname(__file__)), "gui", _MANIFEST_NAME),
    os.path.join(getattr(__import__("sys"), "_MEIPASS", os.path.dirname(__file__)), _MANIFEST_NAME),
]
BUNDLED_MANIFEST = BUNDLED_MANIFEST_CANDIDATES[0]


@dataclass
class FlutterRelease:
    version: str
    archive: str
    sha256: str
    size: int = 0
    channel: str = "stable"

    @property
    def archive_name(self) -> str:
        return os.path.basename(self.archive.replace("\\", "/"))


def parse_release_manifest(data: dict, channel: str = "stable") -> FlutterRelease | None:
    """Pick the release the official manifest marks as current for a channel."""
    channel = (channel or "stable").strip().lower()
    releases = (data or {}).get("releases") or []
    current = ((data or {}).get("current_release") or {}).get(channel)
    chosen = None
    if current:
        for item in releases:
            if item.get("hash") == current and item.get("channel") == channel:
                chosen = item
                break
    if chosen is None:
        candidates = [item for item in releases if item.get("channel") == channel]
        if candidates:
            chosen = max(candidates, key=lambda item: str(item.get("release_date", "")))
    if not chosen:
        return None
    checksum = str(chosen.get("sha256") or "").strip().lower()
    archive = str(chosen.get("archive") or "").strip()
    version = str(chosen.get("version") or "").strip()
    if len(checksum) != 64 or not archive or not version:
        return None
    return FlutterRelease(
        version=version,
        archive=archive,
        sha256=checksum,
        size=int(chosen.get("size") or 0),
        channel=channel,
    )


def load_bundled_manifest(path: str | None = None) -> dict | None:
    candidates = [path] if path else BUNDLED_MANIFEST_CANDIDATES
    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if data:
                return data
        except Exception:
            continue
    return None


def resolve_flutter_release(channel: str = "stable", timeout: int = 30) -> FlutterRelease | None:
    """Prefer the live manifest; fall back to the pinned one shipped with the app."""
    import urllib.request

    try:
        request = urllib.request.Request(RELEASES_URL, headers={"User-Agent": "FlutterWay/1.3"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        release = parse_release_manifest(data, channel)
        if release is not None:
            return release
    except Exception as exc:
        print("Flutter release manifest error:", exc)
    bundled = load_bundled_manifest()
    return parse_release_manifest(bundled, channel) if bundled else None


def _download(url: str, target: str, progress=None, timeout: int = 120) -> bool:
    import urllib.request

    part = target + ".part"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "FlutterWay/1.3"})
        with urllib.request.urlopen(request, timeout=timeout) as response, open(part, "wb") as output:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(int(done * 100 / total))
        os.replace(part, target)
        return True
    except Exception as exc:
        print("Flutter archive download error:", exc)
        try:
            if os.path.exists(part):
                os.remove(part)
        except Exception:
            pass
        return False


def install_flutter_archive(target: str, release: FlutterRelease, progress=None,
                            downloader=None) -> dict:
    """Install a verified Flutter archive at ``target`` without losing the old SDK."""
    if release is None or not release.sha256:
        return {"success": False, "error": "بيانات إصدار Flutter غير مكتملة."}
    cache = Path(paths.data_dir()) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive_path = cache / release.archive_name

    if not archive_path.exists() or not downloads.verify_file(
        str(archive_path), release.sha256, release.size
    ).get("ok"):
        url = "https://storage.googleapis.com/flutter_infra_release/releases/" + release.archive.replace("\\", "/")
        downloader = downloader or _download
        if not downloader(url, str(archive_path), progress):
            return {"success": False, "error": "تعذر تنزيل أرشيف Flutter."}
        check = downloads.verify_file(str(archive_path), release.sha256, release.size)
        if not check.get("ok"):
            try:
                archive_path.unlink()
            except Exception:
                pass
            return {"success": False, "error": f"أرشيف Flutter لا يطابق البصمة ({check.get('reason')})."}

    extract_dir = cache / f"flutter_extract_{release.version}"
    shutil.rmtree(extract_dir, ignore_errors=True)
    result = downloads.safe_extract_zip(str(archive_path), str(extract_dir))
    if not result.get("ok"):
        shutil.rmtree(extract_dir, ignore_errors=True)
        return {"success": False, "error": f"أرشيف Flutter غير آمن: {result.get('reason')}"}

    root = None
    for candidate in [extract_dir] + [p for p in extract_dir.iterdir() if p.is_dir()]:
        if (candidate / "bin" / "flutter.bat").exists():
            root = candidate
            break
    if root is None:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return {"success": False, "error": "الأرشيف لا يحتوي bin/flutter.bat."}

    target_path = Path(target)
    backup = None
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            backup = target_path.with_name(target_path.name + f".old-{int(time.time())}")
            os.replace(target_path, backup)
        shutil.move(str(root), str(target_path))
        if not (target_path / "bin" / "flutter.bat").exists():
            raise RuntimeError("flutter.bat غير موجود بعد التثبيت")
    except Exception as exc:
        if backup is not None and backup.exists() and not target_path.exists():
            try:
                os.replace(backup, target_path)
            except Exception:
                pass
        shutil.rmtree(extract_dir, ignore_errors=True)
        return {"success": False, "error": f"تعذر تركيب Flutter: {exc}"}

    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
    shutil.rmtree(extract_dir, ignore_errors=True)
    return {"success": True, "path": str(target_path), "version": release.version}
