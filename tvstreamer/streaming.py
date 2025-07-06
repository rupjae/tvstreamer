"""
High-level synchronous streaming facade wrapping TvWSClient.

This module provides StreamRouter, which dispatches Tick and Bar events
to iterator-based consumers or callback subscribers with back-pressure support.
"""

from __future__ import annotations

import logging
import threading
import queue
from typing import Any, Callable, Iterator, List, Optional, Set, Tuple

from tvstreamer.events import BaseEvent, Tick, Bar
from tvstreamer.logging_utils import trace
from tvstreamer.wsclient import TvWSClient


logger = logging.getLogger(__name__)

__all__ = ["StreamRouter"]


class StreamRouter:
    """
    Streaming router providing filtering iterators and callback subscriptions.

    The dispatcher thread starts lazily on first iterator or subscribe() call.

    Example
    -------
    >>> from tvstreamer.streaming import StreamRouter
    >>> subs = [("BINANCE:BTCUSDT", "1")]
    >>> with StreamRouter(subs) as router:
    ...     for bar in router.iter_closed_bars(("BINANCE:BTCUSDT", "1")):
    ...         print(bar)
    """

    def __init__(
        self,
        subscriptions: List[Tuple[str, str]],
        queue_maxsize: int = 1,
    ) -> None:
        """
        Initialize router with underlying subscriptions.

        Args:
            subscriptions: list of (symbol, interval) pairs to subscribe.
            queue_maxsize: max size for internal event queues; put() blocks when full.
        """
        self._client = TvWSClient(subscriptions)
        self._queue_size = queue_maxsize
        self._lock = threading.Lock()
        self._consumers: List[dict[str, Any]] = []
        self._callbacks: List[dict[str, Any]] = []
        self._dispatch_thread: Optional[threading.Thread] = None

    def __enter__(self) -> StreamRouter:
        self._client.connect()
        logger.info(
            "StreamRouter connected; dispatcher will start on first consumer",
            extra={"code_path": f"{__name__}.StreamRouter.__enter__"},
        )
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        if self._dispatch_thread:
            self._dispatch_thread.join()
        self._client.close()
        logger.info(
            "StreamRouter stopped", extra={"code_path": f"{__name__}.StreamRouter.__exit__"}
        )

    def _start_dispatch(self) -> None:
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            daemon=True,
            name="streamrouter-dispatch",
        )
        self._dispatch_thread.start()

    @trace
    def _dispatch_loop(self) -> None:
        for event in self._client.stream():
            # iterator consumers
            with self._lock:
                for cons in list(self._consumers):  # copy for thread-safety
                    try:
                        if cons["type"] == "tick" and isinstance(event, Tick):
                            if event.symbol in cons["symbols"]:
                                cons["queue"].put_nowait(event)
                        elif cons["type"] == "bar" and isinstance(event, Bar):
                            key = (event.symbol, event.interval)
                            if event.closed and key in cons["pairs"]:
                                cons["queue"].put_nowait(event)
                    except queue.Full:
                        logger.warning(
                            "Dropping event: consumer queue is full",
                            extra={"code_path": f"{__name__}._dispatch_loop"},
                        )
            # callbacks
            for cb in list(self._callbacks):
                try:
                    if (
                        not cb.get("tick")
                        and isinstance(event, Bar)
                        and event.closed
                        and (event.symbol, event.interval) == cb["pair"]
                    ):
                        cb["on_event"](event)
                    elif (
                        cb.get("tick") and isinstance(event, Tick) and event.symbol == cb["pair"][0]
                    ):
                        cb["on_event"](event)
                except Exception:
                    logger.exception(
                        "Callback error in StreamRouter",
                        extra={"code_path": f"{__name__}._dispatch_loop"},
                    )

        # signal iterators to finish once stream ends
        with self._lock:
            for cons in self._consumers:
                # Blocking put ensures sentinel is delivered
                cons["queue"].put(None)

    def iter_ticks(self, *symbols: str) -> Iterator[Tick]:
        """
        Iterate over Tick events for given symbols.

        Yields:
            Tick
        """
        q: queue.Queue[Optional[Tick]] = queue.Queue(maxsize=self._queue_size)
        cons = {"type": "tick", "symbols": set(symbols), "queue": q}
        with self._lock:
            self._consumers.append(cons)
            if self._dispatch_thread is None:
                self._start_dispatch()
        try:
            while True:
                evt = q.get()
                if evt is None:
                    break
                yield evt
        finally:
            with self._lock:
                self._consumers.remove(cons)

    def iter_closed_bars(self, *pairs: Tuple[str, str]) -> Iterator[Bar]:
        """
        Iterate over closed Bar events for given (symbol, interval) pairs.

        Yields:
            Bar
        """
        pairset: Set[Tuple[str, str]] = set(pairs)
        q: queue.Queue[Optional[Bar]] = queue.Queue(maxsize=self._queue_size)
        cons = {"type": "bar", "pairs": pairset, "queue": q}
        with self._lock:
            self._consumers.append(cons)
            if self._dispatch_thread is None:
                self._start_dispatch()
        try:
            while True:
                evt = q.get()
                if evt is None:
                    break
                yield evt
        finally:
            with self._lock:
                self._consumers.remove(cons)

    def subscribe(
        self,
        pair: Tuple[str, str],
        on_event: Callable[[BaseEvent], Any],
        tick: bool = False,
    ) -> Callable[[], None]:
        """
        Register a callback for Bar (and/or Tick) events for a given pair.

        Args:
            pair: (symbol, interval) tuple for Bar; Tick uses symbol only.
            on_event: callback invoked with the event.
            tick: if True, subscribe to Tick events for symbol.
        """
        cb: dict[str, Any] = {"pair": pair, "on_event": on_event}
        if tick:
            cb["tick"] = True
        with self._lock:
            self._callbacks.append(cb)
            logger.debug(
                "Subscribed callback for %s",
                pair,
                extra={"code_path": f"{__name__}.StreamRouter.subscribe"},
            )
            if self._dispatch_thread is None:
                self._start_dispatch()

        def _dispose() -> None:
            with self._lock:
                if cb in self._callbacks:
                    self._callbacks.remove(cb)
                    logger.debug(
                        "Unsubscribed callback for %s",
                        pair,
                        extra={"code_path": f"{__name__}.StreamRouter.unsubscribe"},
                    )

        return _dispose
