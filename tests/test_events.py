"""Unit tests for typed event models and bar buffer."""

from datetime import datetime, timezone
import json

import pytest

from tvstreamer.events import BarBuffer, Tick, Bar
from tvstreamer.wsclient import TvWSClient, Subscription


def test_barbuffer_maxlen_and_slicing() -> None:
    maxlen = 3
    buffer = BarBuffer(maxlen)
    ts = datetime(2021, 1, 1, tzinfo=timezone.utc)
    # append 5 bars, only last 3 retained
    for i in range(5):
        bar = Bar(
            ts=ts,
            open=i,
            high=i + 0.5,
            low=i - 0.5,
            close=i + 1,
            volume=float(i),
            symbol="SYM",
            interval="1",
            closed=bool(i % 2),
        )
        buffer.append(bar)
    bars = buffer["SYM", "1"]
    assert len(bars) == maxlen
    # slicing on returned list
    assert [b.open for b in bars[-2:]] == [3, 4]


def test_client_stream_returns_typed_events() -> None:
    client = TvWSClient([], n_init_bars=1)
    q = client._q
    # simulate tick payload
    ts_ms = 1_600_000_000_000
    payload = json.dumps({"m": "qsd", "p": []})
    payload = payload[:-1] + f', "lp":1.23, "volume":4.56, "upd":{ts_ms}}}'
    client._handle_payload(payload)
    ev = next(client.stream())
    assert isinstance(ev, Tick)
    assert ev.price == pytest.approx(1.23)
    assert ev.volume == pytest.approx(4.56)
    assert ev.ts.tzinfo is timezone.utc

    # simulate bar payload, register subscription mapping
    sub = Subscription("SYM:TEST", "5")
    series_id = "sX123"
    client._series[series_id] = sub
    epoch = 1_600_000_000
    bar_list = [[epoch, 1, 2, 3, 4, 5, True]]
    payload = json.dumps({"m": "du", "p": [series_id, bar_list]})
    client._handle_payload(payload)
    ev2 = next(client.stream())
    assert isinstance(ev2, Bar)
    assert ev2.open == 1
    assert ev2.high == 2
    assert ev2.low == 3
    assert ev2.close == 4
    assert ev2.volume == 5
    assert ev2.closed is True
    assert ev2.symbol == sub.symbol
    assert ev2.interval == sub.interval

    # buffer should retain the bar
    bars = client._buffer[sub.symbol, sub.interval]
    assert bars and bars[-1] == ev2
