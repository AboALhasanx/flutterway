"""Shared isolated test helpers for FlutterWay.

All values in this module are synthetic. ``temp_data_dir`` scopes the app data
override to a context and restores the caller's environment on exit.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator


CANARY_USER = "Jane Doe"
CANARY_PROJECT = r"D:\Projects\SecretClient"
CANARY_TOKEN = "ghp_" + "A" * 36
CANARY_EMAIL = "jane.doe@example.com"
CANARY_PASSWORD = "password=SuperSecret123"
CANARY_PATH = r"C:\Users\Jane Doe\Desktop\private"


def canary_values() -> dict[str, str]:
    """Return synthetic personal-data and secret values for redaction tests."""
    return {
        "user": CANARY_USER,
        "project": CANARY_PROJECT,
        "token": CANARY_TOKEN,
        "email": CANARY_EMAIL,
        "password": CANARY_PASSWORD,
        "path": CANARY_PATH,
    }


def assert_no_canaries(value: str | bytes) -> None:
    """Assert that no synthetic canary appears in text or serialized bytes."""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    lowered = text.casefold()
    found = [name for name, canary in canary_values().items() if canary.casefold() in lowered]
    if found:
        raise AssertionError("Synthetic canary value(s) leaked: " + ", ".join(found))


@contextmanager
def temp_data_dir() -> Iterator[Path]:
    """Set ``FLUTTERWAY_DATA_DIR`` to a fresh temporary directory.

    The environment is restored even when the test raises. Do not run code
    that reads this process-wide setting concurrently from another thread.
    """
    previous = os.environ.get("FLUTTERWAY_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="flutterway-test-") as directory:
        path = Path(directory).resolve()
        os.environ["FLUTTERWAY_DATA_DIR"] = str(path)
        try:
            yield path
        finally:
            if previous is None:
                os.environ.pop("FLUTTERWAY_DATA_DIR", None)
            else:
                os.environ["FLUTTERWAY_DATA_DIR"] = previous


def fake_webview_bridge(**api_methods):
    """Return a minimal ``window.pywebview.api``-shaped test double."""
    return SimpleNamespace(api=SimpleNamespace(**api_methods))
