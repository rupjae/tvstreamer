#!/usr/bin/env python3
# Streams 1‑minute candles for BINANCE:BTCUSDT from TradingView.
# Standard‑library only: socket, ssl, json, struct, base64.

import os, ssl, socket, base64, hashlib, json, random, string, struct, re, threading, time

from pathlib import Path
from binarycookie import parse

HOST = "prodata.tradingview.com"
PORT = 443
RESOURCE = "/socket.io/websocket"
ORIGIN = "https://prodata.tradingview.com"

# ---------------------------------------------------------------------------
# Debug switch: set to True to dump every raw WebSocket frame (incoming/outgoing)
DEBUG = True


# Helper: announce whether we’re running authenticated or anonymous
def _announce_login(sessionid):
    if DEBUG:
        if sessionid:
            print(">> TradingView login succeeded – authenticated session.")
        else:
            print(">> No TV credentials found – running anonymous.")


# ---------------------------------------------------------------------------
# TradingView authentication via Safari cookies
# We pull both `sessionid` (required for the WS handshake) **and** `auth_token`
# (optional but lets the server emit an "authenticated" confirmation event).
# ---------------------------------------------------------------------------


def _get_safari_cookies():
    """
    Returns
    -------
    tuple[str | None, str | None]
        (sessionid, auth_token) from Safari’s Cookies.binarycookies, or
        (None, None) if not present.
    """
    sid = atok = None
    exp_raw = None
    cookie_path = Path(
        "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"
    ).expanduser()
    if not cookie_path.exists():
        return sid, atok

    try:
        for c in parse(cookie_path.read_bytes()):
            if ".tradingview.com" not in c.domain:
                continue
            if c.name == "sessionid":
                sid = c.value
                # capture any expiry field this build exposes
                exp_raw = next(
                    (
                        getattr(c, a)
                        for a in (
                            "expiry_date",
                            "expiry",
                            "expires",
                            "expires_utc",
                            "expiry_epoch",
                            "expires_epoch",
                        )
                        if hasattr(c, a)
                    ),
                    None,
                )
            elif c.name == "auth_token":
                atok = c.value
    except Exception:
        pass  # parsing failure → stay anonymous
    # Optional debug output showing when the cookie expires
    if DEBUG and sid:
        from datetime import datetime, timezone as _tz

        exp_dt = None
        if isinstance(exp_raw, (int, float)):
            exp_dt = datetime.fromtimestamp(exp_raw, _tz.utc)
        elif isinstance(exp_raw, str):
            try:
                exp_dt = datetime.strptime(exp_raw.strip(), "%a, %d %b %Y").replace(tzinfo=_tz.utc)
            except ValueError:
                pass

        if exp_dt:
            days_left = (exp_dt - datetime.now(_tz.utc)).days
            exp_str = exp_dt.strftime("%Y-%m-%d %H:%M UTC")
            print(f">> Safari sessionid cookie expires {exp_str}  ({days_left} days remaining)")
        else:
            print(">> Safari sessionid cookie expiry unknown")
    return sid, atok


#
# ── WebSocket framing helpers ───────────────────────────────────────────────────
def _mask(payload: bytes) -> bytes:
    key = os.urandom(4)
    return key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def ws_send(sock, text: str):
    payload = text.encode()
    header = bytearray([0x81])  # FIN=1, text
    ln = len(payload)
    if ln < 126:
        header.append(0x80 | ln)
    elif ln < 65536:
        header += struct.pack("!BH", 0x80 | 126, ln)
    else:
        header += struct.pack("!BQ", 0x80 | 127, ln)
    if DEBUG:
        print(f">> {text}")
    sock.sendall(header + _mask(payload))


def ws_recv(sock):
    """
    Receive one WebSocket TEXT frame and return its UTF‑8 payload.

    Non‑text opcodes and undecodable payloads are skipped (empty string).
    """
    # ---- 2‑byte base header ----
    header = sock.recv(2)
    if len(header) < 2:  # connection closed
        return ""
    b1, b2 = struct.unpack("!BB", header)
    opcode = b1 & 0x0F  # 0x1 = TEXT
    masked = b2 >> 7
    ln = b2 & 0x7F

    # ---- extended payload length ----
    if ln == 126:
        (ln,) = struct.unpack("!H", sock.recv(2))
    elif ln == 127:
        (ln,) = struct.unpack("!Q", sock.recv(8))

    mask_key = sock.recv(4) if masked else b""

    # ---- payload ----
    data = bytearray()
    while len(data) < ln:
        chunk = sock.recv(ln - len(data))
        if not chunk:
            break
        data.extend(chunk)

    if DEBUG:
        # Show raw payload even for binary / control frames
        try:
            print(f"<< {data.decode('utf-8', errors='replace')}")
        except Exception:
            print(f"<< {data!r}")

    # ---- unmask if needed ----
    if masked and mask_key:
        data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))

    # skip non‑text frames
    if opcode != 0x1:
        return ""

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


# ── TradingView helpers ─────────────────────────────────────────────────────────
def tv_wrap(cmd: str, params):
    data = json.dumps({"m": cmd, "p": params})
    return f"~m~{len(data)}~m~{data}"


# ── Pretty‑print helper ─────────────────────────────────────────────────────────
def _print_bar(label, ts, o, h, l, c_, v_):
    """
    Print a candle with a prefix label so closed vs live bars stand out.
    """
    print(
        f"{label:<6} "
        f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))} "
        f"O:{o} H:{h} L:{l} C:{c_} V:{v_}"
    )


def heartbeat_loop(sock):
    """
    Handle incoming TradingView messages, maintain heartbeat,
    and print candles distinguishing LIVE updates from CLOSED bars.
    """
    active_ts = None  # timestamp of the candle currently forming
    cached_bar = None  # last full values seen for the active candle

    while True:
        msg = ws_recv(sock)
        if not msg:
            continue

        for part in re.split(r"~m~\d+~m~", msg)[1:]:
            # ---- TradingView heartbeat -------------------------------------------------
            if part.startswith("~h~"):
                pong = f"~m~{len(part)}~m~{part}"
                ws_send(sock, pong)
                continue

            # ---- JSON‑encoded events ---------------------------------------------------
            try:
                evt = json.loads(part)
            except json.JSONDecodeError:
                continue

            if evt.get("m") == "authenticated":
                if DEBUG:
                    print("<< AUTH CONFIRMED by server")
                continue

            if evt.get("m") not in ("timescale_update", "du"):
                continue

            candles = evt["p"][1]["sds_1"]["s"]
            for c in candles:
                ts, o, h, l, cl, v = c["v"]

                # First bar seen
                if active_ts is None:
                    active_ts = ts

                # New candle started -> emit cached final bar as CLOSED
                if ts != active_ts and cached_bar:
                    _print_bar("CLOSE", *cached_bar)
                    active_ts = ts  # roll forward

                # Print LIVE update and cache it
                _print_bar("LIVE", ts, o, h, l, cl, v)

                cached_bar = (ts, o, h, l, cl, v)


def main():
    # TLS socket + RFC‑6455 handshake
    raw = socket.create_connection((HOST, PORT))
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
    key = base64.b64encode(os.urandom(16)).decode()

    # --- Retrieve cookies from Safari ---
    SESSION_ID, AUTH_TOKEN = _get_safari_cookies()
    _announce_login(SESSION_ID)

    # --- Build WebSocket upgrade request ---
    cookie_hdr = f"Cookie: sessionid={SESSION_ID}\r\n" if SESSION_ID else ""
    handshake = (
        f"GET {RESOURCE} HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nOrigin: {ORIGIN}\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n{cookie_hdr}\r\n"
    )
    sock.sendall(handshake.encode())
    if b"101" not in sock.recv(1024):
        raise RuntimeError("WebSocket upgrade failed")
    # Send auth token so the server can confirm login
    if AUTH_TOKEN:
        ws_send(sock, tv_wrap("set_auth_token", [AUTH_TOKEN]))

    # Authorise (with token) and subscribe
    cs = "cs_" + "".join(random.choices(string.ascii_lowercase, k=12))
    ws_send(sock, tv_wrap("chart_create_session", [cs, ""]))
    # Request extended‑hours (pre‑ & post‑market) candles by adding "session":"extended"
    sym = json.dumps(
        {
            "symbol": "NASDAQ:NVDA",
            "adjustment": "splits",
            "session": "extended",  # <‑‑ key part
        }
    )
    ws_send(sock, tv_wrap("resolve_symbol", [cs, "sds_sym_0", f"={sym}"]))
    ws_send(sock, tv_wrap("create_series", [cs, "sds_1", "s0", "sds_sym_0", "1", 1, ""]))

    threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True).start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
