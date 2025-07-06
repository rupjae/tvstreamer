tvstreamer – TradingView WebSocket client & mini-CLI
====================================================

tvstreamer is a **tiny, dependency-light** helper library that lets you stream
real-time market data from [TradingView]’s *undocumented* WebSocket endpoint
with just a handful of lines:

```python
from tvstreamer import TvWSClient

# Subscribe to BTC/USDT 1-minute candles **and** MSFT daily bars
subs = [
    ("BINANCE:BTCUSDT", "1"),   # 1-minute resolution
    ("NYSE:MSFT",       "1D"),  # 1-day   resolution
]

with TvWSClient(subs, n_init_bars=500) as client:
    for event in client.stream():
        match event["type"]:
            case "tick":
                handle_tick(event)
            case "bar":
                handle_bar(event)
```

Or directly from the command-line:

```bash
$ tvws -s BINANCE:BTCUSDT -s NYSE:MSFT -i 1D \
      | jq '.'   # pretty-print the JSON stream
```

> **Heads-up** ─ TradingView has no public, officially supported streaming API.
> This project reverse-engineers the WebSocket contract observed in the web
> application. End-points or message formats may break at any time without
> warning.


Why another TradingView client?
-------------------------------

* **One file, one purpose.** The public surface is purposefully minimal – a
  single `TvWSClient` class and a matching `tvws` CLI wrapper.
* **Zero async complexity.** The client runs synchronously and can therefore be
  dropped into a background thread or process of your choosing.
* **Lean dependency tree.** Only [`websocket-client`] (runtime) and *optionally*
  [`typer`] (rich CLI) are required.
* **Structured logging out of the box.** `configure_logging()` follows the
  project-wide guidelines and writes coloured **Rich** console output *plus*
  rotating `.log` and `.jsonl` files under `logs/`.


Installation
------------

```bash
# PyPI (recommended)
pip install tvstreamer

# From source – editable for local development
git clone https://example.com/your-fork/tvstreamer.git
cd tvstreamer
pip install -e .[dev]
```

Requirements
~~~~~~~~~~~~

* Python 3.8+
* [`websocket-client` ≥ 0.57.0]

The CLI gains additional niceties (command completion, coloured help) when
[`typer` ≥ 0.9] is present, but will gracefully fall back to `argparse` if the
dependency is missing.


Usage
-----

### Library

```python
from tvstreamer import TvWSClient

client = TvWSClient([("BINANCE:BTCUSDT", "1")], n_init_bars=300)
client.connect()

for ev in client.stream():
    if ev["type"] == "tick":
        print("last price:", ev["price"])
    elif ev["type"] == "bar" and ev.get("closed"):
        print("closed candle at", ev["ts"], "close=", ev["close"])
```

Close the connection with `client.close()` or simply use a `with` context as
shown earlier.

### Command-line

```bash
# Subscribe to two symbols, show raw frames for debug purposes
tvws -s BINANCE:ETHUSDT -s BINANCE:BTCUSDT -i 5 -d

# Fetch initial history (500 candles) then continue streaming
tvws -s NYSE:MSFT -i 1D -n 500 | tee msft.jsonl
```

Run `tvws --help` for the full list of options.


Logging
-------

Importing `tvstreamer` automatically installs the default logging configuration
*unless* the host application has already set up handlers.  You can adjust the
behaviour manually:

```python
from tvstreamer import configure_logging

# Enable TRACE level and limit noisy modules to DEBUG
configure_logging(debug=True, debug_module="tvstreamer.wsclient")
```

The helper returns the paths of the freshly created `.log` and `.jsonl` files
so they can be attached to test artefacts, S3 uploads, etc.


Development
-----------

* Clone your fork and install **dev** extras (`pip install -e .[dev]`).
* Run the test-suite: `pytest -q`.
* Apply the pre-commit hooks before pushing: `pre-commit run -a`.

Pull requests must ship unit tests for new features and keep `ruff`/`black`
clean.


License
-------

This project is licensed under the MIT License – see `LICENSE` for details.


[TradingView]: https://www.tradingview.com/
[`websocket-client`]: https://pypi.org/project/websocket-client/
[`typer`]: https://pypi.org/project/typer/
