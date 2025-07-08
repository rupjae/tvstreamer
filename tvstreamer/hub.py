"""In-memory pub-sub hubs for Tick and Candle events."""

from __future__ import annotations

import anyio
from anyio.streams.memory import (
    MemoryObjectReceiveStream,
    MemoryObjectSendStream,
)
from typing import Generic, Set, TypeVar

from .events import Tick
from .models import Candle

__all__ = ["TickHub", "CandleHub"]

T = TypeVar("T")


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
        """Broadcast *item* to all subscribers, dropping on overflow."""
        for send in list(self._subs):
            try:
                send.send_nowait(item)
            except anyio.WouldBlock:
                # Drop item when subscriber backlog is full
                pass
            except Exception:
                self._subs.discard(send)
                await send.aclose()

    async def aclose(self) -> None:
        """Close all subscriber streams."""
        for send in list(self._subs):
            await send.aclose()
        self._subs.clear()

    @property
    def metrics(self) -> int:
        """Return total queued items across subscribers."""
        return sum(s.statistics().current_buffer_used for s in self._subs)


class TickHub(_Hub[Tick]):
    """In-memory hub for :class:`Tick` events."""


class CandleHub(_Hub[Candle]):
    """In-memory hub for :class:`Candle` events."""
