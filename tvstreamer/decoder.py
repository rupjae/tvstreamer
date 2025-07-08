from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

__all__ = ["decode_tick_frame", "decode_candle_frame"]

# Regex for tick frames with last price (lp), volume and update timestamp
_re_tick = re.compile(
    r"qsd.*?\"lp\"\s*:\s*(?P<price>[0-9.]+).*?\"volume\"\s*:\s*(?P<vol>[0-9.]+).*?\"upd\"\s*:\s*(?P<ts>\d+)"
)

# Regex for candle frames (TradingView 'du' updates). Captures OHLCV and optional bar_close_time
_re_candle = re.compile(
    r"\"m\":\"du\".*?\"v\":\[(?P<ts>[0-9.]+),(?P<open>[0-9.]+),(?P<high>[0-9.]+),(?P<low>[0-9.]+),(?P<close>[0-9.]+),(?P<vol>[0-9.]+)\](?:.*?\"bar_close_time\":(?P<bct>\d+))?"
)


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


def decode_candle_frame(raw: str) -> Optional[dict]:
    """Return a dict with candle values from a TradingView ``du`` frame."""
    m = _re_candle.search(raw)
    if not m:
        return None

    ts_val = float(m.group("ts"))
    frame = {
        "v": [
            ts_val,
            float(m.group("open")),
            float(m.group("high")),
            float(m.group("low")),
            float(m.group("close")),
            float(m.group("vol")),
        ]
    }
    bct = m.group("bct")
    if bct:
        frame["lbs"] = {"bar_close_time": int(bct)}
    return frame
