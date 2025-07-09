from __future__ import annotations

import os
import socket

import anyio
import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_candles_live_smoke(tmp_path) -> None:
    try:
        sock = socket.create_connection(("data.tradingview.com", 443), timeout=2)
        sock.close()
    except OSError:
        pytest.xfail("network unavailable")

    cmd = [
        "python",
        "-m",
        "tvstreamer.cli",
        "candles",
        "live",
        "--symbol",
        "AAPL",
        "--interval",
        "1m",
    ]
    process = await anyio.open_process(
        cmd, stdout=anyio.subprocess.PIPE, stderr=anyio.subprocess.PIPE
    )
    async with anyio.move_on_after(5):
        await process.wait()
    if process.returncode is None:
        process.terminate()
        await process.wait()
    stderr = (await process.stderr.receive()).decode()
    stdout = (await process.stdout.receive()).decode()
    assert "protocol_error" not in stderr
    assert "|" in stdout
