"""Verified downloads and safe archives.

Small building blocks for the setup path: hash verification before a file is
trusted, and zip extraction that refuses to escape its destination.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import urllib.error
import zipfile


class DownloadCancelled(Exception):
    """Raised by a progress callback to stop while preserving the .part file."""


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: str, expected_sha256: str, min_bytes: int = 0) -> dict:
    """Return {ok, reason, size, sha256}. Never raises for a missing file."""
    expected = str(expected_sha256 or "").strip().lower()
    if not expected:
        return {"ok": False, "reason": "missing_checksum", "size": 0, "sha256": ""}
    if not os.path.isfile(path):
        return {"ok": False, "reason": "missing_file", "size": 0, "sha256": ""}
    size = os.path.getsize(path)
    if size < int(min_bytes or 0):
        return {"ok": False, "reason": "too_small", "size": size, "sha256": ""}
    actual = sha256_file(path)
    if actual.lower() != expected:
        return {"ok": False, "reason": "checksum_mismatch", "size": size, "sha256": actual}
    return {"ok": True, "reason": None, "size": size, "sha256": actual}


def resumable_download(url: str, destination: str, progress=None, timeout: int = 60,
                       retries: int = 3, chunk_size: int = 1024 * 1024) -> dict:
    """Download to ``.part`` and resume only when the server confirms byte ranges.

    The partial file is retained after transient errors and promoted atomically
    only after the advertised object length has arrived. Callers must still
    verify a trusted checksum before extracting or using the downloaded bytes.
    """
    import urllib.request

    part = destination + ".part"
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    last_error = "download failed"
    for attempt in range(max(1, int(retries))):
        offset = os.path.getsize(part) if os.path.isfile(part) else 0
        headers = {"User-Agent": "FlutterWay/1.3"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", None) or response.getcode()
                content_range = response.headers.get("Content-Range", "")
                append = False
                total = 0
                if offset and status == 206:
                    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", content_range.strip(), re.I)
                    if match and int(match.group(1)) == offset:
                        append = True
                        total = 0 if match.group(3) == "*" else int(match.group(3))
                    else:
                        # Invalid/mismatched range response: retry cleanly, never corrupt the file.
                        with open(part, "wb"):
                            pass
                        last_error = f"server returned invalid Content-Range: {content_range!r}"
                        continue
                elif status == 200:
                    offset = 0
                    total = int(response.headers.get("Content-Length") or 0)
                elif status == 206:
                    match = re.fullmatch(r"bytes\s+0-(\d+)/(\d+|\*)", content_range.strip(), re.I)
                    if not match:
                        last_error = f"server returned invalid initial Content-Range: {content_range!r}"
                        continue
                    total = 0 if match.group(2) == "*" else int(match.group(2))
                else:
                    last_error = f"unexpected HTTP status {status}"
                    continue

                mode = "ab" if append else "wb"
                received = offset if append else 0
                with open(part, mode) as output:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        output.write(chunk)
                        received += len(chunk)
                        if progress:
                            progress(received, total)
                actual = os.path.getsize(part)
                if total and actual != total:
                    last_error = f"incomplete download: received {actual} of {total} bytes"
                    continue
                os.replace(part, destination)
                return {"ok": True, "size": actual, "resumed_from": offset if append else 0}
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset:
                match = re.fullmatch(r"bytes\s+\*/(\d+)", exc.headers.get("Content-Range", "").strip(), re.I)
                if match and os.path.getsize(part) == int(match.group(1)):
                    os.replace(part, destination)
                    return {"ok": True, "size": os.path.getsize(destination), "resumed_from": offset}
            last_error = str(exc)
        except Exception as exc:
            if isinstance(exc, DownloadCancelled):
                return {"ok": False, "reason": "cancelled", "error": str(exc),
                        "partial_bytes": os.path.getsize(part) if os.path.isfile(part) else 0}
            last_error = str(exc)
        if attempt + 1 < max(1, int(retries)):
            time.sleep(min(0.25 * (2 ** attempt), 2.0))
    return {"ok": False, "reason": "download_failed", "error": last_error,
            "partial_bytes": os.path.getsize(part) if os.path.isfile(part) else 0}


def _is_within(base: str, target: str) -> bool:
    base_abs = os.path.normcase(os.path.realpath(os.path.abspath(base)))
    target_abs = os.path.normcase(os.path.realpath(os.path.abspath(target)))
    try:
        return os.path.commonpath([base_abs, target_abs]) == base_abs
    except ValueError:
        return False


def safe_extract_zip(archive_path: str, destination: str) -> dict:
    """Extract a zip, refusing absolute paths and ``..`` traversal."""
    destination = os.path.abspath(destination)
    try:
        with zipfile.ZipFile(archive_path) as bundle:
            for member in bundle.infolist():
                name = member.filename
                if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
                    return {"ok": False, "reason": "unsafe_path", "entry": name}
                if not _is_within(destination, os.path.join(destination, name)):
                    return {"ok": False, "reason": "unsafe_path", "entry": name}
            os.makedirs(destination, exist_ok=True)
            bundle.extractall(destination)
    except Exception as exc:
        return {"ok": False, "reason": "extract_failed", "error": str(exc)}
    return {"ok": True, "reason": None, "destination": destination}
