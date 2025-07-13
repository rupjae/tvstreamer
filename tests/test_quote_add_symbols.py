from __future__ import annotations

import json
import re

import tvstreamer.messages as m


def test_quote_add_symbols_payload() -> None:
    msg = m.quote_add("qs_TEST", "BINANCE:BTCUSDT")
    payload = json.loads(re.sub(r"^~m~\d+~m~", "", msg))
    assert payload["m"] == "quote_add_symbols"
    assert payload["p"] == ["qs_TEST", ["BINANCE:BTCUSDT"]]

