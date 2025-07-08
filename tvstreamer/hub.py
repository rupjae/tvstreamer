"""In-memory pub-sub hubs for Tick and Candle events.

``CandleHub`` and ``TickHub`` provide a lightweight broadcast mechanism using
``anyio`` memory streams.  Each subscriber gets an independent queue so slow
consumers do not block fast ones.  ``publish`` is non-blocking and will drop an
item when a subscriber's queue is full, emitting a TRACE log for observability.
"""

from __future__ import annotations

import anyio
from anyio.streams.memory import (
    MemoryObjectReceiveStream,
    MemoryObjectSendStream,
)
import logging
from typing import Generic, Set, TypeVar

from .events import Tick
from .models import Candle
from .logging_utils import TRACE_LEVEL

__all__ = ["TickHub", "CandleHub"]

T = TypeVar("T")


logger = logging.getLogger(__name__)


class _Hub(Generic[T]):
    """Generic in-memory broadcast hub."""

    def __init__(self, maxsize: int = 0) -> None:
        self._maxsize = maxsize
        self._subs: Set[MemoryObjectSendStream[T]] = set()

    def subscribe(self) -> MemoryObjectReceiveStream[T]:
        """Return a receive stream for published items."""
        send, recv = anyio.create_memory_object_stream[T](self._maxsize)
        self._subs.add(send)
        return recv

    async def publish(self, item: T) -> None:
        """Broadcast ``item`` to all subscribers.

        The call is non-blocking; if a subscriber backlog is full the item is
        dropped and a TRACE log records the event.
        """
        for send in list(self._subs):
            try:
                send.send_nowait(item)
            except anyio.WouldBlock:
                logger.log(
                    TRACE_LEVEL,
                    "drop item: subscriber backlog full",
                    extra={"code_path": __name__},
                )
            except Exception:
                self._subs.discard(send)
                await send.aclose()

    async def aclose(self) -> None:
        """Close all subscriber streams."""
        for send in list(self._subs):
            await send.aclose()
        self._subs.clear()

    @property
    def metrics(self) -> dict[str, int]:
        """Return observability metrics."""
        qlen = sum(s.statistics().current_buffer_used for s in self._subs)
        return {"queue_len": qlen}


class TickHub(_Hub[Tick]):
    """In-memory hub for :class:`Tick` events."""


class CandleHub(_Hub[Candle]):
    """In-memory hub for :class:`Candle` events.

    Example
    -------
    >>> hub = CandleHub(maxsize=10)
    >>> recv = hub.subscribe()
    >>> await hub.publish(candle)
    >>> await recv.receive()
    """
