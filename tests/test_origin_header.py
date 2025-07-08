try:
    import websockets
except ModuleNotFoundError:
    import pytest

    pytest.skip("websockets package required", allow_module_level=True)

import anyio
from tvstreamer.wsclient import TvWSClient
from tvstreamer.constants import DEFAULT_ORIGIN


headers: list[str] = []


async def _handler(ws):
    headers.append(ws.request_headers.get("Origin"))
    await ws.close()


def test_origin_header(monkeypatch):
    global headers
    headers = []

    async def main():
        async with websockets.serve(_handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(TvWSClient, "WS_ENDPOINT", f"ws://127.0.0.1:{port}")
            client = TvWSClient([])
            await anyio.to_thread.run_sync(client.connect)
            client.close()

    anyio.run(main, backend="asyncio")
    assert headers and headers[0] == DEFAULT_ORIGIN
