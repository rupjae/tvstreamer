from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

__all__ = ["Candle"]


@dataclass(frozen=True)
class Candle:
    """OHLCV bar with open/close timestamps."""

    symbol: str
    ts_open: datetime
    ts_close: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: float | None = None
    interval: str = "1m"

    @classmethod
    def from_frame(cls, frame: Mapping[str, Any], *, interval: str = "1m") -> "Candle":
        """Return a :class:`Candle` built from a TradingView frame."""
        data = frame.get("v")
        if not isinstance(data, list) or len(data) < 5:
            raise ValueError("invalid candle frame")

        ts_raw = data[0]
        ts_epoch = ts_raw / 1000 if ts_raw > 1e12 else ts_raw
        ts_open = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

        def to_dec(val: Any) -> Decimal:
            return Decimal(str(val))

        open_ = to_dec(data[1])
        high = to_dec(data[2])
        low = to_dec(data[3])
        close = to_dec(data[4])
        volume = float(data[5]) if len(data) > 5 else None

        lbs = frame.get("lbs")
        close_ts_val = None
        if isinstance(lbs, Mapping):
            close_ts_val = lbs.get("bar_close_time")
        if close_ts_val is not None:
            ts_close = datetime.fromtimestamp(int(close_ts_val), tz=timezone.utc)
        else:
            ts_close = ts_open + cls._interval_to_timedelta(interval)

        symbol = str(frame.get("n") or frame.get("symbol") or "")
        return cls(
            symbol=symbol,
            ts_open=ts_open,
            ts_close=ts_close,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            interval=interval,
        )

    @staticmethod
    def _interval_to_timedelta(interval: str) -> timedelta:
        """Translate interval string to :class:`timedelta`."""
        s = interval.lower()
        if s.isdigit():
            return timedelta(minutes=int(s))
        units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
        for key, attr in units.items():
            if s.endswith(key) and s[:-1].isdigit():
                return timedelta(**{attr: int(s[:-1])})
        raise ValueError(f"unsupported interval: {interval}")
