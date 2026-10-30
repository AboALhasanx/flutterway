"""Verified downloads and safe archives.

Small building blocks for the setup path: hash verification before a file is
trusted, and zip extraction that refuses to escape its destination.
"""

from __future__ import annotations

import hashlib
import os
import zipfile


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
