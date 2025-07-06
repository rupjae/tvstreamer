"""tvstreamer.cli – Typer-powered command-line interface.

Currently exposes a single *stream* command that opens a TradingView
WebSocket connection for one or more symbols and prints tick / bar
events as JSON.
"""

from __future__ import annotations

# NOTE: We import *typer* lazily to keep core package usable without CLI deps.
import json
import signal
import sys
from typing import List


try:
    import typer  # type: ignore

# ---------------------------------------------------------------------------
# Optional *typer* dependency
# ---------------------------------------------------------------------------

# If *typer* is unavailable (very likely in minimal execution sandboxes) we fall
# back to an *argparse* powered implementation that exposes the exact same
# *tvws* command-line surface.  This guarantees the binary defined in
# pyproject.toml always works, even when third-party extras cannot be installed.
#
# Keeping the richer Typer experience when the dependency is present costs us
# almost nothing and avoids rewriting existing docs, but in constrained
# environments the lightweight fallback prevents an unconditional runtime
# failure.

except ModuleNotFoundError:  # pragma: no cover – optional runtime dep
    typer = None  # type: ignore – will be handled below


import tvstreamer


# ---------------------------------------------------------------------------
# Shared helpers – agnostic to the frontend (typer / argparse)
# ---------------------------------------------------------------------------


def _run_stream(symbols: List[str], interval: str, init_bars: int, debug: bool):
    """Common streaming routine used by both CLI front-ends."""

    subs = [(sym, interval) for sym in symbols]

    client = tvstreamer.TvWSClient(subs, n_init_bars=init_bars, ws_debug=debug)

    def _graceful_shutdown(*_a):  # noqa: D401 – signal handler
        client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    with client:
        for event in client.stream():
            print(json.dumps(event, default=str), flush=True)


# ---------------------------------------------------------------------------
# Branch depending on *typer* availability
# ---------------------------------------------------------------------------

# *typer*   available → expose the rich CLI exactly as before.
# *typer* • missing   → build a minimal *argparse*-based replacement that keeps
#                       the same public surface (options / behaviour) without
#                       introducing new runtime requirements.

if typer is not None:
    # Typer imported successfully – create the usual application.
    app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
else:
    # Will be defined later using *argparse* – placeholder so type-checkers are
    # satisfied.  At runtime the attribute is replaced with a callable.
    app = None  # type: ignore

# When typer present, implement commands below.

if typer is not None:

    # ------------------------------------------------------------------
    # Typer implementation (unchanged)
    # ------------------------------------------------------------------

    @app.command()
    def stream(
        symbol: List[str] = typer.Option(  # noqa: D401 – CLI params
            ..., "-s", "--symbol", help="TradingView symbol (exchange:SYMBOL). Can repeat.",
        ),
        interval: str = typer.Option("1", "-i", "--interval", help="Resolution code (e.g. 1, 1H, 1D)"),
        init_bars: int = typer.Option(0, "-n", "--init-bars", help="Initial history bars to fetch"),
        debug: bool = typer.Option(False, "-d", "--debug", help="Print raw WS frames"),
    ):
        """Stream real-time ticks and bar updates to stdout in JSON lines format."""

        _run_stream(symbol, interval, init_bars, debug)

    # Entrypoint ------------------------------------------------------

    def run() -> None:  # entrypoint wrapper for poetry console-script
        """Console-script entrypoint for the ``tvws`` command.

        The wrapper exists so *poetry* can reference ``tvstreamer.cli:run`` in
        *pyproject.toml*.  It does nothing more than forward execution to the
        :pydata:`Typer` application configured above.

        Returns:
            None
        """

        app()

else:  # -------------------------------------------------------------

    # ------------------------------------------------------------------
    # *argparse* fallback implementation
    # ------------------------------------------------------------------

    import argparse

    def _build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="tvws",
            description="Stream real-time ticks and bar updates from TradingView (minimal fallback)",
        )
        parser.add_argument(
            "-s",
            "--symbol",
            action="append",
            required=True,
            help="TradingView symbol (exchange:SYMBOL). Can repeat.",
        )
        parser.add_argument(
            "-i",
            "--interval",
            default="1",
            help="Resolution code (e.g. 1, 1H, 1D)",
        )
        parser.add_argument(
            "-n",
            "--init-bars",
            type=int,
            default=0,
            help="Initial history bars to fetch",
        )
        parser.add_argument(
            "-d",
            "--debug",
            action="store_true",
            help="Print raw WS frames",
        )
        return parser

    def run(argv: List[str] | None = None) -> None:  # noqa: D401 – console entrypoint
        """Console-script entrypoint used when *typer* is unavailable.

        Args:
            argv: Optional list of raw command-line tokens.  When *None* (the
                default) :pyclass:`argparse.ArgumentParser` receives
                ``sys.argv[1:]`` as usual.
        """

        parser = _build_parser()
        args = parser.parse_args(argv)

        # We pass symbols as list
        _run_stream(args.symbol, args.interval, args.init_bars, args.debug)

    # Keep a dummy *stream* alias so that importing code does not break.
    def stream(*_a, **_kw):  # type: ignore
        raise ModuleNotFoundError("'typer' is not installed – use 'tvws' command instead.")
