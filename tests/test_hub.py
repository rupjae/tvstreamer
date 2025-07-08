import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest

try:
    from anyio.testing import MockClock
except Exception:  # pragma: no cover - older anyio
    from trio.testing import MockClock

import trio

from tvstreamer.hub import CandleHub
from tvstreamer.models import Candle


def _sample_candle(idx: int) -> Candle:
    now = datetime.now(timezone.utc)
    return Candle(
        symbol="SYM",
        ts_open=now,
        ts_close=now,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("0"),
        close=Decimal(str(idx)),
        volume=1.0,
        interval="1",
    )


def test_candlehub_order() -> None:
    hub = CandleHub(maxsize=10)
    recv1 = hub.subscribe()
    recv2 = hub.subscribe()
    candles = [_sample_candle(i) for i in range(5)]
    out1: list[Candle] = []
    out2: list[Candle] = []

    async def producer() -> None:
        for c in candles:
            await hub.publish(c)

    async def consume(recv, out) -> None:
        for _ in candles:
            out.append(await recv.receive())

    async def main() -> None:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(producer)
            nursery.start_soon(consume, recv1, out1)
            nursery.start_soon(consume, recv2, out2)

    trio.run(main, clock=MockClock())

    assert out1 == candles
    assert out2 == candles


def test_candlehub_stress() -> None:
    hub = CandleHub(maxsize=10000)
    recv1 = hub.subscribe()
    recv2 = hub.subscribe()
    sample = _sample_candle(0)
    n = 10000

    async def consume(recv) -> None:
        for _ in range(n):
            await recv.receive()

    async def main() -> None:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(consume, recv1)
            nursery.start_soon(consume, recv2)
            start = time.perf_counter()
            for _ in range(n):
                await hub.publish(sample)
            elapsed = time.perf_counter() - start
            assert elapsed < 0.1
            nursery.cancel_scope.cancel()

    trio.run(main, clock=MockClock())
