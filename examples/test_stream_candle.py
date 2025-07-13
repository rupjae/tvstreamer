#!/usr/bin/env python3
"""
test_stream_candle.py
================
Pure‑standard‑library example that streams **completed 1‑minute candles**
for a TradingView symbol, printing each closed bar in real time.

Highlights
----------
* Requires you to be logged in to TradingView in Safari – the script reads
  the `sessionid` cookie for authentication and exits otherwise.
* No external packages required (optional Safari cookie parsing if the
  `binarycookie` module is present).
* Minimal WebSocket implementation – only what is needed for TradingView.
* Emits a “META” line (or a JSON object with `"type": "META"`) containing
  full symbol metadata as soon as TradingView sends it.

Usage
-----
    python test_stream_candle.py BINANCE:BTCUSDT
  • To emit newline‑delimited JSON instead of pretty text:
      python test_stream_candle.py BINANCE:BTCUSDT -f json
"""
# ---------------------------------------------------------------------------

import os
import ssl
import socket
import base64
import json
import random
import string
import struct
import re
import sys
import argparse
import time
from pathlib import Path
from datetime import datetime, timezone

# ------------------------------ CONFIG --------------------------------------

PORT = 443
RESOURCE = "/socket.io/websocket"

DEBUG = False  # True = log every inbound / outbound WebSocket frame
SHOW_LIVE = False  # True = also print intrabar “LIVE” updates (very chatty)

RETRY_DELAY_INIT = 5  # First reconnect after N seconds
RETRY_DELAY_MAX = 60  # Cap exponential back‑off at this many seconds

# Output format: False ➜ pretty text, True ➜ newline‑delimited JSON (ndjson)
OUTPUT_JSON = False
SYMBOL_INFO = None  # Populated after receiving “symbol_resolved” metadata

# ---------------------------------------------------------------------------
# Optional `binarycookie` import for Safari cookie reading
try:
    from binarycookie import parse as _bc_parse
except ModuleNotFoundError:  # pragma: no cover
    _bc_parse = None

# ------------------------- WebSocket helpers --------------------------------


def _mask(payload: bytes) -> bytes:
    key = os.urandom(4)
    return key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def ws_send(sock: socket.socket, text: str):
    payload = text.encode()
    hdr = bytearray([0x81])  # FIN=1, opcode=TEXT
    ln = len(payload)
    if ln < 126:
        hdr.append(0x80 | ln)
    elif ln < 65536:
        hdr += struct.pack("!BH", 0x80 | 126, ln)
    else:
        hdr += struct.pack("!BQ", 0x80 | 127, ln)
    sock.sendall(hdr + _mask(payload))
    if DEBUG:
        print(f">> {text}")


def ws_recv(sock: socket.socket) -> str:
    """
    Return UTF‑8 payload of next TEXT frame (other opcodes are ignored).
    """
    head = sock.recv(2)
    if len(head) < 2:
        raise ConnectionResetError("peer closed")  # treat graceful close as fatal
    b1, b2 = struct.unpack("!BB", head)
    opcode = b1 & 0x0F
    masked = b2 >> 7
    ln = b2 & 0x7F
    if ln == 126:
        (ln,) = struct.unpack("!H", sock.recv(2))
    elif ln == 127:
        (ln,) = struct.unpack("!Q", sock.recv(8))
    mask_key = sock.recv(4) if masked else b""
    data = bytearray()
    while len(data) < ln:
        chunk = sock.recv(ln - len(data))
        if not chunk:
            break
        data.extend(chunk)
    if masked and mask_key:
        data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
    if DEBUG:
        # Attempt to decode the payload for pretty printing.
        try:
            decoded = data.decode("utf-8", "replace")
        except Exception:
            # Binary or undecodable payload – fall back to repr.
            print(f"<< {data!r}")
        else:
            # When a WebSocket frame contains several TradingView
            # sub‑messages (e.g. “~h~1” heartbeat + “~m~…~m~{…}” data),
            # print them on separate lines for readability.
            if "~m~" in decoded:
                for part in re.split(r"~m~\d+~m~", decoded):
                    if part:
                        print(f"<< {part}")
            else:
                print(f"<< {decoded}")
    if opcode != 0x1:
        return ""
    try:
        return data.decode()
    except UnicodeDecodeError:
        return ""


# ----------------------- TradingView helpers ---------------------------------


def _tv_wrap(cmd: str, params):
    payload = json.dumps({"m": cmd, "p": params})
    return f"~m~{len(payload)}~m~{payload}"


def _announce(expiry: datetime | int | float | str | None, sid: str | None):
    """
    Emit a concise debug line about login status and Safari cookie expiry.

    Supported `expiry` types
    ------------------------
    • datetime (aware or naive)          – converted to UTC
    • int / float (epoch seconds)        – interpreted as UTC timestamp
    • RFC‑1123 string (Safari default)   – “Tue, 29 Jul 2025 13:00:00 GMT”
    • “YYYY‑MM‑DD HH:MM UTC”             – format used by test_auth.py
    • None                               – expiry unavailable
    """
    if not DEBUG:
        return

    if not sid:
        print(">> Running anonymous – data may be delayed.")
        return

    # ── normalise to an aware UTC datetime ───────────────────────────────
    exp_dt: datetime | None = None

    if isinstance(expiry, datetime):
        exp_dt = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)

    elif isinstance(expiry, (int, float)):
        exp_dt = datetime.fromtimestamp(expiry, tz=timezone.utc)

    elif isinstance(expiry, str):
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d %H:%M %Z"):
            try:
                exp_dt = datetime.strptime(expiry.strip(), fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue

    # ── emit one‑liner ─────────────────────────────────────────────────────
    if exp_dt:
        delta = exp_dt - datetime.now(timezone.utc)
        days_left = max(delta.days, 0)
        print(
            f">> Authenticated (cookie expires {exp_dt:%Y-%m-%d %H:%M UTC}, "
            f"{days_left} days left)"
        )
    else:
        print(">> Authenticated – cookie expiry unknown.")


def _get_safari_cookies():
    """
    Returns
    -------
    tuple[str | None, str | None, datetime | int | float | str | None]
        (sessionid, auth_token, expiry) – extracted solely from Safari
        Cookies.binarycookies; no environment‑variable fallback.
    """
    sid = None
    atok = None
    exp_dt = None

    cookie_path = Path(
        "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"
    ).expanduser()

    # Parse Safari cookies to obtain credentials and expiry.
    if cookie_path.exists() and _bc_parse is not None:
        try:
            for c in _bc_parse(cookie_path.read_bytes()):
                if ".tradingview.com" not in c.domain:
                    continue
                if c.name == "sessionid":
                    sid = c.value
                    # Gather every plausible expiry attribute this `Cookie` object may carry.
                    attr_names = (
                        "expiry_date",  # binarycookie >= macOS 14
                        "expires_date",  # older macOS builds
                        "expiry",
                        "expires",  # generic
                        "expiry_epoch",
                        "expires_epoch",
                        "expiryDate",
                        "expiresDate",  # camel‑case edge cases
                    )
                    for attr in attr_names:
                        exp_candidate = getattr(c, attr, None)
                        if exp_candidate is not None:
                            break
                    else:
                        exp_candidate = None
                    if isinstance(exp_candidate, (int, float)):
                        exp_candidate = datetime.fromtimestamp(exp_candidate, timezone.utc)
                    elif isinstance(exp_candidate, str):
                        # Try to parse common RFC‑1123 / cookie date formats
                        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y"):
                            try:
                                exp_candidate = datetime.strptime(
                                    exp_candidate.strip(), fmt
                                ).replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue
                    exp_dt = exp_candidate or exp_dt
                elif c.name == "auth_token":
                    atok = c.value
        except Exception:
            pass  # ignore parsing failures

    return sid, atok, exp_dt


def _fmt_bar(ts, o, h, l, c_, v_):
    # Render a candle timestamp (UTC) as “YYYY‑MM‑DD HH:MM”.
    timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
    return f"{timestamp}  O:{o} H:{h} L:{l} C:{c_} V:{v_}"


# ---------------------------------------------------------------------------
# Unified printer -----------------------------------------------------------


def _emit_bar(kind: str, ts, o, h, l, c_, v_):
    """
    Print one bar either as human‑readable text or as a single‑line JSON object.

    Parameters
    ----------
    kind : str
        One of "HIST", "LIVE", or "CLOSE".
    """
    if OUTPUT_JSON:
        print(
            json.dumps(
                {
                    "type": kind.strip(),
                    "timestamp": ts,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c_,
                    "volume": v_,
                }
            )
        )
    else:
        # Pad label to 5 chars to align with previous output
        print(f"{kind:<5}", _fmt_bar(ts, o, h, l, c_, v_))


# ------------------------ Metadata printer -----------------------------------


def _emit_meta(info: dict):
    """
    Emit one “META” message containing symbol metadata.

    Parameters
    ----------
    info : dict
        The metadata dictionary contained in TradingView’s `symbol_resolved`
        payload.
    """
    global SYMBOL_INFO
    SYMBOL_INFO = info  # expose for downstream import if needed

    if OUTPUT_JSON:
        print(json.dumps({"type": "META", **info}))
    else:
        # Pretty‑print a concise one‑liner followed by the raw JSON dict
        sym = info.get("pro_name") or info.get("name") or "<unknown>"
        print(f"META  {sym}  ({info.get('description', '').strip()})")
        print(json.dumps(info, indent=2))


# ------------------------ Candle loop ----------------------------------------


def candle_loop(sock: socket.socket):
    """
    Consume TradingView WebSocket messages in an infinite loop and emit
    completed candles via `_emit_bar()`. Handles both historical back‑fill and
    live updates. Exits only when the underlying socket raises, signalling the
    caller to reconnect.
    """
    active_ts = None
    cache = None
    while True:
        msg = ws_recv(sock)
        if not msg:
            continue
        # Proceed to splitting msg into parts for TradingView sub‑messages
        for part in re.split(r"~m~\d+~m~", msg)[1:]:
            # ── Socket.IO heartbeat (<~h~n>) – must be echoed back wrapped
            if part.startswith("~h~"):
                # Re‑wrap the ping inside a new Socket.IO frame exactly as TV expects
                ws_send(sock, f"~m~{len(part)}~m~{part}")
                continue
            try:
                evt = json.loads(part)
            except json.JSONDecodeError:
                continue

            # Capture symbol metadata as soon as it arrives
            if evt.get("m") == "symbol_resolved":
                meta_info = evt["p"][2] if len(evt["p"]) >= 3 else {}
                _emit_meta(meta_info)
                continue

            if evt.get("m") == "timescale_update":
                series = evt["p"][1]
                key = next(iter(series))
                bars = series[key]["s"]

                # If a new candle has started, close the previous one
                if cache and bars and cache[0] != bars[-1]["v"][0]:
                    _emit_bar("CLOSE", *cache)

                # Emit only fully‑closed candles; the final bar in the list is
                # the currently‑forming minute and should not be printed yet.
                for bar in bars[:-1]:
                    ts, o, h, l, c_, v_ = bar["v"]
                    _emit_bar("HIST", ts, o, h, l, c_, v_)

                # Prepare the last (still open) bar for live updates
                if bars:
                    active_ts = bars[-1]["v"][0]
                    cache = bars[-1]["v"]
                continue

            if evt.get("m") not in ("timescale_update", "du"):
                continue
            series = evt["p"][1]
            key = next(iter(series))  # sds_1 etc.
            for bar in series[key]["s"]:
                ts, o, h, l, c_, v_ = bar["v"]
                if active_ts is None:
                    active_ts = ts
                # Candle closed when timestamp advances
                if ts != active_ts and cache:
                    _emit_bar("CLOSE", *cache)
                    active_ts = ts
                if SHOW_LIVE:
                    _emit_bar("LIVE", ts, o, h, l, c_, v_)
                cache = (ts, o, h, l, c_, v_)


def _connect_and_boot(symbol: str, sid: str, atok: str | None, history: int) -> socket.socket:
    """
    Establish a TLS‑encrypted WebSocket connection to TradingView, authenticate
    using the provided cookies, open a chart session, resolve the symbol, and
    request the desired number of 1‑minute candles.

    Parameters
    ----------
    symbol : str
        TradingView symbol identifier (e.g. "NASDAQ:TSLA").
    sid : str
        Value of the `sessionid` cookie (required).
    atok : str | None
        Value of the optional `auth_token` cookie granting real‑time permissions.
    history : int
        Number of historical candles to preload (1‑minute resolution).

    Returns
    -------
    socket.socket
        Connected and handshake‑completed WebSocket ready for `candle_loop()`.
    """
    host = "prodata.tradingview.com"
    origin = "https://prodata.tradingview.com"

    # ---- TLS + WebSocket handshake --------------------------------------
    raw = socket.create_connection((host, PORT))
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    sock.settimeout(30)  # hard read timeout to trigger reconnect
    ws_key = base64.b64encode(os.urandom(16)).decode()

    headers = [
        f"GET {RESOURCE} HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Origin: {origin}",
        f"Sec-WebSocket-Key: {ws_key}",
        "Sec-WebSocket-Version: 13",
        f"Cookie: sessionid={sid}",
    ]

    handshake = "\r\n".join(headers) + "\r\n\r\n"
    sock.sendall(handshake.encode())
    if b"101" not in sock.recv(1024):
        raise RuntimeError("WebSocket upgrade failed")

    # ---- TradingView boot sequence ------------------------------------------
    if atok:
        ws_send(sock, _tv_wrap("set_auth_token", [atok]))

    cs = "cs_" + "".join(random.choices(string.ascii_lowercase, k=12))
    ws_send(sock, _tv_wrap("chart_create_session", [cs, ""]))

    sym_descriptor = json.dumps(
        {
            "symbol": symbol,
            "adjustment": "splits",
            "session": "extended",
        }
    )
    ws_send(sock, _tv_wrap("resolve_symbol", [cs, "sds_sym_0", f"={sym_descriptor}"]))
    ws_send(sock, _tv_wrap("create_series", [cs, "sds_1", "s0", "sds_sym_0", "1", history, ""]))

    print(f">> Streaming completed 1‑minute candles for {symbol} …\n")
    return sock


# ---------------------------- Main -------------------------------------------


def main():
    """
    Parse command‑line arguments, set the desired output format, maintain a
    reconnect loop with exponential back‑off, and delegate actual streaming to
    `candle_loop()`.
    """
    parser = argparse.ArgumentParser(
        description="Stream completed 1‑minute candles with optional historical back‑fill."
    )
    parser.add_argument(
        "symbol",
        nargs="?",
        default="BINANCE:BTCUSDT",
        help="TradingView symbol, e.g. NASDAQ:TSLA",
    )
    parser.add_argument(
        "--history",
        "-n",
        type=int,
        default=1000,
        help="Number of historical bars to preload (default: 1000)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format for bars (default: text; use 'json' for ndjson)",
    )
    args = parser.parse_args()

    global OUTPUT_JSON
    OUTPUT_JSON = args.format == "json"

    symbol = args.symbol
    history = args.history

    if len(sys.argv) < 2 and DEBUG:
        print(f">> No symbol argument given – defaulting to {symbol}")

    delay = RETRY_DELAY_INIT
    while True:
        # Re‑read Safari cookies so a refreshed sessionid is picked up automatically
        sid, atok, exp = _get_safari_cookies()
        if not sid:
            sys.exit(
                "ERROR: TradingView session cookie not found. "
                "Log in to tradingview.com in Safari and retry."
            )
        _announce(exp, sid)

        try:
            sock = _connect_and_boot(symbol, sid, atok, history)
            delay = RETRY_DELAY_INIT  # successful connect → reset back‑off
            candle_loop(sock)
        except (
            socket.timeout,
            OSError,
            ssl.SSLError,
            socket.error,
            RuntimeError,
        ) as exc:
            print(f">> Connection lost: {exc} – retrying in {delay}s …")
            time.sleep(delay)
            delay = min(delay * 2, RETRY_DELAY_MAX)
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
