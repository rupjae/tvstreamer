"""
Typed event models and internal bar buffer for tvstreamer.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, List, Tuple, Union


@dataclass(frozen=True)
class Tick:
    """Single price/volume update (tick) event."""

    ts: datetime
    price: float
    volume: float
    symbol: str


@dataclass(frozen=True)
class Bar:
    """OHLCV bar event (partial or closed candle)."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    interval: str
    closed: bool


BaseEvent = Union[Tick, Bar]


class BarBuffer:
    """
    Ring buffer storing the last N bars per (symbol, interval) pair.

    Append and slicing are O(1) amortized; __getitem__ returns a list of bars.
    """

    def __init__(self, maxlen: int) -> None:
        self._maxlen: int = maxlen
        self._buffers: Dict[Tuple[str, str], Deque[Bar]] = {}

    def append(self, bar: Bar) -> None:
        key = (bar.symbol, bar.interval)
        buf = self._buffers.get(key)
        if buf is None:
            buf = deque(maxlen=self._maxlen)
            self._buffers[key] = buf
        buf.append(bar)

    def __getitem__(self, key: Tuple[str, str]) -> List[Bar]:
        buf = self._buffers.get(key)
        return list(buf) if buf is not None else []
