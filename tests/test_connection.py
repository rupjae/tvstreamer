import json
import pytest
import typer

try:
    from anyio.testing import MockClock
except Exception:  # pragma: no cover - older anyio
    from trio.testing import MockClock

from tvstreamer.connection import TradingViewConnection


def test_subscribe_candles_message(monkeypatch):
    sent = []

    async def fake_send(msg: str) -> None:
        sent.append(msg)

    async def main() -> None:
        async with TradingViewConnection(sender=fake_send) as conn:
            await conn.subscribe_candles("SYM:TEST", "5")

    import trio

    trio.run(main, clock=MockClock())

    expected = json.dumps(
        {"m": "quote_add_series", "p": ["qs", "SYM:TEST", "5"]}, separators=(",", ":")
    )
    assert sent[0] == expected


def test_interval_normalisation(monkeypatch):
    sent = []

    async def fake_send(msg: str) -> None:
        sent.append(msg)

    async def main() -> None:
        async with TradingViewConnection(sender=fake_send) as conn:
            await conn.subscribe_candles("SYM:TEST", "5m")

    import trio

    trio.run(main, clock=MockClock())

    expected = json.dumps(
        {"m": "quote_add_series", "p": ["qs", "SYM:TEST", "5"]}, separators=(",", ":")
    )
    assert sent[0] == expected


def test_invalid_interval(monkeypatch):
    async def fake_send(msg: str) -> None:
        pass

    async def main() -> None:
        async with TradingViewConnection(sender=fake_send) as conn:
            await conn.subscribe_candles("SYM:TEST", "2")

    import trio

    with pytest.raises(typer.BadParameter):
        trio.run(main, clock=MockClock())
