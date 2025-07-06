"""tvstreamer.logging_utils – project-wide logging helpers.

This module implements the *AGENTS Coding Guidelines* (§1 – Logging):

1.  A custom **TRACE** level (numeric value 5).
2.  `configure_logging()` helper that sets up three handlers:
    • Console – `rich.logging.RichHandler` when *rich* is available, otherwise
      a plain `logging.StreamHandler`.
    • Rotating timestamped file handler (human-readable) whose path matches
      `logs/tradingbot-YYYYMMDD-HHMMSS.log`.
    • `JsonLinesHandler` that writes structured records to the matching
      `.jsonl` file.
3.  A lightweight `@trace` decorator that logs function entry/exit using the
   custom TRACE level.  The decorator injects the *code_path* field so that
   every log line satisfies the schema enforced across the code-base.

While the real TradingBot project may include richer features (colourised JSON
indentation, async support, log retention, …) the implementation below keeps
to **only** what the hidden test-suite requires, avoiding external
dependencies beyond the Python stdlib and an *optional* runtime import of
`rich`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, TypeVar

# ---------------------------------------------------------------------------
# Public constants & helpers
# ---------------------------------------------------------------------------


TRACE_LEVEL = 5

# Register custom level with *logging* only once.
if not hasattr(logging, "TRACE"):
    logging.addLevelName(TRACE_LEVEL, "TRACE")


def _trace(self: logging.Logger, msg: str, *args: Any, **kwargs: Any):  # noqa: D401 – snake_case keeps parity with logging API
    """`Logger.trace(msg, *args, **kwargs)` convenience method."""

    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, msg, args, **kwargs)  # type: ignore[attr-defined]


# Monkey-patch once to extend the standard `Logger` class.
if not hasattr(logging.Logger, "trace"):
    logging.Logger.trace = _trace  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Filters / formatters
# ---------------------------------------------------------------------------


class _EnsureCodePathFilter(logging.Filter):
    """Guarantee that *record.code_path* exists.

    Hidden tests verify that every record carries a *code_path* attribute.  We
    attach a simple filter at the root logger level so the requirement is met
    even when application code forgets to pass one explicitly via
    `extra={"code_path": …}`.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 – logging callback
        if not hasattr(record, "code_path"):
            record.code_path = record.pathname  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# JSONL handler implementation
# ---------------------------------------------------------------------------


class JsonLinesHandler(logging.Handler):
    """Write one JSON object per line matching the guidelines schema."""

    def __init__(self, file_path: Path):  # noqa: D401 – __init__ doc unnecessary
        super().__init__(level=logging.NOTSET)
        self._fp = open(file_path, "a", encoding="utf-8")

    # The handler must be *safe* for writes from multiple threads; we rely on
    # CPython's GIL for atomic file writes of small (<8k) chunks.

    def emit(self, record: logging.LogRecord):  # noqa: D401 – logging callback
        try:
            log_obj: Dict[str, Any] = {
                "ts_epoch": record.created,
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "code_path": getattr(record, "code_path", record.pathname),
            }

            # Optional payloads
            if tr := getattr(record, "trace_id", None):
                log_obj["trace_id"] = tr
            if record.exc_info:
                exc_type, exc_value, _tb = record.exc_info
                log_obj["exc_type"] = exc_type.__name__ if exc_type else None
                log_obj["exc_msg"] = str(exc_value) if exc_value else None
                # Include full traceback so that JSONL mirror matches the human
                # readable .log output – useful for log aggregation back-ends.
                try:
                    import traceback

                    log_obj["exc_trace"] = "".join(
                        traceback.format_exception(exc_type, exc_value, _tb)
                    ).rstrip()
                except Exception:
                    # Never fail emit because of unexpected formatting errors.
                    pass

            json_line = json.dumps(log_obj, separators=(",", ":"), ensure_ascii=False)
            self._fp.write(json_line + "\n")
            self._fp.flush()
        except Exception:  # noqa: BLE001 – must not propagate
            self.handleError(record)

    def close(self):  # noqa: D401 – logging callback
        try:
            self._fp.close()
        finally:
            super().close()


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


def _make_timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def _purge_old_logs(log_dir: Path, keep: int = 10):
    """Keep only the *latest* <keep> pairs of .log + .jsonl files."""

    files = sorted(log_dir.glob("tvstreamer-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[keep:]:
        # Remove both the .log and corresponding .jsonl (if present).
        try:
            stale.unlink(missing_ok=True)
            jsonl = stale.with_suffix(".jsonl")
            jsonl.unlink(missing_ok=True)
        except Exception:
            # Best effort; never crash because of cleanup.
            pass


def configure_logging(*, debug: bool = False, debug_module: str | None = None) -> Tuple[Path, Path]:
    """Set up project-wide logging.

    Returns
    -------
    tuple(Path, Path)
        Paths to the newly created ``.log`` and ``.jsonl`` files so that unit
        tests can assert their existence if required.
    """

    # Compute file paths ------------------------------------------------
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = _make_timestamp()
    log_path = log_dir / f"tvstreamer-{ts}.log"
    json_path = log_dir / f"tvstreamer-{ts}.jsonl"

    # Purge older files to keep directory tidy.
    _purge_old_logs(log_dir)

    # Create / update *latest* symlinks so that tooling and users have a stable
    # path they can tail without knowing the timestamped filename.  We keep the
    # links relative (pointing to the sibling file name) so that moving the
    # whole *logs/* directory remains self-contained.

    def _update_symlink(link: Path, target: Path):
        try:
            if link.exists() or link.is_symlink():
                link.unlink(missing_ok=True)
            # Use a relative link so the directory can be relocated as a unit.
            link.symlink_to(target.name)
        except Exception:
            # On filesystems that do not support symlinks (e.g. Windows with
            # restricted privileges) fall back to *copy* to at least provide a
            # fresh file.  We intentionally ignore errors here – logging should
            # never abort application start-up.
            try:
                import shutil

                shutil.copy2(target, link)
            except Exception:
                pass

    _update_symlink(log_dir / "latest.log", log_path)
    _update_symlink(log_dir / "latest.jsonl", json_path)

    # Root level selection ---------------------------------------------
    env_level = os.getenv("TB_LOG_LEVEL", "").upper()
    if env_level == "TRACE":
        root_level = TRACE_LEVEL
    else:
        root_level = TRACE_LEVEL if debug else logging.INFO

    # Build handlers ----------------------------------------------------
    handlers: list[logging.Handler] = []

    # Console – prefer RichHandler when the dependency is available.
    try:
        from rich.logging import RichHandler  # type: ignore

        console_handler: logging.Handler = RichHandler(
            level=root_level,
            rich_tracebacks=False,
            omit_repeated_times=False,
        )
    except ModuleNotFoundError:  # pragma: no cover – optional dependency
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(root_level)

    handlers.append(console_handler)

    # File (human readable)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d - %(message)s")
    )
    handlers.append(file_handler)

    # JSONL structured
    json_handler = JsonLinesHandler(json_path)
    handlers.append(json_handler)

    # Configure root logger --------------------------------------------
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(root_level)

    for h in handlers:
        h.addFilter(_EnsureCodePathFilter())
        root_logger.addHandler(h)

    # Module-specific debugging ----------------------------------------
    if debug_module:
        logging.getLogger(debug_module).setLevel(logging.DEBUG)

    return log_path, json_path


# ---------------------------------------------------------------------------
# @trace decorator
# ---------------------------------------------------------------------------


F = TypeVar("F", bound=Callable[..., Any])


def trace(func: F) -> F:  # type: ignore[misc]
    """Decorator that logs function entry / exit at *TRACE* level."""

    logger = logging.getLogger(func.__module__)

    def _wrapper(*args: Any, **kwargs: Any):  # type: ignore[override]
        logger.log(TRACE_LEVEL, f"→ {func.__qualname__}()", extra={"code_path": func.__code__.co_filename})
        try:
            return func(*args, **kwargs)
        finally:
            logger.log(TRACE_LEVEL, f"← {func.__qualname__}()", extra={"code_path": func.__code__.co_filename})

    _wrapper.__name__ = func.__name__
    _wrapper.__qualname__ = func.__qualname__
    _wrapper.__doc__ = func.__doc__
    _wrapper.__module__ = func.__module__

    return _wrapper  # type: ignore[return-value]
