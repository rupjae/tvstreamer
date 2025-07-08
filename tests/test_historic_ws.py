try:
    from anyio.testing import MockClock
except Exception:  # pragma: no cover - older anyio
    from trio.testing import MockClock as _TrioClock

    def MockClock(*a, **kw):  # type: ignore
        return _TrioClock(*a, autojump_threshold=0, **kw)


import trio
import anyio
import logging
import pytest

import tvstreamer.historic as historic
from tvstreamer.models import Candle


class DummyWS:
    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []

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
        self.sent.append(msg)


def make_frames(n: int) -> list[str]:
    base = 1_600_000_000
    frames = []
    for i in range(n):
        ts = base + i * 60
        payload = {
            "m": "du",
            "p": [
                "cs_x",
                {
                    "s1": {
                        "s": [{"i": 1, "v": [ts, 1, 2, 0.5, 1.5, 100]}],
                        "ns": {},
                        "t": "s1",
                        "lbs": {"bar_close_time": ts + 60},
                    }
                },
            ],
        }
        raw = historic._tv_msg("du", payload["p"])
        frames.append(raw)
    complete = historic._tv_msg("series_completed", ["cs_x", "s1"])
    frames.append(complete)
    return frames


def run_fetch(monkeypatch, limit: int, frames: list[str]):
    ws = DummyWS(frames)

    class DummyConnect:
        def __init__(self, ws):
            self.ws = ws

        def __await__(self):
            async def _wrap():
                return self.ws

            return _wrap().__await__()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            pass

    def connect(*_a, **_kw):
        return DummyConnect(ws)

    monkeypatch.setattr(historic.websockets, "connect", connect)

    async def main():
        return await historic.get_historic_candles("SYM", "1", limit, timeout=1)

    result = trio.run(main, clock=MockClock())
    assert historic._websocket_semaphore._value == 3
    return result


def test_basic_limits(monkeypatch):
    frames = make_frames(4)
    res = run_fetch(monkeypatch, 3, frames.copy())
    assert len(res) == 3
    assert all(isinstance(c, Candle) for c in res)

    res2 = run_fetch(monkeypatch, 4, frames.copy())
    assert len(res2) == 4

    res3 = run_fetch(monkeypatch, 10, frames.copy())
    assert len(res3) == 4


def test_timeout(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)

    class StalledWS(DummyWS):
        async def __anext__(self):
            await anyio.sleep(1)
            raise StopAsyncIteration

    ws = StalledWS([])

    class DummyConnect:
        def __init__(self, ws):
            self.ws = ws

        def __await__(self):
            async def _wrap():
                return self.ws

            return _wrap().__await__()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            pass

    def connect(*_a, **_kw):
        return DummyConnect(ws)

    monkeypatch.setattr(historic.websockets, "connect", connect)

    async def main():
        return await historic.get_historic_candles("SYM", "1", 2, timeout=0.1)

    result = trio.run(main, clock=MockClock())
    assert result == []
    assert any("Timeout" in r.message for r in caplog.records)


def test_cache(monkeypatch):
    frames = make_frames(2)
    ws = DummyWS(frames)
    calls = 0

    class DummyConnect:
        def __init__(self, ws):
            self.ws = ws

        def __await__(self):
            async def _wrap():
                return self.ws

            return _wrap().__await__()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            pass

    def connect(*_a, **_kw):
        nonlocal calls
        calls += 1
        return DummyConnect(ws)

    monkeypatch.setattr(historic.websockets, "connect", connect)
    monkeypatch.setattr(historic.time, "monotonic", lambda: 1000)

    async def main1():
        return await historic.get_historic_candles("SYM", "1", 2, timeout=1)

    async def main2():
        return await historic.get_historic_candles("SYM", "1", 2, timeout=1)

    res1 = trio.run(main1, clock=MockClock())
    res2 = trio.run(main2, clock=MockClock())
    assert calls == 1
    assert res1 == res2


def test_bad_interval(monkeypatch):
    frames = make_frames(1)

    class DummyConnect:
        def __init__(self, ws):
            self.ws = ws

        def __await__(self):
            async def _wrap():
                return self.ws

            return _wrap().__await__()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            pass

    def connect(*_a, **_kw):
        return DummyConnect(DummyWS(frames))

    monkeypatch.setattr(historic.websockets, "connect", connect)

    async def main():
        await historic.get_historic_candles("SYM", "99", 1)

    with pytest.raises(ValueError):
        trio.run(main, clock=MockClock())
