import asyncio
import anyio
import pytest
import websockets

from tvstreamer.wsclient import TvWSClient
from tvstreamer.constants import DEFAULT_ORIGIN


def test_origin_header(monkeypatch):
    """Ensure that TvWSClient.connect sends the DEFAULT_ORIGIN header."""
    headers: list[str] = []

    async def main():
        # synchronization event for server handler
        ev = asyncio.Event()

        async def _handler(ws):
            headers.append(ws.request_headers.get("Origin"))
            ev.set()
            await ws.close()

        async with websockets.serve(_handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(TvWSClient, "WS_ENDPOINT", f"ws://127.0.0.1:{port}")
            client = TvWSClient([])
            await anyio.to_thread.run_sync(client.connect)
            client.close()
            # await handler to record the Origin header
            await asyncio.wait_for(ev.wait(), timeout=1)

    anyio.run(main, backend="asyncio")
    assert headers and headers[0] == DEFAULT_ORIGIN
