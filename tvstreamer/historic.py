from __future__ import annotations

import asyncio
import json
import logging
import random
import string
import time
from functools import lru_cache

import anyio
import websockets

from .decoder import decode_candle_frame
from .models import Candle

__all__ = ["get_historic_candles", "TooManyRequestsError"]


class TooManyRequestsError(RuntimeError):
    """Raised when concurrent history sessions exceed the allowed limit."""


# global semaphore controlling concurrent websocket sessions
_websocket_semaphore = asyncio.Semaphore(3)

_WS_ENDPOINT = "wss://data.tradingview.com/socket.io/websocket"


def _tv_msg(method: str, params: list) -> str:
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~" + payload


async def _fetch_history(symbol: str, interval: str, limit: int, timeout: float) -> list[Candle]:
    symbol_up = symbol.upper()
    chart = "cs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    quote = "qs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    candles: list[Candle] = []
    completed = False
    logger = logging.getLogger(__name__)

    try:
        async with websockets.connect(_WS_ENDPOINT) as ws:
            await ws.send(_tv_msg("set_auth_token", ["unauthorized_user_token"]))
            await ws.send(_tv_msg("chart_create_session", [chart]))
            await ws.send(_tv_msg("quote_create_session", [quote]))
            await ws.send(_tv_msg("quote_set_fields", [quote, "lp", "volume", "ch"]))
            await ws.send(_tv_msg("quote_add_symbols", [quote, symbol_up]))
            await ws.send(
                _tv_msg(
                    "quote_add_series",
                    [quote, symbol_up, interval, {"countback": limit}],
                )
            )

            with anyio.move_on_after(timeout) as cancel:
                async for raw in ws:
                    if "series_completed" in raw or "quote_completed" in raw:
                        completed = True
                        break
                    frame = decode_candle_frame(raw)
                    if not frame or "bar_close_time" not in frame:
                        continue
                    payload = {
                        "symbol": symbol_up,
                        "v": [
                            frame["ts"],
                            frame["o"],
                            frame["h"],
                            frame["l"],
                            frame["c"],
                            frame["v"],
                        ],
                        "lbs": {"bar_close_time": frame["bar_close_time"]},
                    }
                    candles.append(Candle.from_frame(payload, interval=interval))
                    if len(candles) >= limit:
                        completed = True
                        break
            if cancel.cancel_called:
                logger.warning(
                    "Timeout fetching history for %s %s",
                    symbol,
                    interval,
                    extra={"code_path": __file__},
                )
    except Exception as exc:
        logger.warning(
            "Error fetching history for %s %s: %s",
            symbol,
            interval,
            exc,
            extra={"code_path": __file__},
        )
        return []

    if not completed:
        logger.warning(
            "Incomplete history for %s %s", symbol, interval, extra={"code_path": __file__}
        )
    return candles[-limit:]


@lru_cache(maxsize=128)
def _cached_fetch(symbol: str, interval: str, limit: int, timeout: float, ttl: int) -> list[Candle]:
    return asyncio.run(_fetch_history(symbol, interval, limit, timeout))


async def get_historic_candles(
    symbol: str, interval: str, limit: int = 500, *, timeout: float = 10.0
) -> list[Candle]:
    """Return recent closed candles for ``symbol`` and ``interval``.

    Example
    -------
    >>> await get_historic_candles("BINANCE:BTCUSDT", "1m", limit=200)
    """

    sem = _websocket_semaphore
    if sem.locked():
        raise TooManyRequestsError
    await sem.acquire()

    try:
        ttl = int(time.monotonic() // 60)
        return await anyio.to_thread.run_sync(_cached_fetch, symbol, interval, limit, timeout, ttl)
    finally:
        sem.release()
