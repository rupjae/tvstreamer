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
import signal
import sys
from typing import List

import tvstreamer

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
                print(json.dumps(event, default=str), flush=True)

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
            help="Resolution code (e.g. 1, 1H, 1D).",
            rich_help_panel="Subscription",
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
