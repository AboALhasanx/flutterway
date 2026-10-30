"""Single source of truth for the FlutterWay app version.

``BUILD_COMMIT`` and ``BUILD_DATE`` are injected at packaging time (for example
via the ``FLUTTERWAY_COMMIT`` / ``FLUTTERWAY_BUILD_DATE`` environment variables
in the PyInstaller spec).  Inside a frozen exe there is no git repository, so
relying on ``git rev-parse`` alone would report ``unknown``.
"""

__version__ = "1.0.0"
BUILD_COMMIT = "unknown"
BUILD_DATE = "unknown"
