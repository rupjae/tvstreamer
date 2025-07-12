import json
import os
import sys
from typing import cast

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" and not (os.getenv("TV_SESSIONID") and os.getenv("TV_AUTH_TOKEN")),
    reason="requires macOS or TradingView cookies via env vars",
)

from tvstreamer.wsclient import TvWSClient
from tvstreamer.auth import AuthCookies


def test_header_and_token(monkeypatch):
    headers = []

    class DummyWS:
        def __init__(self):
            self.sent = []

        def send(self, msg: str) -> None:
            self.sent.append(msg)

        def close(self) -> None:
            pass

    def fake_create(*args, **kwargs):
        headers.extend(kwargs.get("header", []))
        return DummyWS()

    monkeypatch.setattr("tvstreamer.wsclient.create_connection", fake_create)
    monkeypatch.setattr(TvWSClient, "_subscribe_all", lambda self: None)

    auth = AuthCookies("SID", "AT", None)
    client = TvWSClient([("SYM:A", "1")], auth=auth, auto_auth=False)
    client.connect()

    assert f"Cookie: sessionid={auth.sessionid}" in headers
    sent = cast(DummyWS, client._ws).sent
    first = json.loads(sent[0].split("~m~", 2)[2])
    assert first["m"] == "set_auth_token"
    assert first["p"] == [auth.auth_token]
