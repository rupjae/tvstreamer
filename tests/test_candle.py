from datetime import datetime, timezone, timedelta
from decimal import Decimal

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
