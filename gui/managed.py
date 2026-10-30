"""Ownership markers for folders FlutterWay created.

A folder name is not proof of ownership.  FlutterWay writes a marker **only**
when it creates the folder itself; callers must treat a missing marker as
user content and leave it untouched.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

try:
    from gui.version import __version__
except ImportError:  # pragma: no cover
    from version import __version__

MARKER_NAME = ".flutterway-managed.json"
SCHEMA = 1
KINDS = frozenset({"sdk", "starter_project", "lecture_project", "gradle_home", "cache"})


def marker_path(path: str) -> str:
    return os.path.join(path, MARKER_NAME)


def read_marker(path: str) -> dict | None:
    try:
        with open(marker_path(path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("app") != "FlutterWay" or data.get("schema") != SCHEMA:
        return None
    return data


def is_managed(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    data = read_marker(path)
    return bool(data and data.get("kind") in KINDS)


def write_marker(path: str, kind: str) -> bool:
    """Write a marker only for a folder FlutterWay just created."""
    if kind not in KINDS or not os.path.isdir(path):
        return False
    target = marker_path(path)
    if os.path.exists(target):
        return False
    payload = {
        "app": "FlutterWay",
        "schema": SCHEMA,
        "kind": kind,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": __version__,
        "path": os.path.abspath(path),
    }
    part = target + ".tmp"
    try:
        with open(part, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, target)
        return True
    except Exception:
        return False
    finally:
        if os.path.exists(part):
            try:
                os.unlink(part)
            except Exception:
                pass


def classify(path: str) -> str:
    """Return managed_verified | managed_unverified | missing | user_content."""
    if not os.path.isdir(path):
        return "missing"
    if is_managed(path):
        return "managed_verified"
    # A folder with a Flutter project but no marker could be the student's own
    # work or a pre-marker FlutterWay project; both require explicit consent.
    if os.path.exists(os.path.join(path, "pubspec.yaml")):
        return "managed_unverified"
    return "user_content"
