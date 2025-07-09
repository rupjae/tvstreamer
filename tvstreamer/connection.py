"""Async TradingView connection handling tick and candle subscriptions."""

from __future__ import annotations

import json
import logging
import secrets
import string
from typing import Awaitable, Callable, Set, Tuple

import anyio

from .logging_utils import TRACE_LEVEL
from .intervals import validate


SendHook = Callable[[str], Awaitable[None]]


class TradingViewConnection:
    """Minimal async wrapper sending TradingView protocol messages."""

    def __init__(self, sender: SendHook | None = None, token: str | None = None) -> None:
        self._send_hook: SendHook = sender or (lambda _m: anyio.sleep(0))
        self._tick_subs: Set[str] = set()
        self._candle_subs: Set[Tuple[str, str]] = set()
        self._quote_session = self._gen_quote_session()
        self._chart_session = self._gen_chart_session()
        self._started = False
        self._token = token or "unauthorized_user_token"
        self._handshake_lock = anyio.Lock()

    async def __aenter__(self) -> "TradingViewConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        await self.aclose()

    async def _send(self, method: str, params: list) -> None:
        payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
        frame = self._prepend_header(payload)
        await self._send_hook(frame)

    @staticmethod
    def _prepend_header(payload: str) -> str:
        return f"~m~{len(payload.encode())}~m~{payload}"

    @staticmethod
    def _gen_chart_session() -> str:
        alphabet = string.ascii_lowercase
        return "cs_" + "".join(secrets.choice(alphabet) for _ in range(12))

    @staticmethod
    def _gen_quote_session() -> str:
        alphabet = string.ascii_lowercase
        return "qs_" + "".join(secrets.choice(alphabet) for _ in range(12))

    async def _ensure_started(self) -> None:
        async with self._handshake_lock:
            if self._started:
                return
            await self._send("set_auth_token", [self._token])
            await self._send("chart_create_session", [self._chart_session, ""])
            await self._send("quote_create_session", [self._quote_session])
            await self._send(
                "quote_set_fields",
                [self._quote_session, "lp", "volume", "ch"],
            )
            self._started = True

    async def subscribe_ticks(self, symbol: str) -> None:
        await self._ensure_started()
        sym = symbol.upper()
        self._tick_subs.add(sym)
        await self._send("quote_add_symbols", [self._quote_session, sym])
        logging.getLogger(__name__).log(
            TRACE_LEVEL,
            "Subscribed to %s ticks",
            symbol,
            extra={"code_path": __name__},
        )

    async def subscribe_candles(self, symbol: str, interval: str = "1") -> None:
        """Subscribe to periodic bar updates for *symbol* and *interval*.

        *interval* is a TradingView resolution string such as ``"5"`` or ``"D"``.
        Aliases like ``"5m"`` are accepted. Raises ``ValueError`` for unsupported
        resolutions.
        """
        await self._ensure_started()
        res = validate(interval)
        sym = symbol.upper()
        series_id = f"s{secrets.randbelow(9000) + 1000}"
        alias = f"{sym}_{series_id}"
        await self._send("quote_add_symbols", [self._quote_session, sym])
        await self._send(
            "resolve_symbol",
            [self._chart_session, alias, {"symbol": sym, "adjustment": "splits"}],
        )
        await self._send(
            "create_series",
            [self._chart_session, series_id, series_id, alias, res, 1, ""],
        )
        self._candle_subs.add((sym, res))
        logging.getLogger(__name__).log(
            TRACE_LEVEL,
            "Subscribed to %s %s-bar",
            symbol,
            res,
            extra={"code_path": __name__},
        )

    async def aclose(self) -> None:
        if not self._started:
            return
        if self._tick_subs:
            for sym in list(self._tick_subs):
                await self._send("quote_remove_symbols", [self._quote_session, sym])
            self._tick_subs.clear()
        if self._candle_subs:
            self._candle_subs.clear()
