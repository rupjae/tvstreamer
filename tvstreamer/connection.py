"""Async TradingView connection handling tick and candle subscriptions."""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Set, Tuple

import anyio

from .logging_utils import TRACE_LEVEL
from .intervals import validate


SendHook = Callable[[str], Awaitable[None]]


class TradingViewConnection:
    """Minimal async wrapper sending TradingView protocol messages."""

    def __init__(self, sender: SendHook | None = None) -> None:
        self._send_hook: SendHook = sender or (lambda _m: anyio.sleep(0))
        self._tick_subs: Set[str] = set()
        self._candle_subs: Set[Tuple[str, str]] = set()

    async def __aenter__(self) -> "TradingViewConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        await self.aclose()

    async def _send(self, method: str, params: list) -> None:
        msg = json.dumps({"m": method, "p": params}, separators=(",", ":"))
        await self._send_hook(msg)

    async def subscribe_ticks(self, symbol: str) -> None:
        sym = symbol.upper()
        self._tick_subs.add(sym)
        await self._send("quote_add_symbols", ["qs", sym])
        logging.getLogger(__name__).log(
            TRACE_LEVEL,
            "Subscribed to %s ticks",
            symbol,
            extra={"code_path": __file__},
        )

    async def subscribe_candles(self, symbol: str, interval: str = "1") -> None:
        """Subscribe to periodic bar updates for *symbol* and *interval*.

        *interval* is a TradingView resolution string such as ``"5"`` or ``"D"``.
        Aliases like ``"5m"`` are accepted. Raises ``ValueError`` for unsupported
        resolutions.
        """
        res = validate(interval)
        sym = symbol.upper()
        self._candle_subs.add((sym, res))
        await self._send("quote_add_series", ["qs", sym, res])
        logging.getLogger(__name__).log(
            TRACE_LEVEL,
            "Subscribed to %s %s-bar",
            symbol,
            res,
            extra={"code_path": __file__},
        )

    async def aclose(self) -> None:
        if self._tick_subs:
            for sym in list(self._tick_subs):
                await self._send("quote_remove_symbols", ["qs", sym])
            self._tick_subs.clear()
        if self._candle_subs:
            for sym, interval in list(self._candle_subs):
                await self._send("quote_remove_series", ["qs", sym, interval])
            self._candle_subs.clear()
