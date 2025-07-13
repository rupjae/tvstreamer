from __future__ import annotations

"""TradingView message helpers."""

import json
from typing import Any

__all__ = ["quote_add", "tv_msg"]


def tv_msg(method: str, params: list[Any]) -> str:
    """Return a raw TradingView WebSocket frame."""
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~" + payload


def quote_add(quote_session: str, symbol: str) -> str:
    """Return a quote_add_symbols frame."""
    return tv_msg("quote_add_symbols", [quote_session, [symbol]])
