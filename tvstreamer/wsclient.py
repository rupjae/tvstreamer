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
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Tuple

# Heavy dependency; we import lazily to allow docs / type-checking without runtime package.
# ruff: noqa: I001
try:
    from websocket import create_connection, WebSocket
except ModuleNotFoundError:  # pragma: no cover
    # Stub fallback so that type hints work in editor; actual runtime failure will
    # occur when *connect()* is called if dependency missing.
    WebSocket = object

    def create_connection(*_a: Any, **_kw: Any):
        raise ModuleNotFoundError("websocket-client package is required for TvWSClient")


logger = logging.getLogger(__name__)

# Typed events and buffer
from tvstreamer.events import BaseEvent, Tick, Bar, BarBuffer

# ---------------------------------------------------------------------------
# Helper data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
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
    """Synchronous TradingView WebSocket client.

    The class hides all the *wire-protocol* ceremony required to speak to
    TradingView’s private WebSocket endpoint and exposes a **very** small
    surface to user space:

    • :meth:`connect` – open the socket and start the background reader.
    • :meth:`stream` – iterate over parsed *tick* / *bar* events.
    • :meth:`close`  – shut everything down.

    Example
    -------
    ```python
    from tvstreamer import TvWSClient
    from tvstreamer.events import Tick, Bar

    client = TvWSClient(
        [("BINANCE:BTCUSDT", "1"), ("NYSE:MSFT", "1D")],
        n_init_bars=500,
    )

    client.connect()
    for event in client.stream():
        if isinstance(event, Tick):
            handle_tick(event)
        elif isinstance(event, Bar):
            handle_bar(event)
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
    ) -> None:
        """Create a new websocket client instance.

        Args:
            subscriptions: List of ``(symbol, interval)`` tuples where
                *symbol* is the TradingView identifier (e.g. ``"BINANCE:BTCUSDT"``)
                and *interval* is the internal resolution code (``"1"``, ``"1D"`` …).
            n_init_bars: How many historical bars TradingView should return right
                after subscribing. ``None`` or ``<=0`` falls back to ``300`` – the
                smallest value TradingView accepts.
            token: Authentication token extracted from the TradingView website.
                For anonymous users the hard-coded ``"unauthorized_user_token"``
                works fine.
            ws_debug: When *True*, raw websocket frames are echoed both to
                ``stdout`` **and** the structured log, which is helpful when
                reverse-engineering protocol changes.
        """
        self._subs: List[Subscription] = [Subscription(sym, tf) for sym, tf in subscriptions]
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
        self._q: "queue.Queue[BaseEvent|Dict[str, Any]]" = queue.Queue()

        # Background read thread
        self._rx_thread: threading.Thread | None = None
        # Internal buffer of bars and mapping for subscriptions
        self._buffer: BarBuffer = BarBuffer(self._n_init_bars)
        self._series: Dict[str, Subscription] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self):
        """Open the WebSocket connection and spin up the reader thread.

        Raises:
            RuntimeError: If the client is already connected.
        """

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

    def stream(self) -> Generator[BaseEvent | Dict[str, Any], None, None]:
        """Iterate over typed events coming from the background thread.

        Yields:
            BaseEvent | dict: Either a typed Tick/Bar event or a status dict.

        The generator blocks until :meth:`close` is invoked **and** the internal
        queue is drained, making it safe to use in ``for`` loops without
        additional shutdown bookkeeping.
        """

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
        """Prefix a raw TradingView payload with the length header."""

        return f"~m~{len(payload)}~m~{payload}"

    def _construct_msg(self, func: str, params: List[Any]) -> str:
        """Return a compact JSON-encoded TradingView message body."""

        return json.dumps({"m": func, "p": params}, separators=(",", ":"))

    def _send(self, func: str, params: List[Any]) -> None:
        """Send a single protocol frame over the underlying websocket."""

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

    def _handshake(self) -> None:
        """Perform the initial authentication / session negotiation."""

        self._send("set_auth_token", [self._token])
        self._send("chart_create_session", [self._chart_session])
        self._send("quote_create_session", [self._quote_session])
        self._send("quote_set_fields", [self._quote_session, "lp", "volume", "ch"])

        # NB: we do *not* set quote_set_fields – client may do so later if desired.

    def _subscribe_all(self) -> None:
        for sub in self._subs:
            self._subscribe(sub)

    def _subscribe(self, sub: Subscription) -> None:
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
        # track mapping from series id to subscription metadata
        self._series[series_id] = sub

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

    def _reader_loop(self) -> None:
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

    def _handle_payload(self, payload: str) -> None:
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
            # Typed Tick events: parse symbol, price, volume, timestamp
            symbol = None
            price = None
            volume = None
            ts = None
            if len(params) > 1 and isinstance(params[1], dict):
                info = params[1]
                symbol = info.get("n")
                v = info.get("v", {})
                price = float(v.get("lp", 0.0))
                volume = float(v.get("volume", 0.0))
                # prefer timestamp from payload if present, else fallback to regex
                ts_ms = v.get("upd")
                if ts_ms:
                    ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
                else:
                    m = self._re_tick.search(payload)
                    if m:
                        ts = datetime.fromtimestamp(int(m.group("ts")) / 1000, tz=timezone.utc)
            # Fallback to root-level fields for payloads with direct lp/volume/upd keys
            if price is None and "lp" in msg:
                price = float(msg.get("lp", 0.0))
                volume = float(msg.get("volume", 0.0))
                upd_val = msg.get("upd")
                if upd_val:
                    ts = datetime.fromtimestamp(int(upd_val) / 1000, tz=timezone.utc)
                else:
                    m2 = self._re_tick.search(payload)
                    if m2:
                        ts = datetime.fromtimestamp(int(m2.group("ts")) / 1000, tz=timezone.utc)

            if price is not None and volume is not None and ts is not None:
                # Determine symbol if available, default to empty string
                sym = symbol or msg.get("n", "")
                tick = Tick(ts=ts, price=price, volume=volume, symbol=sym)
                self._q.put(tick)

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
                # bar format: [ts, open, high, low, close, volume, closed?]
                if len(bar_data) < 6:
                    continue
                ts_epoch = bar_data[0] / 1000 if bar_data[0] > 1e12 else bar_data[0]
                ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
                sub = self._series.get(series_id)
                if sub is None:
                    continue

                closed = bool(bar_data[6]) if len(bar_data) > 6 else False
                bar = Bar(
                    ts=ts,
                    open=bar_data[1],
                    high=bar_data[2],
                    low=bar_data[3],
                    close=bar_data[4],
                    volume=bar_data[5],
                    symbol=sub.symbol,
                    interval=sub.interval,
                    closed=closed,
                )
                # store in internal buffer and emit typed Bar
                self._buffer.append(bar)
                self._q.put(bar)

        # else: ignore others (ping, etc.)

    def _fetch_history(self, symbol: str, interval: str, n_bars: int) -> list[Bar]:
        """Internal: send history_get frames, collect up to n_bars, and wait for completion.

        Raises:
            TimeoutError: if no completion event arrives within timeout.
        """
        logger = logging.getLogger(__name__)
        sub = Subscription(symbol, interval)
        alias = sub.key()
        series_id = f"s{random.randint(1_000, 9_999)}"
        self._series[series_id] = sub

        sym_up = symbol.upper()
        logger.debug(
            "Requesting %d history bars for %s %s",
            n_bars,
            symbol,
            interval,
            extra={"code_path": __file__},
        )
        # resolve and subscribe for history bars
        self._send("quote_add_symbols", [self._quote_session, sym_up])
        desc = f'{{"symbol":"{sym_up}","adjustment":"splits"}}'
        self._send("resolve_symbol", [self._chart_session, alias, desc])
        self._send(
            "create_series",
            [
                self._chart_session,
                series_id,
                series_id,
                alias,
                interval,
                max(1, n_bars),
                "",
            ],
        )

        bars: list[Bar] = []
        completed = False
        deadline = time.monotonic() + max(5.0, 0.1 * n_bars)
        while not completed and len(bars) < n_bars:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # clean up series mapping
                self._series.pop(series_id, None)
                logger.warning(
                    "Timeout fetching history for %s %s",
                    symbol,
                    interval,
                    extra={"code_path": __file__},
                )
                raise TimeoutError(f"History fetch timeout for {symbol}:{interval}")
            try:
                evt = self._q.get(timeout=remaining)
            except queue.Empty:
                continue
            if isinstance(evt, Bar) and evt.symbol == symbol and evt.interval == interval:
                bars.append(evt)
            elif (
                isinstance(evt, dict)
                and evt.get("type") == "bar"
                and evt.get("sub") == alias
                and evt.get("status") == "completed"
            ):
                completed = True

        # clean up series mapping
        self._series.pop(series_id, None)
        logger.debug(
            "Fetched %d history bars for %s %s",
            len(bars),
            symbol,
            interval,
            extra={"code_path": __file__},
        )
        return bars

    def get_history(self, symbol: str, interval: str, n_bars: int) -> list[Bar]:
        """
        Fetch historical bars synchronously (with its own queue to isolate from live stream).

        Args:
            symbol: TradingView symbol (exchange:SYMBOL).
            interval: Resolution code (e.g. '1', '1D').
            n_bars: Number of bars to fetch.

        Returns:
            List[Bar]: Historical bars collected.

        Raises:
            TimeoutError: If no completion event is received in time.
        """
        own_conn = False
        if self._ws is None:
            self.connect()
            own_conn = True
        old_q = self._q
        self._q = queue.Queue()
        try:
            return self._fetch_history(symbol, interval, n_bars)
        finally:
            self._q = old_q
            if own_conn:
                self.close()
