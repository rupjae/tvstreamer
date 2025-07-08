from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from tvstreamer.models import Candle


def test_from_frame_with_bar_close_time() -> None:
    epoch = 1_600_000_000
    frame = {
        "n": "SYM",
        "v": [epoch, 1.0, 2.0, 0.5, 1.5, 100.0],
        "lbs": {"bar_close_time": epoch + 60},
    }
    c = Candle.from_frame(frame, interval="1m")
    assert c.symbol == "SYM"
    assert c.ts_open == datetime.fromtimestamp(epoch, tz=timezone.utc)
    assert c.ts_close == datetime.fromtimestamp(epoch + 60, tz=timezone.utc)
    assert c.open == Decimal("1.0")
    assert c.high == Decimal("2.0")
    assert c.low == Decimal("0.5")
    assert c.close == Decimal("1.5")
    assert c.volume == 100.0
    assert c.interval == "1m"


def test_from_frame_without_bar_close_time() -> None:
    epoch = 1_600_000_000
    frame = {"symbol": "SYM", "v": [epoch, 1, 2, 0, 1, 50]}
    c = Candle.from_frame(frame, interval="5m")
    assert c.ts_close - c.ts_open == timedelta(minutes=5)


def test_from_frame_defaults_interval() -> None:
    epoch = 1_600_000_000
    frame = {"v": [epoch, 1, 1, 1, 1]}
    c = Candle.from_frame(frame)
    assert c.interval == "1m"
    assert c.ts_close - c.ts_open == timedelta(minutes=1)


def test_from_frame_uppercase_interval() -> None:
    epoch = 1_600_000_000
    frame = {"v": [epoch, 1, 1, 1, 1]}
    c = Candle.from_frame(frame, interval="15M")
    assert c.ts_close - c.ts_open == timedelta(minutes=15)


def test_from_frame_error_missing_v() -> None:
    with pytest.raises(ValueError):
        Candle.from_frame({}, interval="1m")


def test_from_frame_error_short_v() -> None:
    with pytest.raises(ValueError):
        Candle.from_frame({"v": [1, 2, 3]}, interval="1m")
