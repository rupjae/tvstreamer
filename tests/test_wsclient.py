"""Unit tests for TvWSClient internal helpers and payload handling."""

from __future__ import annotations

import json
import queue
import re
from datetime import datetime, timezone

import pytest

from tvstreamer.wsclient import Subscription, TvWSClient
from tvstreamer.events import Tick, Bar


def test_construct_and_prepend_header() -> None:
    client = TvWSClient([], n_init_bars=1)
    payload = client._construct_msg("foo", ["a", 1])
    expected = json.dumps({"m": "foo", "p": ["a", 1]}, separators=(",", ":"))
    assert payload == expected
    wrapped = client._prepend_header(payload)
    match = re.match(r"~m~(\d+)~m~(.+)", wrapped)
    assert match, "Header format incorrect"
    assert int(match.group(1)) == len(payload)
    assert match.group(2) == payload


def test_session_generators_length_and_prefix() -> None:
    chart = TvWSClient._gen_chart_session()
    assert chart.startswith("cs_") and len(chart) == 3 + 12
    quote = TvWSClient._gen_quote_session()
    assert quote.startswith("qs_") and len(quote) == 3 + 12


def test_handshake_sends_expected_messages() -> None:
    client = TvWSClient([("SYM:TEST", "1")], n_init_bars=2)
    client._chart_session = "cs_fixed"
    client._quote_session = "qs_fixed"
    sent: list[str] = []

    class DummyWS:
        def send(self, msg: str) -> None:
            sent.append(msg)

    client._ws = DummyWS()
    client._handshake()
    methods = [json.loads(m.split("~m~", 2)[2])["m"] for m in sent]
    assert methods == [
        "set_auth_token",
        "chart_create_session",
        "quote_create_session",
        "quote_set_fields",
    ]


def test_subscribe_sends_expected_sequence() -> None:
    sub = Subscription("ABC:XYZ", "5")
    client = TvWSClient([], n_init_bars=3)
    client._chart_session = "cs_test"
    client._quote_session = "qs_test"
    sent: list[str] = []
    client._ws = type("W", (), {"send": lambda self, msg: sent.append(msg)})()
    client._subs = [sub]
    client._subscribe_all()
    loaded = [json.loads(msg.split("~m~", 2)[2]) for msg in sent]
    names = [m["m"] for m in loaded]
    assert names == ["quote_add_symbols", "resolve_symbol", "create_series"]


def test_handle_payload_tick_and_bar_events() -> None:
    client = TvWSClient([], n_init_bars=1)
    q = client._q
    # Non-JSON payload is ignored
    client._handle_payload("not json")
    with pytest.raises(queue.Empty):
        q.get_nowait()

    # Tick event (qsd) yields typed Tick
    ts_ms = 1_600_000_000_000
    payload = json.dumps({"m": "qsd", "p": []})
    payload = payload[:-1] + f', "lp":1.23, "volume":4.56, "upd":{ts_ms}}}'
    client._handle_payload(payload)
    evt = q.get_nowait()
    assert isinstance(evt, Tick)
    assert evt.price == pytest.approx(1.23)
    assert evt.volume == pytest.approx(4.56)
    assert isinstance(evt.ts, datetime) and evt.ts.tzinfo is timezone.utc

    # series_completed -> bar event
    payload = json.dumps({"m": "series_completed", "p": ["x", "alias_key"]})
    client._handle_payload(payload)
    evt2 = q.get_nowait()
    assert evt2 == {"type": "bar", "sub": "alias_key", "status": "completed"}

    # du -> bar events yields typed Bar and populates buffer
    epoch = 1_600_000_000
    bar_list = [[epoch, 1, 2, 3, 4, 5, True]]
    # register mapping so event is recognized
    client._series["s1234"] = Subscription("SYM", "1")
    payload = json.dumps({"m": "du", "p": ["s1234", bar_list]})
    client._handle_payload(payload)
    evt3 = q.get_nowait()
    assert isinstance(evt3, Bar)
    assert evt3.open == 1
    assert evt3.high == 2
    assert evt3.low == 3
    assert evt3.close == 4
    assert evt3.volume == 5
    assert evt3.closed is True
    assert isinstance(evt3.ts, datetime)
