"""Package entrypoint – allows `python -m tvstreamer …`.

We consistently delegate to *tvstreamer.cli.run* so that a single place
implements the command-line interface.  This file purposefully avoids importing
*typer* directly to keep runtime dependencies minimal: all heavy lifting
happens in *tvstreamer.cli*, which already contains a graceful fallback when
*typer* is missing.
"""

from __future__ import annotations

import sys

from .cli import run


def main() -> None:  # noqa: D401 – CLI entrypoint
    """Entry-point executed by ``python -m tvstreamer``.

    This thin wrapper hands control to :pyfunc:`tvstreamer.cli.run` so that all
    command-line concerns remain centralised in *tvstreamer.cli*.

    Args:
        None

    Returns:
        None
    """

    # The *tvstreamer.cli.run* function accepts an optional *argv* list when we
    # operate in *argparse* fallback mode.  When Typer is installed the
    # function takes no arguments – luckily Python allows passing no arguments
    # to a callable that accepts optional ones.  Therefore we simply forward to
    # *run()* unconditionally.
    run()


if __name__ == "__main__":  # pragma: no cover – direct invocation
    main()
