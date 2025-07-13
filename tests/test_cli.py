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


def test_candles_help():
    """`tvws candles --help` should exit 0 and list candle subcommands."""
    from typer.testing import CliRunner

    from tvstreamer.cli import app

    result = CliRunner().invoke(app, ["candles", "--help"])
    assert result.exit_code == 0, result.output
    assert "live" in result.output and "hist" in result.output


def test_candles_hist_help():
    """`tvws candles hist --help` should exit 0 and show limit option."""
    from typer.testing import CliRunner

    from tvstreamer.cli import app

    result = CliRunner().invoke(app, ["candles", "hist", "--help"])
    assert result.exit_code == 0, result.output
    assert "--limit" in result.output or "-n" in result.output
