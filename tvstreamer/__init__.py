"""tvstreamer package.

Minimal TradingView WebSocket streaming client plus small CLI helper.

Public API
----------
The library intentionally keeps its surface area tiny.  Only the following
symbols are considered **public**:

* ``TvWSClient`` – synchronous WebSocket client for real-time market data.
* ``configure_logging`` – project-wide logging helper that installs coloured
  console + rotating file handlers matching the *AGENTS* guidelines.
* ``trace`` – decorator that logs function entry/exit at the custom TRACE
  level (numeric value 5).

# Everything else is **internal** and may change without notice.  Import only
# from the names re-exported via the ``__all__`` list below to stay on the safe
# side.
"""

# ---------------------------------------------------------------------------
# tvstreamer public surface – *streaming only*
# ---------------------------------------------------------------------------

# This package has been slimmed down to focus exclusively on real-time
# WebSocket streaming.  All historical-data helpers have been removed.

from .wsclient import TvWSClient

# Public re-exports ---------------------------------------------------

__all__ = [
    "TvWSClient",
    # Logging helpers (re-exported for public consumption)
    "configure_logging",
    "trace",
]

# --------------------------------------------------------------------
# Single-source versioning
# --------------------------------------------------------------------

# --------------------------------------------------------------------
# Single-source versioning – rely on importlib.metadata so the value stays in
# sync with *pyproject.toml*.  Fall back to reading the TOML directly when the
# package is executed from a source checkout (not installed).
# --------------------------------------------------------------------

from importlib import metadata as _metadata


try:
    __version__: str = _metadata.version(__name__)
except _metadata.PackageNotFoundError:  # pragma: no cover – dev environment only
    # Fallback for editable/source checkouts: parse *pyproject.toml* to obtain
    # the version string.  This avoids the need to maintain a duplicate value.
    import pathlib as _pl

    _root = _pl.Path(__file__).resolve().parents[1]
    _toml_path = _root / "pyproject.toml"
    if _toml_path.exists():
        try:
            import tomllib as _tomllib  # Python 3.11+
        except ModuleNotFoundError:  # pragma: no cover – older runtime
            import tomli as _tomllib  # type: ignore

        with _toml_path.open("rb") as _fp:
            _data = _tomllib.load(_fp)
        __version__ = _data["tool"]["poetry"]["version"]
    else:
        __version__ = "0.0.0.dev0"


# Public re-exports ---------------------------------------------------

# --------------------------------------------------------------------
# Logging – auto-configure on first import unless the application already
# set up handlers.  This guarantees that *some* log destination exists so
# users do not encounter a silent experience when they forget to call
# ``configure_logging()`` explicitly.
# --------------------------------------------------------------------

import logging as _logging

# Import public helpers after stdlib is ready so that configure_logging can be
# executed safely.
from .logging_utils import configure_logging as _configure_logging, trace  # noqa: E402  – after sys modules ready

# If the root logger has **no** handlers attached, assume the host application
# has not configured logging yet and apply the project-wide defaults.  We keep
# this idempotent to avoid clobbering custom setups.

if not _logging.getLogger().handlers:
    # We intentionally swallow any exception here – logging mis-configuration
    # must never break application startup.  In the unlikely event of a fatal
    # filesystem error the stdlib *logging* module will still emit to stderr.
    try:
        _configure_logging()
    except Exception:  # noqa: BLE001 – best-effort safety net
        pass

# Re-export public names ------------------------------------------------------

configure_logging = _configure_logging

# Backward-compat import alias so that external code can `import
# tvstreamer.logging` as documented in some guidelines / examples.
import sys as _sys

# Map *tvstreamer.logging* → *tvstreamer.logging_utils* so imports stay stable.
_sys.modules.setdefault(f"{__name__}.logging", _sys.modules[configure_logging.__module__])
