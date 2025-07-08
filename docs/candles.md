# Live and historic candles

The library offers high-level helpers around candle data so you don't
have to decode TradingView frames yourself.

## API overview

- `CandleHub` – lightweight pub/sub queue for forwarding events to many
  consumers.
- `CandleStream` – async wrapper that connects to TradingView and
  publishes `Candle` objects through a hub.
- `get_historic_candles(symbol, interval, limit=500, *, timeout=10.0)` –
  fetch a list of closed candles. Results are cached for 60 seconds and
  no more than three concurrent sessions are opened.

## Intervals

TradingView accepts the following resolution codes:

```
1, 3, 5, 15, 30, 60, 120, 240, D, W, M
```

Aliases such as `5m`, `1h`, `1d` and `1w` are also recognised.

## Performance tips

- Reuse a single `CandleStream` for multiple consumers by sharing its
  hub.
- Historical fetches hit an in-memory cache; avoid spamming the API in a
  tight loop.
- The stream automatically reconnects with exponential backoff if the
  websocket drops.

### CLI examples

```bash
$ tvws candles live --symbol BINANCE:BTCUSDT --interval 5m
$ tvws candles hist --symbol BINANCE:BTCUSDT --interval 1h --limit 100
```
