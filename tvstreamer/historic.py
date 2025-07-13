from __future__ import annotations

"""Short-lived websocket helper for historical candles."""

import asyncio
import json
import logging
import random
import re
import string
import time

import anyio
from typing import Any

from .exceptions import MissingDependencyError

websockets: Any = None

from .decoder import decode_candle_frame
from .models import Candle
from .intervals import validate
from .auth import discover_tv_cookies, AuthCookies

__all__ = ["get_historic_candles", "TooManyRequestsError"]


class TooManyRequestsError(RuntimeError):
    """Raised when concurrent history sessions exceed the allowed limit."""


# global semaphore controlling concurrent websocket sessions
_websocket_semaphore = asyncio.Semaphore(3)

# See comment in tvstreamer.wsclient.TvWSClient – switch to *prodata* cluster
# which currently allows direct WebSocket upgrades without Cloudflare cookies.
_WS_ENDPOINT = "wss://prodata.tradingview.com/socket.io/websocket"


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
    # ------------------------------------------------------------------
    # Discover TradingView cookies (env → Safari macOS) so we can authenticate
    # against the *prodata* cluster.  Anonymous requests still work for many
    # symbols, but certain exchanges and low intervals require a valid
    # session.  We silently fall back to anonymous mode when no cookies are
    # available so CLI users without a browser login are not blocked.
    # ------------------------------------------------------------------

    cookies: AuthCookies = discover_tv_cookies()
    chart = "cs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))
    candles: list[Candle] = []
    completed = False
    seen_ts: set[int] = set()
    logger = logging.getLogger(__name__)

    try:
        # Some TradingView edge nodes reject WebSocket upgrades that do not
        # carry an *Origin* header matching the host.  Pass the header using
        # the modern ``origin=…`` parameter when available, falling back to
        # *extra_headers* for older ``websockets`` versions (<10).

        import inspect

        origin_hdr = "https://prodata.tradingview.com"

        # Assemble extra HTTP headers
        extra_headers: dict[str, str] = {"Origin": origin_hdr}
        if cookies.sessionid:
            extra_headers["Cookie"] = f"sessionid={cookies.sessionid}"

        if "origin" in inspect.signature(websockets.connect).parameters:
            connect_ctx = websockets.connect(
                _WS_ENDPOINT,
                origin=origin_hdr,
                extra_headers=extra_headers,
            )
        else:  # pragma: no cover – legacy websockets (<10)
            connect_ctx = websockets.connect(_WS_ENDPOINT, extra_headers=extra_headers)

        async with connect_ctx as ws:
            # ------------------------------------------------------------------
            # Minimal message sequence to request historic bars
            # ------------------------------------------------------------------
            auth_tok = cookies.auth_token or "unauthorized_user_token"
            await ws.send(_tv_msg("set_auth_token", [auth_tok]))

            # 1) Create a chart session (bar data lives here)
            await ws.send(_tv_msg("chart_create_session", [chart]))

            # 2) Resolve the TradingView symbol to an internal descriptor. We use
            #    a short alias so subsequent messages remain compact.
            alias = "sds_sym_0"
            descriptor = f'={{"symbol":"{symbol_up}","adjustment":"splits"}}'
            await ws.send(_tv_msg("resolve_symbol", [chart, alias, descriptor]))

            # 3) Request *limit* historical bars with create_series. The 6-th
            #    parameter (history) instructs the server to send a snapshot of
            #    the last *limit* completed candles.
            await ws.send(
                _tv_msg(
                    "create_series",
                    [chart, "sds_1", "s0", alias, interval, limit, ""],
                )
            )

            with anyio.move_on_after(timeout) as cancel:
                # pre-compiled regex for footer splitting
                _split_re = re.compile(r"~m~\d+~m~")

                async for raw in ws:
                    # ------------------------------------------------------------------
                    # Heartbeat handling – echo same payload back (~h~<id>)
                    # ------------------------------------------------------------------
                    if "~h~" in raw:
                        for part in _split_re.split(raw):
                            if part.startswith("~h~"):
                                pong = f"~m~{len(part)}~m~{part}"
                                await ws.send(pong)

                    # ------------------------------------------------------------------
                    # Try fast-path regex decoder for incremental 'du' updates
                    # ------------------------------------------------------------------
                    frame = decode_candle_frame(raw)
                    if frame and "bar_close_time" in frame:
                        ts_int = int(frame["ts"])
                        if ts_int not in seen_ts:
                            seen_ts.add(ts_int)
                            payload = {
                                "symbol": symbol_up,
                                "n": symbol_up,
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

                    # ------------------------------------------------------------------
                    # Scan JSON chunks for series_loading / timescale_update snapshots
                    # ------------------------------------------------------------------
                    for part in _split_re.split(raw):
                        if not part or part.startswith("~h~"):
                            continue
                        try:
                            msg = json.loads(part)
                        except json.JSONDecodeError:
                            continue

                        mtype = msg.get("m")
                        if mtype not in ("series_loading", "timescale_update"):
                            continue

                        try:
                            series_obj = msg["p"][1]["sds_1"]
                            frames = series_obj.get("s", [])
                        except (IndexError, KeyError, TypeError):  # pragma: no cover
                            continue

                        for f in frames:
                            v_arr = f.get("v")
                            if not v_arr:
                                continue
                            ts_int = int(v_arr[0])
                            if ts_int in seen_ts:
                                continue
                            seen_ts.add(ts_int)
                            # Ensure symbol present for from_frame()
                            f.setdefault("n", symbol_up)
                            candles.append(Candle.from_frame(f, interval=interval))

                        if len(candles) >= limit:
                            completed = True
                            break

                    if completed:
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
