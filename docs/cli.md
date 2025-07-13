# tvws command-line interface

The `tvws` tool wraps the low-level WebSocket client.

## Global options

- `--origin` – sets the `Origin` header used during the handshake.
  Default: `https://www.tradingview.com`.

Example: tvws stream --origin https://foo.bar --symbol BINANCE:BTCUSDT

## Commands

### history

```bash
tvws history SYMBOL INTERVAL N_BARS [OPTIONS]
```

Fetch historical bars for a symbol/interval and emit JSON lines. Exits with code 1 on timeout.

Options:
  - `-d`, `--debug`: print raw websocket frames for troubleshooting.

### stream

```bash
tvws stream -s SYMBOL -s SYMBOL -i INTERVAL [--init-bars N] [--debug]
```

Stream real-time ticks and bar updates to stdout (JSON lines).

### candles live

```bash
tvws candles live SYMBOL INTERVAL [--debug]
```

Stream candle updates using TradingView chart sessions.

### candles hist

```bash
tvws candles hist SYMBOL INTERVAL [--limit N]
```

Fetch historic candles and display a Rich table (or plain text if Rich is unavailable).
