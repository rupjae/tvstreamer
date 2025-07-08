#!/usr/bin/env python3
"""Demo script to stream real-time market data using tvstreamer."""

from tvstreamer import TvWSClient
from tvstreamer.events import Tick, Bar


def handle_tick(event: Tick) -> None:
    """Print tick events to the console."""
    print(f"[Tick] {event.symbol} @ {event.ts} - price={event.price}, volume={event.volume}")


def handle_bar(event: Bar) -> None:
    """Print bar events (open or closed candles) to the console."""
    status = "closed" if event.closed else "open"
    print(
        f"[Bar ] {event.symbol} @ {event.ts} - o={event.open}, h={event.high}, l={event.low}, \
c={event.close}, v={event.volume}, {status}"
    )


def main() -> None:
    """Main entry point for the demo script."""
    # Subscribe to a 1-minute BTC/USDT ticker and daily MSFT bars
    subscriptions = [("BINANCE:BTCUSDT", "1")]
    print(f"Subscribing to: {', '.join(f'{s}@{i}' for s, i in subscriptions)}")
    with TvWSClient(subscriptions, n_init_bars=50) as client:
        for event in client.stream():
            if isinstance(event, Tick):
                handle_tick(event)
            elif isinstance(event, Bar):
                handle_bar(event)


if __name__ == "__main__":
    main()
