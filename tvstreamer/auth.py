from __future__ import annotations

"""Authentication helpers using browser cookies."""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from binarycookie import parse


@dataclass(frozen=True)
class AuthCookies:
    """Container for TradingView session cookies."""

    sessionid: Optional[str]
    auth_token: Optional[str]
    expiry: Optional[datetime]

    @property
    def is_authenticated(self) -> bool:
        """Return ``True`` when both cookie values are present."""

        return bool(self.sessionid and self.auth_token)


def _convert_expiry(raw: object) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str):
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y",
            "%Y-%m-%d %H:%M:%S %z",
        ):
            try:
                return datetime.strptime(raw.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def get_safari_cookies() -> AuthCookies:
    """Return cookies extracted from Safari's binary storage."""

    cookie_path = Path(
        "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"
    ).expanduser()
    if not cookie_path.exists():
        return AuthCookies(None, None, None)
    sid = None
    atok = None
    expiry = None
    try:
        for c in parse(cookie_path.read_bytes()):
            if ".tradingview.com" not in c.domain:
                continue
            if c.name == "sessionid":
                sid = c.value
                exp_raw = None
                for attr in (
                    "expiry_date",
                    "expiry",
                    "expires",
                    "expires_utc",
                    "expiry_epoch",
                    "expires_epoch",
                ):
                    if hasattr(c, attr):
                        exp_raw = getattr(c, attr)
                        if exp_raw:
                            break
                expiry = _convert_expiry(exp_raw)
            elif c.name == "auth_token":
                atok = c.value
    except Exception:
        return AuthCookies(None, None, None)
    return AuthCookies(sid, atok, expiry)


def discover_tv_cookies() -> AuthCookies:
    """Discover TradingView cookies via environment or browser stores."""

    sid = os.getenv("TV_SESSIONID")
    atok = os.getenv("TV_AUTH_TOKEN")
    if sid or atok:
        return AuthCookies(sid, atok, None)

    if sys.platform == "darwin":
        cookies = get_safari_cookies()
        if cookies.sessionid or cookies.auth_token:
            return cookies

    # Future: Chrome/Firefox support
    return AuthCookies(None, None, None)
