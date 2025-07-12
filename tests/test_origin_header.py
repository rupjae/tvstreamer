"""Test that TvWSClient.connect uses the DEFAULT_ORIGIN header."""

from typing import Dict, Optional

from tvstreamer.wsclient import create_connection, TvWSClient
from tvstreamer.constants import DEFAULT_ORIGIN
import tvstreamer.constants as const


def test_origin_header(monkeypatch):
    # Intercept create_connection to capture the origin argument
    captured: Dict[str, Optional[str]] = {}

    monkeypatch.setattr(const, "DEFAULT_ORIGIN", const.DEFAULT_ORIGIN)

    def fake_create_connection(
        endpoint: str, timeout: int = 7, origin: Optional[str] = None, header=None
    ):
        captured["origin"] = origin

        class DummyWS:
            def send(self, *args, **kwargs):
                pass

            def close(self):
                pass

        return DummyWS()

    # Patch the wsclient.create_connection function to our fake implementation
    monkeypatch.setattr(
        "tvstreamer.wsclient.create_connection",
        fake_create_connection,
    )
    # Skip handshake/subscriptions to avoid network operations
    monkeypatch.setattr(TvWSClient, "_handshake", lambda self: None)
    monkeypatch.setattr(TvWSClient, "_subscribe_all", lambda self: None)

    client = TvWSClient([])
    client.connect()
    client.close()

    assert captured.get("origin") == DEFAULT_ORIGIN
