"""tvstreamer.wsclient – minimal TradingView WebSocket streaming client.

This implementation keeps *only* what is required to:

* open a single TradingView WebSocket connection;
* subscribe to **many** symbol / interval pairs (1-m or n-m);
* surface two kinds of events to user-space:
    1. *ticks*  – every price/volume update pushed by TradingView;
    2. *bars*   – closed candles (OHLCV).

The public API purposefully stays tiny and synchronous – users can choose
whether to run it in its own thread / process.
"""

from __future__ import annotations

import json
import logging
import queue
import random
import re
import string
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Generator, List, Tuple

# Heavy dependency; we import lazily to allow docs / type-checking without runtime package.
try:
    from websocket import create_connection, WebSocket  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    # Stub fallback so that type hints work in editor; actual runtime failure will
    # occur when *connect()* is called if dependency missing.
    WebSocket = object  # type: ignore

    def create_connection(*_a, **_kw):  # type: ignore
        raise ModuleNotFoundError("websocket-client package is required for TvWSClient")


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Subscription:
    """Immutable subscription key."""

    symbol: str  # e.g. BINANCE:BTCUSDT or NSE:RELIANCE
    interval: str  # TradingView internal resolution code – "1", "1H", …

    def key(self) -> str:  # TradingView series id we choose
        return f"sub_{self.symbol.replace(':', '_')}_{self.interval}"


# ---------------------------------------------------------------------------
# Core WS client
# ---------------------------------------------------------------------------


class TvWSClient:
    """Minimal synchronous TradingView WebSocket client.

    Example
    -------
    ```python
    client = TvWSClient(
        [("BINANCE:BTCUSDT", "1"), ("NYSE:MSFT", "1D")],
        n_init_bars=500,
    )
    client.connect()

    for event in client.stream():
        match event["type"]:
            case "tick":
                ...
            case "bar":
                ...
    ```
    """

    WS_ENDPOINT = "wss://data.tradingview.com/socket.io/websocket"

    def __init__(
        self,
        subscriptions: List[Tuple[str, str]],
        *,
        n_init_bars: int | None = None,
        token: str = "unauthorized_user_token",
        ws_debug: bool = False,
    ):
        self._subs: List[Subscription] = [
            Subscription(sym, tf) for sym, tf in subscriptions
        ]
        # TradingView rejects history=0; fall back to a sane default
        if n_init_bars is None or n_init_bars <= 0:
            n_init_bars = 300
        self._n_init_bars = n_init_bars

        self._token = token
        self._ws: WebSocket | None = None
        self._ws_debug = ws_debug

        self._stop_flag = threading.Event()

        # Internal session ids – have to be random per connection
        self._chart_session = self._gen_chart_session()
        self._quote_session = self._gen_quote_session()

        # Outgoing / incoming queues so that user can iterate easily
        self._q: "queue.Queue[dict]" = queue.Queue()

        # Background read thread
        self._rx_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self):
        """Open the websocket and start background listener."""

        if self._ws is not None:
            raise RuntimeError("Client already connected")

        logger.debug("Opening TradingView websocket…")
        self._ws = create_connection(self.WS_ENDPOINT, timeout=7)

        self._handshake()
        self._subscribe_all()

        self._rx_thread = threading.Thread(
            target=self._reader_loop, name="tvws_reader", daemon=True
        )
        self._rx_thread.start()

    def close(self):
        """Close the connection and stop reader thread."""

        self._stop_flag.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001 – best-effort close
                pass
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2)

    # Allow use with *with* statement ---------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: D401 – *context-manager*
        self.close()

    # Stream iterator --------------------------------------------------

    def stream(self) -> Generator[dict, None, None]:
        """Yield events as produced by background thread until *close()* is called."""

        while not self._stop_flag.is_set() or not self._q.empty():
            try:
                event = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            yield event

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ---- Session / message creation ----------------------------------

    @staticmethod
    def _prepend_header(payload: str) -> str:
        return f"~m~{len(payload)}~m~{payload}"

    @staticmethod
    def _construct_msg(func: str, params: List):
        return json.dumps({"m": func, "p": params}, separators=(",", ":"))

    def _send(self, func: str, params: List):
        msg = self._prepend_header(self._construct_msg(func, params))
        if self._ws_debug:
            # Echo to stdout for interactive debugging **and** persist in log files.
            print("->", msg)
            logger.info("WS TX %s", msg, extra={"code_path": __file__})
        assert self._ws is not None, "WS not connected"
        self._ws.send(msg)

    @staticmethod
    def _gen_chart_session() -> str:
        return "cs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

    @staticmethod
    def _gen_quote_session() -> str:
        return "qs_" + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

    # ---- Handshake / subscribe --------------------------------------

    def _handshake(self):
        """Authentication token + session creation."""

        self._send("set_auth_token", [self._token])
        self._send("chart_create_session", [self._chart_session])
        self._send("quote_create_session", [self._quote_session])
        self._send("quote_set_fields", [self._quote_session, "lp", "volume", "ch"])

        # NB: we do *not* set quote_set_fields – client may do so later if desired.

    def _subscribe_all(self):
        for sub in self._subs:
            self._subscribe(sub)

    def _subscribe(self, sub: Subscription):
        symbol = sub.symbol
        symbol_upper = symbol.upper()

        # TradingView requires a numeric‑style series id that starts with "s"
        series_id = f"s{random.randint(1_000, 9_999)}"
        alias = sub.key()  # symbol alias for resolve_symbol

        # Quote subscription (for last trade ‘tick’ updates)
        self._send(
            "quote_add_symbols",
            [self._quote_session, symbol_upper],
        )

        # Resolve symbol and subscribe for bars
        descriptor = f'={{"symbol":"{symbol_upper}","adjustment":"splits"}}'
        self._send("resolve_symbol", [self._chart_session, alias, descriptor])

        # create_series expects: [cs, series_id, series_id, alias, resolution, history, ""]
        self._send(
            "create_series",
            [
                self._chart_session,  # chart session
                series_id,  # series id (sXXXX)
                series_id,  # duplicated id
                alias,  # symbol alias
                sub.interval,  # resolution ("1" etc.)
                max(1, self._n_init_bars),
                "",  # no extended session
            ],
        )

    # ---- Background reader -----------------------------------------

    def _reader_loop(self):
        assert self._ws is not None, "WS not connected"

        buffer = ""
        while not self._stop_flag.is_set():
            try:
                raw = self._ws.recv()
                # Echo back TradingView heartbeat to keep the connection alive
                if raw.startswith("~m~") and "~h~" in raw:
                    try:
                        self._ws.send(raw)
                    except Exception:  # noqa: BLE001 – heartbeat echo failure
                        logger.warning("Heartbeat echo failed", exc_info=True)
                    continue
            except Exception:  # noqa: BLE001
                logger.error("WebSocket recv failed", exc_info=True)
                break

            if self._ws_debug:
                print("<-", raw)
                logger.info("WS RX %s", raw, extra={"code_path": __file__})

            buffer += raw

            # TradingView’s stream is length-prefixed. Process each frame.
            while True:
                match = re.match(r"~m~(\d+)~m~", buffer)
                if not match:
                    break

                frame_len = int(match.group(1))
                header_len = match.end()
                total_len = header_len + frame_len

                if len(buffer) < total_len:
                    # Wait for more data
                    break

                payload = buffer[header_len:total_len]
                buffer = buffer[total_len:]

                self._handle_payload(payload)

    # ---- Message parsing -------------------------------------------

    _re_tick = re.compile(
        r"qsd\.*?\"lp\":(?P<price>[0-9.]+).*?\"volume\":(?P<vol>[0-9.]+).*?\"upd\":(?P<ts>\d+)"
    )

    def _handle_payload(self, payload: str):
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            # Not JSON? Some ping/pong or control string -> ignore
            return

        if not isinstance(msg, dict) or "m" not in msg:
            return

        method = msg["m"]
        params = msg.get("p", [])

        if method == "qsd":  # quote symbol data – tick updates
            # We can’t rely on exact structure; quick regex fallback.
            m = self._re_tick.search(payload)
            if m:
                price = float(m.group("price"))
                vol = float(m.group("vol"))
                ts = datetime.fromtimestamp(int(m.group("ts")) / 1000, tz=timezone.utc)
                event = {"type": "tick", "price": price, "volume": vol, "ts": ts}
                self._q.put(event)

        elif method == "series_completed":
            sub_key = params[1] if len(params) > 1 else ""
            self._q.put({"type": "bar", "sub": sub_key, "status": "completed"})

        elif method == "du":  # data update (partial candles & closed bars)
            # params shape: [series_id, [[<list-of-values>], …]]
            if len(params) < 2:
                return

            series_id = params[0]
            bars = params[1]
            for bar_data in bars:
                # TradingView bar format: [ts, open, high, low, close, volume]
                if len(bar_data) < 6:
                    continue
                ts_epoch = bar_data[0] / 1000 if bar_data[0] > 1e12 else bar_data[0]
                ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

                event = {
                    "type": "bar",
                    "sub": series_id,
                    "ts": ts,
                    "open": bar_data[1],
                    "high": bar_data[2],
                    "low": bar_data[3],
                    "close": bar_data[4],
                    "volume": bar_data[5],
                    "closed": bar_data[6] if len(bar_data) > 6 else False,
                }
                self._q.put(event)

        # else: ignore others (ping, etc.)
