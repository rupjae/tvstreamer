from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, TypedDict

__all__ = ["decode_tick_frame", "decode_candle_frame"]

# Regex for tick frames with last price (lp), volume and update timestamp
_re_tick = re.compile(
    r"qsd.*?\"lp\"\s*:\s*(?P<price>[0-9.]+).*?\"volume\"\s*:\s*(?P<vol>[0-9.]+).*?\"upd\"\s*:\s*(?P<ts>\d+)"
)

# Regex for candle frames (TradingView 'du' updates). Captures OHLCV and optional bar_close_time
_CANDLE_RE = re.compile(
    r"\"m\":\"du\".*?\"v\":\[(?P<ts>[0-9.]+),(?P<open>[0-9.]+),(?P<high>[0-9.]+),(?P<low>[0-9.]+),(?P<close>[0-9.]+),(?P<vol>[0-9.]+)\](?:.*?\"bar_close_time\":(?P<bct>\d+))?"
)


class CandleFrame(TypedDict, total=False):
    ts: float
    o: float
    h: float
    l: float  # noqa: E741 - field mirrors TradingView key
    c: float
    v: float
    bar_close_time: int


def decode_tick_frame(raw: str) -> Optional[dict]:
    """Return a simple dict from a TradingView tick frame or ``None``."""
    m = _re_tick.search(raw)
    if not m:
        return None
    ts = datetime.fromtimestamp(int(m.group("ts")) / 1000, tz=timezone.utc)
    return {
        "ts": ts,
        "price": float(m.group("price")),
        "volume": float(m.group("vol")),
    }


def decode_candle_frame(raw: str) -> Optional[CandleFrame]:
    """Return OHLCV values from a TradingView ``du`` frame.

    Example
    -------
    >>> decode_candle_frame('~m~207~m~{"m":"du","p":["s",{"s1":{"s":[{"i":1,"v":[1,2,3,4,5,6]}],"t":"s1"}}]}')
    {'ts': 1.0, 'o': 2.0, 'h': 3.0, 'l': 4.0, 'c': 5.0, 'v': 6.0}
    """
    m = _CANDLE_RE.search(raw)
    if not m:
        return None

    frame: CandleFrame = {
        "ts": float(m.group("ts")),
        "o": float(m.group("open")),
        "h": float(m.group("high")),
        "l": float(m.group("low")),
        "c": float(m.group("close")),
        "v": float(m.group("vol")),
    }
    bct = m.group("bct")
    if bct:
        frame["bar_close_time"] = int(bct)
    return frame
