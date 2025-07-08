from datetime import datetime, timezone

try:
    from anyio.testing import MockClock
except Exception:  # pragma: no cover - older anyio
    from trio.testing import MockClock

import trio
import anyio

from tvstreamer.streamer import CandleStream
from tvstreamer.hub import CandleHub
from tvstreamer.models import Candle


class DummyConn:
    def __init__(self, frames: list[str]):
        self._frames = list(frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._frames:
            raise StopAsyncIteration
        await anyio.sleep(0)
        return self._frames.pop(0)

    async def send(self, msg: str) -> None:
        pass


def test_candlestream_integration():
    frames = [
        '~m~208~m~{"m":"du","p":["cs_x",{"n":"SYM","s1":{"s":[{"i":1,"v":[1600000000,1,2,0.5,1.5,100]}],"ns":{},"t":"s1","lbs":{"bar_close_time":1600000060}}}]}',
        '~m~207~m~{"m":"du","p":["cs_x",{"n":"SYM","s1":{"s":[{"i":1,"v":[1600000000,1,2,0.5,1.5,100]}],"ns":{},"t":"s1"}}]}',
        '~m~207~m~{"m":"du","p":["cs_x",{"n":"SYM","s1":{"s":[{"i":1,"v":[1600000060,1,2,0.5,1.6,100]}],"ns":{},"t":"s1"}}]}',
    ]

    def connect():
        return DummyConn(frames)

    hub = CandleHub(maxsize=10)
    out: list[Candle] = []
    stream_instance: CandleStream | None = None

    async def main() -> None:
        nonlocal stream_instance
        async with CandleStream(connect, [("SYM", "1m")], hub=hub) as stream:
            stream_instance = stream
            it = stream.subscribe()
            for _ in range(3):
                out.append(await it.__anext__())
            await it.aclose()
            stream._tg.cancel_scope.cancel()

    trio.run(main, clock=MockClock())

    assert len(out) == 3
    assert all(isinstance(c, Candle) for c in out)
    assert out[0].symbol == "SYM"
    assert out[0].ts_open.tzinfo is timezone.utc
    assert stream_instance is not None and stream_instance.hub is hub
