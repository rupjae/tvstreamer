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

__version__ = "0.1.0"

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
