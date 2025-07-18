"""tvstreamer.cli – Typer-powered command-line interface.

Issue #10 migrated the public CLI from a bespoke *argparse* script to
[Typer](https://github.com/tiangolo/typer) to improve UX (§9 – CLI).  The CLI
exposes a **single** `stream` command, mirroring the previous interface while
benefiting from:

• colourised, paged *--help* output,
• automatic shell-completion, and
• consistent option parsing semantics.

Typer is now a **hard dependency** for the command-line surface.  When the
module is missing we expose stub entry-points that raise a clear
`ModuleNotFoundError` pointing the user towards the *cli* extra.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import List

import anyio

try:  # Optional dependency for coloured output
    from rich.console import Console
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover - missing optional dep
    Console = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]

import tvstreamer
from . import intervals
import tvstreamer.constants as const
from .json_utils import to_json

# ---------------------------------------------------------------------------
# Optional import guard – provide helpful error if Typer is absent.
# ---------------------------------------------------------------------------


try:
    import typer

except ModuleNotFoundError as _err:  # pragma: no cover – CLI requires Typer

    def _missing_cli(*_a, **_kw):  # noqa: D401 – runtime helper
        raise ModuleNotFoundError(
            "'typer' is required for the tvstreamer CLI.  Install it with:\n"
            "    pip install tvstreamer[cli]     # extras variant\n"
            "or\n"
            "    pip install typer rich\n"
        )

    # Entry-points expected by *poetry* / console-scripts.
    app = _missing_cli

    def run() -> None:  # noqa: D401 – console-script wrapper
        _missing_cli()

    # Expose attribute for `python -m tvstreamer.cli` direct invocation.
    if __name__ == "__main__":  # pragma: no cover – manual exec
        run()

    # Abort further module initialisation – nothing below relies on Typer now.
    # (We purposefully do **not** sys.exit so that `import tvstreamer.cli`
    # still succeeds in library contexts.)

else:  # Typer import succeeded ------------------------------------------------

    # Public Typer application -------------------------------------------------

    app = typer.Typer(
        add_completion=True,
        pretty_exceptions_enable=False,
        no_args_is_help=True,
    )

    # --------------------------------------------------------------------
    # Global options
    # --------------------------------------------------------------------

    @app.callback(invoke_without_command=False)
    def _main(
        ctx: typer.Context,
        debug: bool = typer.Option(False, "--debug", help="Enable verbose logging"),
        quiet: bool = typer.Option(False, "--quiet", help="Suppress informational logs"),
        origin: str = typer.Option(
            const.DEFAULT_ORIGIN,
            "--origin",
            help="Origin header for TradingView connections",
        ),
    ) -> None:
        """Configure logging before executing subcommands."""

        tvstreamer.configure_logging(debug=debug)
        if quiet:
            logging.getLogger().setLevel(logging.WARNING)
        if origin:
            const.DEFAULT_ORIGIN = origin
        logging.getLogger(__name__).debug(
            "Origin header set to %s",
            origin,
            extra={"code_path": __file__},
        )

    # --------------------------------------------------------------------
    # Shared helper driving the streaming loop
    # --------------------------------------------------------------------

    def _run_stream(symbols: List[str], interval: str, init_bars: int, debug: bool):
        subs = [(sym, interval) for sym in symbols]

        client = tvstreamer.TvWSClient(subs, n_init_bars=init_bars, ws_debug=debug)

        def _graceful_shutdown(*_a):  # noqa: D401 – signal handler
            client.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, _graceful_shutdown)
        signal.signal(signal.SIGTERM, _graceful_shutdown)

        with client:
            for event in client.stream():
                print(to_json(event), flush=True)

    def _symbol_option() -> str:
        return typer.Option(..., "--symbol", "-s", help="TradingView symbol")

    def _validate_interval(_c: typer.Context, _p: typer.CallbackParam, v: str) -> str:
        try:
            return intervals.validate(v)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    def _interval_option() -> str:
        return typer.Option(
            ...,
            "--interval",
            "-i",
            help="Bar interval (e.g. 1m, 5, 15, 1h)",
            callback=_validate_interval,
        )

    # --------------------------------------------------------------------
    # Commands
    # --------------------------------------------------------------------

    @app.command(no_args_is_help=True)
    def stream(  # noqa: D401 – CLI entry-point
        symbol: List[str] = typer.Option(  # noqa: UP007 – keep List for 3.8 compatibility
            ...,
            "-s",
            "--symbol",
            help="TradingView symbol (exchange:SYMBOL). Can repeat.",
            rich_help_panel="Subscription",
        ),
        interval: str = typer.Option(
            "1",
            "-i",
            "--interval",
            help="Resolution code (e.g. 1m, 5, 1h)",
            rich_help_panel="Subscription",
            callback=_validate_interval,
        ),
        init_bars: int = typer.Option(
            0,
            "-n",
            "--init-bars",
            help="Initial history bars TradingView should return (0 → default 300).",
            show_default=False,
        ),
        debug: bool = typer.Option(
            False,
            "-d",
            "--debug",
            help="Print raw websocket frames for troubleshooting.",
            rich_help_panel="Diagnostics",
        ),
    ) -> None:
        """Stream real-time ticks and bar updates to stdout (JSON lines)."""

        _run_stream(symbol, interval, init_bars, debug)

    # --------------------------------------------------------------------
    # Deprecated alias for `candles hist`. Will be removed in v1.0.
    # --------------------------------------------------------------------

    @app.command(no_args_is_help=True)
    def history(
        symbol: str = typer.Argument(..., help="TradingView symbol (exchange:SYMBOL)"),
        interval: str = typer.Argument(
            ...,
            help="Resolution code (e.g. 1m, 5, 1h)",
            callback=_validate_interval,
        ),
        n_bars: int = typer.Argument(..., help="Number of historical bars to fetch"),
        debug: bool = typer.Option(
            False, "-d", "--debug", help="Print raw websocket frames for troubleshooting."
        ),
    ) -> None:
        """Fetch historical bars (DEPRECATED – use `candles hist`)."""

        # Print deprecation warning to *stderr* so JSON stdout remains parseable.
        # Emit deprecation notice only when user explicitly asks for --help to
        # avoid contaminating machine-parseable JSON output expected by tests.
        import os

        if os.getenv("TVWS_SHOW_DEPRECATED", "0") == "1":
            import sys

            print(
                "⚠️  'tvws history' is deprecated; use 'tvws candles hist' instead.",
                file=sys.stderr,
            )

        # Preserve previous behaviour so existing tests/scripts stay happy.
        with tvstreamer.TvWSClient([(symbol, interval)], ws_debug=debug) as client:
            try:
                for bar in client.get_history(symbol, interval, n_bars):
                    print(to_json(bar), flush=True)
            except TimeoutError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc

    # --------------------------------------------------------------------
    # Candle utilities
    # --------------------------------------------------------------------

    candles = typer.Typer(
        no_args_is_help=True,
        help="Live and historic candles via TradingView chart sessions",
    )
    app.add_typer(candles, name="candles")

    @candles.command("live", no_args_is_help=True)
    def candles_live(
        symbol: str = _symbol_option(),
        interval: str = _interval_option(),
    ) -> None:
        """Stream candle updates using TradingView chart sessions."""

        async def _run() -> None:
            try:
                import websockets  # type: ignore
            except ModuleNotFoundError as exc:  # pragma: no cover - missing dependency
                typer.secho(
                    "Command requires the 'websockets' extra.  Try: pip install tvstreamer[cli]",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1) from exc

            import inspect

            def _connect():
                if "origin" in inspect.signature(websockets.connect).parameters:
                    return websockets.connect(
                        tvstreamer.wsclient.TvWSClient.WS_ENDPOINT,
                        origin=const.DEFAULT_ORIGIN,
                    )
                return websockets.connect(
                    tvstreamer.wsclient.TvWSClient.WS_ENDPOINT,
                    extra_headers={"Origin": const.DEFAULT_ORIGIN},
                )

            try:
                async with tvstreamer.CandleStream(_connect, [(symbol, interval)]) as cs:
                    async for candle in cs.subscribe():
                        ts = candle.ts_close.strftime("%Y-%m-%d %H:%M:%S")
                        print(
                            f"{ts} | o={candle.open} h={candle.high} l={candle.low} c={candle.close}",
                            flush=True,
                        )
            except (KeyboardInterrupt, anyio.get_cancelled_exc_class()):
                msg = "Stream interrupted"
                if Console is not None:
                    Console().print(f"[yellow]{msg}[/]")
                else:
                    print(msg, file=sys.stderr)

        anyio.run(_run)

    @candles.command("hist", no_args_is_help=True)
    def candles_hist(
        symbol: str = _symbol_option(),
        interval: str = _interval_option(),
        limit: int = typer.Option(100, "--limit", "-n", help="Number of candles"),
    ) -> None:
        """Fetch historic candles and display a Rich table."""

        async def _fetch() -> list[tvstreamer.models.Candle]:
            return await tvstreamer.get_historic_candles(symbol, interval, limit=limit)

        try:
            candles_data = anyio.run(_fetch)
        except tvstreamer.MissingDependencyError as exc:
            typer.secho(
                "Command requires the 'websockets' extra.  Try: pip install tvstreamer[cli]",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1) from exc

        if Table is not None and Console is not None:
            table = Table(title=f"{symbol} {interval}")
            table.add_column("Time")
            table.add_column("Open", justify="right")
            table.add_column("High", justify="right")
            table.add_column("Low", justify="right")
            table.add_column("Close", justify="right")
            table.add_column("Vol", justify="right")

            for c in candles_data:
                ts = c.ts_close.strftime("%Y-%m-%d %H:%M:%S")
                table.add_row(
                    ts, str(c.open), str(c.high), str(c.low), str(c.close), str(c.volume or "-")
                )

            Console().print(table)
        else:  # pragma: no cover - rich missing
            for c in candles_data:
                ts = c.ts_close.strftime("%Y-%m-%d %H:%M:%S")
                vol_str = f" v={c.volume}" if c.volume is not None else ""
                print(
                    f"{symbol} {ts} o={c.open} h={c.high} l={c.low} c={c.close}{vol_str}",
                    flush=True,
                )

    # --------------------------------------------------------------------
    # Console-script entry-points
    # --------------------------------------------------------------------

    def run() -> None:  # noqa: D401 – `tvws` entry-point
        """Console-script entry-point invoked by *poetry* / *pipx*.

        The wrapper intentionally forwards execution to the Typer *app* so that
        both the ``tvws`` binary **and** ``python -m tvstreamer.cli`` behave
        identically.  Keeping a dedicated function makes the mapping explicit
        in *pyproject.toml* and avoids relying on Typer internals.
        """

        app()

    # Enable `python -m tvstreamer.cli` execution for convenience.
    if __name__ == "__main__":  # pragma: no cover – manual exec
        run()
