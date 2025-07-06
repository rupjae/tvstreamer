"""tvstreamer package.

High-level streaming facade, WebSocket client, and logging helpers.

Public API
----------
The library intentionally keeps its surface area minimal. The following
symbols are the supported public interface:

* ``TvWSClient``      – synchronous WebSocket client for real-time market data.
* ``StreamRouter``    – high-level router for iterator- and callback-based
  streaming of Tick and Bar events with filtering and back-pressure.
* ``configure_logging``– project-wide logging helper that installs coloured
  console + rotating file handlers matching the *AGENTS* guidelines.
* ``trace``           – decorator that logs function entry/exit at the custom
  TRACE level (numeric value 5).

# Anything else is internal and may change without notice. Import only from
# the names re-exported in ``__all__`` below to stay compatible.
"""

# ---------------------------------------------------------------------------
# tvstreamer public surface – *streaming only*
# ---------------------------------------------------------------------------

# This package has been slimmed down to focus exclusively on real-time
# WebSocket streaming.  All historical-data helpers have been removed.

# Import standard library dependencies first (PEP8 / Ruff I001 compliant)
import logging as _logging
from importlib import metadata as _metadata

# ---------------------------------------------------------------------------
# First-party imports
# ---------------------------------------------------------------------------

# Import logging helpers *before* TvWSClient so that downstream code that
# pulls in tvstreamer.TvWSClient receives a ready-to-use logging setup.

from .logging_utils import (
    configure_logging as _configure_logging,
    trace,
)  # noqa: E402 – deferred until stdlib ready

# Public streaming client
from .wsclient import TvWSClient
from .streaming import StreamRouter

# Public re-exports -----------------------------------------------------------

__all__ = [
    "TvWSClient",
    "StreamRouter",
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

# Single-source versioning ----------------------------------------------------

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

# Import public helpers after stdlib is ready so that configure_logging can be
# executed safely.
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
