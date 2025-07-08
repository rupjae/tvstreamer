from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import tvstreamer
from tvstreamer.cli import app
from tvstreamer.models import Candle


class DummyStream:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    async def __aenter__(self) -> "DummyStream":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass

    def subscribe(self):
        async def _iter():
            for c in self._candles:
                yield c

        return _iter()


def test_candles_live(monkeypatch):
    from typer.testing import CliRunner
    import types
    import sys

    sample = [
        Candle(
            symbol="BTCUSD",
            ts_open=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ts_close=datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=1,
            interval="5m",
        )
    ]

    class _Factory:
        def __init__(self, *a, **kw):
            pass

        def __call__(self, *a, **kw):
            return DummyStream(sample)

    monkeypatch.setattr(tvstreamer, "CandleStream", lambda *a, **kw: DummyStream(sample))
    monkeypatch.setitem(
        sys.modules, "websockets", types.SimpleNamespace(connect=lambda *a, **k: None)
    )

    res = CliRunner().invoke(app, ["candles", "live", "--symbol", "BTCUSD", "--interval", "5m"])
    assert res.exit_code == 0
    assert "1.5" in res.output


def test_candles_hist(monkeypatch):
    from typer.testing import CliRunner

    sample = [
        Candle(
            symbol="NVDA",
            ts_open=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ts_close=datetime(2020, 1, 1, 1, tzinfo=timezone.utc),
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=1,
            interval="1h",
        )
    ]

    async def fake_get(symbol: str, interval: str, limit: int = 500, *, timeout: float = 10.0):
        return sample

    monkeypatch.setattr(tvstreamer, "get_historic_candles", fake_get)

    res = CliRunner().invoke(
        app,
        ["candles", "hist", "--symbol", "NVDA", "--interval", "1h", "--limit", "1"],
    )
    assert res.exit_code == 0
    assert "NVDA" in res.output
    assert "1.5" in res.output
