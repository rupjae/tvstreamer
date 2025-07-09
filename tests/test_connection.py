from __future__ import annotations

import json
import re

import pytest

try:
    from anyio.testing import MockClock
except Exception:  # pragma: no cover - older anyio
    from trio.testing import MockClock

from tvstreamer.connection import TradingViewConnection


@pytest.mark.anyio
async def test_handshake_and_prefix_once() -> None:
    sent: list[str] = []

    async def fake_send(msg: str) -> None:
        sent.append(msg)

    async with TradingViewConnection(sender=fake_send) as conn:
        await conn.subscribe_candles("SYM:TEST", "1")
        await conn.subscribe_ticks("SYM:TEST")
        await conn.subscribe_candles("SYM:TEST2", "1")
        quote_session = conn._quote_session  # type: ignore[attr-defined]

    # first three frames constitute the handshake
    methods = [json.loads(re.split(r"~m~\d+~m~", m)[1])["m"] for m in sent[:3]]
    assert methods == [
        "set_auth_token",
        "quote_create_session",
        "quote_set_fields",
    ]
    # only once
    assert methods.count("set_auth_token") == 1
    # frames are length-prefixed
    assert all(m.startswith("~m~") for m in sent)
    # subsequent subscription uses generated quote session
    payload = json.loads(re.split(r"~m~\d+~m~", sent[3])[1])
    assert payload["m"] in {"quote_add_series", "quote_add_symbols"}
    assert quote_session in payload["p"]


@pytest.mark.anyio
async def test_invalid_interval() -> None:
    async def fake_send(msg: str) -> None:
        pass

    async with TradingViewConnection(sender=fake_send) as conn:
        with pytest.raises(ValueError):
            await conn.subscribe_candles("SYM:TEST", "2")
