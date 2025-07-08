from typer.testing import CliRunner
import tvstreamer
from tvstreamer.cli import app


def test_cli_origin_option(monkeypatch):
    captured = {}

    def fake_create_connection(url, timeout=7, origin=None):
        captured["origin"] = origin

        class DummyWS:
            def send(self, *_a, **_kw):
                pass

            def close(self):
                pass

        return DummyWS()

    monkeypatch.setattr(tvstreamer.wsclient, "create_connection", fake_create_connection)
    monkeypatch.setattr(tvstreamer.wsclient.TvWSClient, "_handshake", lambda self: None)
    monkeypatch.setattr(tvstreamer.wsclient.TvWSClient, "_subscribe_all", lambda self: None)
    monkeypatch.setattr(tvstreamer.wsclient.TvWSClient, "stream", lambda self: iter(()))

    res = CliRunner().invoke(
        app, ["--origin", "https://foo.bar", "stream", "--symbol", "BINANCE:BTCUSDT"]
    )
    assert res.exit_code == 0
    assert captured.get("origin") == "https://foo.bar"
