"""Async candle streaming via :class:`CandleHub`."""

from __future__ import annotations

import anyio
import logging
from typing import AsyncContextManager, AsyncIterator, Callable, Iterable
import random

from .connection import TradingViewConnection
from .decoder import decode_candle_frame
from .intervals import validate
from .hub import CandleHub
from .models import Candle
from .settings import RECONNECT_MAX_DELAY
from .logging_utils import TRACE_LEVEL

__all__ = ["CandleStream"]

logger = logging.getLogger(__name__)


class CandleStream:
    """Stream candle updates and fan-out via :class:`CandleHub`."""

    def __init__(
        self,
        connect: Callable[[], AsyncContextManager],
        pairs: Iterable[tuple[str, str]],
        *,
        hub: CandleHub | None = None,
        reconnect_delay: float = 1.0,
    ) -> None:
        self._connect = connect
        self._pairs = list(pairs)
        self._interval_map = {sym.upper(): validate(interval) for sym, interval in self._pairs}
        self._hub = hub or CandleHub()
        self._delay = reconnect_delay
        self._tg: anyio.abc.TaskGroup | None = None

    @property
    def hub(self) -> CandleHub:
        """Broadcast hub for published candles."""

        return self._hub

    async def __aenter__(self) -> "CandleStream":
        self._tg = anyio.create_task_group()
        await self._tg.__aenter__()
        self._tg.start_soon(self._run)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self._tg is not None
        self._tg.cancel_scope.cancel()
        await self._tg.__aexit__(exc_type, exc, tb)
        await self._hub.aclose()

    async def _run(self) -> None:
        assert self._tg is not None
        attempt = 0
        while True:
            try:
                logger.log(
                    TRACE_LEVEL,
                    "connect candle stream",
                    extra={"code_path": f"{__name__}.CandleStream"},
                )
                async with self._connect() as ws:
                    conn = TradingViewConnection(sender=ws.send)  # type: ignore[attr-defined]
                    for sym, interval in self._pairs:
                        await conn.subscribe_candles(sym, interval)
                    attempt = 0
                    async for raw in ws:
                        frame = decode_candle_frame(raw)
                        if not frame:
                            continue
                        sym = frame["sym"].upper()
                        interval = self._interval_map.get(sym)
                        if interval is None:
                            continue
                        payload = {
                            "n": sym,
                            "v": [
                                frame["ts"],
                                frame["o"],
                                frame["h"],
                                frame["l"],
                                frame["c"],
                                frame["v"],
                            ],
                        }
                        bct = frame.get("bar_close_time")
                        if bct is not None:
                            payload["lbs"] = {"bar_close_time": bct}
                        candle = Candle.from_frame(payload, interval=interval)
                        await self._hub.publish(candle)
            except anyio.get_cancelled_exc_class():
                break
            except Exception:  # pragma: no cover - reconnect branch
                attempt += 1
                logger.exception("candle stream error", extra={"code_path": __name__})
                delay = min(self._delay * (2**attempt), RECONNECT_MAX_DELAY)
                delay *= 0.8 + random.random() * 0.4
                await anyio.sleep(delay)

    def subscribe(self) -> AsyncIterator[Candle]:
        """Return an async iterator of :class:`Candle` events."""

        recv = self._hub.subscribe()

        async def _iterator() -> AsyncIterator[Candle]:
            try:
                while True:
                    yield await recv.receive()
            finally:
                await recv.aclose()

        return _iterator()
