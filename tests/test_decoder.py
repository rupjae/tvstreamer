from datetime import datetime, timezone
import json

import pytest

from tvstreamer.decoder import decode_tick_frame, decode_candle_frame


def test_decode_tick_frame() -> None:
    ts_ms = 1_600_000_000_000
    payload = {
        "m": "qsd",
        "p": ["qs_x", {"n": "SYM", "v": {"lp": 1.23, "volume": 4.56, "upd": ts_ms}}],
    }
    raw = f"~m~{len(json.dumps(payload))}~m~" + json.dumps(payload)
    result = decode_tick_frame(raw)
    assert result is not None
    assert result["price"] == pytest.approx(1.23)
    assert result["volume"] == pytest.approx(4.56)
    assert result["ts"] == datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            '~m~208~m~{"m":"du","p":["cs_x",{"s1":{"s":[{"i":1,"v":[1600000000,1,2,0.5,1.5,100]}],"ns":{},"t":"s1","lbs":{"bar_close_time":1600000060}}}]}',
            {"v": [1600000000, 1.0, 2.0, 0.5, 1.5, 100.0], "lbs": {"bar_close_time": 1600000060}},
        ),
        (
            '~m~207~m~{"m":"du","p":["cs_x",{"s1":{"s":[{"i":1,"v":[1600000000,1,2,0.5,1.5,100]}],"ns":{},"t":"s1"}}]}',
            {"v": [1600000000, 1.0, 2.0, 0.5, 1.5, 100.0]},
        ),
    ],
)
def test_decode_candle_frame(raw: str, expected: dict) -> None:
    assert decode_candle_frame(raw) == expected


def test_decode_candle_frame_non_candle() -> None:
    assert decode_candle_frame('{"m":"qsd"}') is None
