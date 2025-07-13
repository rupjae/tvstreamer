"""Project-wide constants for TradingView communication."""

# Allowed by TradingView as of 2025-07-13 – must match WS endpoint host to
# avoid 403 during the upgrade handshake.
DEFAULT_ORIGIN = "https://prodata.tradingview.com"

__all__ = ["DEFAULT_ORIGIN"]
