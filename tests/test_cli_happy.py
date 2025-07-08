from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from typer.testing import CliRunner

import tvstreamer
from tvstreamer.cli import app
from tvstreamer.events import Tick, Bar


class DummyClient:
    def __init__(self, *a: Any, **kw: Any) -> None:
        pass

    def __enter__(self) -> "DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def stream(self):
        yield Tick(datetime(2020, 1, 1, tzinfo=timezone.utc), 1.0, 1.0, "BTCUSDT")

    def get_history(self, symbol: str, interval: str, n_bars: int):
        return [
            Bar(
                ts=datetime(2020, 1, 1, tzinfo=timezone.utc),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=1,
                symbol=symbol,
                interval=interval,
                closed=True,
            )
        ]


def test_stream_json(monkeypatch):
    monkeypatch.setattr(tvstreamer, "TvWSClient", DummyClient)
    res = CliRunner().invoke(app, ["stream", "-s", "BINANCE:BTCUSDT", "-n", "1"])
    assert res.exit_code == 0
    first = res.stdout.splitlines()[0]
    assert json.loads(first)["symbol"] == "BTCUSDT"


def test_history_json(monkeypatch):
    monkeypatch.setattr(tvstreamer, "TvWSClient", DummyClient)
    res = CliRunner().invoke(app, ["history", "BINANCE:BTCUSDT", "1", "1"])
    assert res.exit_code == 0
    first = res.stdout.splitlines()[0]
    assert json.loads(first)["symbol"] == "BINANCE:BTCUSDT"
