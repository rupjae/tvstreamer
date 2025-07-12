from datetime import datetime
from pathlib import Path
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" and not (os.getenv("TV_SESSIONID") and os.getenv("TV_AUTH_TOKEN")),
    reason="requires macOS or TradingView cookies via env vars",
)

import tvstreamer.auth as auth


class DummyCookie:
    def __init__(self, name: str, value: str, domain: str) -> None:
        self.name = name
        self.value = value
        self.domain = domain
        self.expiry_date = "Wed, 10 Jul 2025"


def test_get_safari_cookies(monkeypatch, tmp_path) -> None:
    data = b"fakebinary"
    cookie_file = tmp_path / "Cookies.binarycookies"
    cookie_file.write_bytes(data)

    monkeypatch.setattr(auth.Path, "expanduser", lambda p: cookie_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(auth.Path, "exists", lambda p: True)  # type: ignore[attr-defined]
    monkeypatch.setattr(auth.Path, "read_bytes", lambda p: data)  # type: ignore[attr-defined]

    def fake_parse(raw: bytes):
        assert raw == data
        return [
            DummyCookie("sessionid", "ABC", ".tradingview.com"),
            DummyCookie("auth_token", "TOKEN", ".tradingview.com"),
        ]

    monkeypatch.setattr(auth, "parse", fake_parse)
    result = auth.get_safari_cookies()
    assert result.sessionid == "ABC"
    assert result.auth_token == "TOKEN"
    assert result.is_authenticated
    assert isinstance(result.expiry, datetime) or result.expiry is None


def test_discover_tv_cookies_env(monkeypatch) -> None:
    monkeypatch.setenv("TV_SESSIONID", "SID")
    monkeypatch.setenv("TV_AUTH_TOKEN", "T")
    res = auth.discover_tv_cookies()
    assert res.sessionid == "SID"
    assert res.auth_token == "T"
    assert res.is_authenticated


def test_get_safari_cookies_parse_error(monkeypatch, tmp_path) -> None:
    cookie_file = tmp_path / "Cookies.binarycookies"
    cookie_file.write_bytes(b"err")
    monkeypatch.setattr(auth.Path, "expanduser", lambda p: cookie_file)  # type: ignore[attr-defined]
    monkeypatch.setattr(auth.Path, "exists", lambda p: True)  # type: ignore[attr-defined]
    monkeypatch.setattr(auth.Path, "read_bytes", lambda p: b"err")  # type: ignore[attr-defined]
    monkeypatch.setattr(auth, "parse", lambda _b: (_ for _ in ()).throw(ValueError("boom")))
    res = auth.get_safari_cookies()
    assert res.sessionid is None and res.auth_token is None


def test_discover_tv_cookies_safari(monkeypatch):
    monkeypatch.delenv("TV_SESSIONID", raising=False)
    monkeypatch.delenv("TV_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(auth, "get_safari_cookies", lambda: auth.AuthCookies("S", "A", None))
    monkeypatch.setattr(auth.sys, "platform", "darwin")
    res = auth.discover_tv_cookies()
    assert res.sessionid == "S" and res.auth_token == "A"
