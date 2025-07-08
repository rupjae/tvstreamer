from __future__ import annotations

"""Short-lived websocket helper for historical candles."""

import asyncio
import json
import logging
import random
import string
import time

import anyio
from typing import Any

from .exceptions import MissingDependencyError

websockets: Any = None

from .decoder import decode_candle_frame
from .models import Candle
from .intervals import validate

__all__ = ["get_historic_candles", "TooManyRequestsError"]


class TooManyRequestsError(RuntimeError):
    """Raised when concurrent history sessions exceed the allowed limit."""


# global semaphore controlling concurrent websocket sessions
_websocket_semaphore = asyncio.Semaphore(3)

_WS_ENDPOINT = "wss://data.tradingview.com/socket.io/websocket"


async def _ensure_websockets() -> None:
    try:
        global websockets
        if websockets is None:
            import websockets as _ws  # type: ignore

            websockets = _ws
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise MissingDependencyError(
            "Command requires the 'websockets' extra.  Try: pip install tvstreamer[cli]"
        ) from exc


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


_CACHE_TTL = 60.0
_CACHE_MAXSIZE = 128
_cache: dict[tuple[str, str, int], tuple[float, list[Candle]]] = {}
_cache_lock = asyncio.Lock()


async def _cached_fetch(symbol: str, interval: str, limit: int, timeout: float) -> list[Candle]:
    key = (symbol.upper(), interval, limit)
    now = time.monotonic()
    async with _cache_lock:
        entry = _cache.get(key)
        if entry and now - entry[0] < _CACHE_TTL:
            return entry[1]
    data = await _fetch_history(symbol, interval, limit, timeout)
    async with _cache_lock:
        _cache[key] = (now, data)
        if len(_cache) > _CACHE_MAXSIZE:
            oldest = min(_cache.items(), key=lambda kv: kv[1][0])[0]
            _cache.pop(oldest, None)
    return data


async def get_historic_candles(
    symbol: str, interval: str, limit: int = 500, *, timeout: float = 10.0
) -> list[Candle]:
    """Return recent closed candles.

    Results are cached for 60 seconds keyed by ``(symbol, interval, limit)``.

    Example
    -------
    >>> await get_historic_candles("BINANCE:BTCUSDT", "1m", limit=200)
    """

    await _ensure_websockets()
    res = validate(interval)
    sem = _websocket_semaphore
    if sem.locked():
        raise TooManyRequestsError
    await sem.acquire()

    try:
        return await _cached_fetch(symbol, res, limit, timeout)
    finally:
        sem.release()
