from typer.testing import CliRunner
import typer

from tvstreamer.cli import app


def test_invalid_interval():
    res = CliRunner(mix_stderr=False).invoke(app, ["stream", "-s", "SYM", "--interval", "2m"])
    assert res.exit_code == 2
    assert "Invalid value for '-i' / '--interval'" in res.stderr
