"""CLI smoke tests – ensure the Typer application initialises correctly."""

from __future__ import annotations


def test_help_ok():
    """`tvws --help` should exit 0 and print usage text."""

    from typer.testing import CliRunner  # imported lazily to avoid hard dep in runtime

    from tvstreamer.cli import app

    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in result.output or "USAGE" in result.output


def test_history_help():
    """`tvws history --help` should exit 0 and show history usage."""
    from typer.testing import CliRunner

    from tvstreamer.cli import app

    result = CliRunner().invoke(app, ["history", "--help"])
    assert result.exit_code == 0, result.output
    assert "Fetch historical bars" in result.output
