from __future__ import annotations

"""Custom exceptions used across :mod:`tvstreamer`."""


class MissingDependencyError(ImportError):
    """Raised when a required optional dependency is absent."""
