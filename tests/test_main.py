"""Test the __main__.py entrypoint for invoking the CLI runner."""

from __future__ import annotations

import tvstreamer.__main__ as main_mod
from tvstreamer.__main__ import main


def test_main_invokes_cli_run(monkeypatch) -> None:
    called: bool = False

    def fake_run(*args, **kwargs) -> None:
        nonlocal called  # type: ignore[name-defined]
        called = True

    monkeypatch.setattr(main_mod, "run", fake_run)
    main()
    assert called, "__main__.main() did not delegate to tvstreamer.cli.run"
