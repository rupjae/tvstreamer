#!/usr/bin/env python
from __future__ import annotations

from tvstreamer import TvWSClient

client = TvWSClient([("BINANCE:BTCUSDT", "1")], n_init_bars=1)
with client:
    for idx, event in enumerate(client.stream(), start=1):
        if getattr(event, "__class__", None).__name__ == "Bar":
            print("PASS: stream alive")
            break
        if idx >= 10:
            raise RuntimeError("timescale_update not received")
