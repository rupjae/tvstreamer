from typer.testing import CliRunner
import sys

from tvstreamer.cli import app


def test_missing_websockets(monkeypatch):
    monkeypatch.setitem(sys.modules, "websockets", None)
    import tvstreamer.historic as hist

    monkeypatch.setattr(hist, "websockets", None)
    res = CliRunner().invoke(
        app,
        ["candles", "hist", "--symbol", "SYM", "--interval", "1m", "--limit", "1"],
    )
    assert res.exit_code == 1
    assert "pip install tvstreamer[cli]" in res.stderr
    assert "Traceback" not in res.stderr
