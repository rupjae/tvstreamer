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

### Version bumps

Need to publish a new release?  Run the helper:

```bash
./scripts/bump_version.sh patch   # or minor / major / <exact>
```

The script:

1. Updates *pyproject.toml* via `poetry version` (or a fallback if Poetry is
   unavailable).
2. Inserts a new dated section into `CHANGELOG.md` right below the **Unreleased** header.

This keeps the runtime `tvstreamer.__version__` (resolved at import-time via
`importlib.metadata`) in lock-step with the package metadata.


Project Architecture (Bird’s-eye view)
--------------------------------------

👉 *Looking for a deeper dive?* Check out
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the complete module-level
break-down.

```text
               ┌───────────┐      imports       ┌────────────┐
               │ tvstreamer│  ────────────────► │ logging_utils │
               │  facade   │                    └────────────┘
               │ (__init__)│
               ▼                           (handles TRACE, Rich console,
      ┌──────────────┐                       rotating .log/.jsonl files)
      │  wsclient    │
      │ (domain)     │ ◄───────────────────────┐
      └──────────────┘                         │ structured events
                                               │
        ▲  JSON lines                          │
        │  stdout                              │
        │                                      │ logging records
   ┌──────────┐   CLI calls  ┌─────────┐       ▼
   │   User   │ ───────────► │  cli    │──► Rich console / files / JSONL
   │ scripts  │              └─────────┘
   └──────────┘
```

• The **facade** re-exports only three symbols: `TvWSClient`,
  `configure_logging`, and `trace`.  Everything else is internal.
• A **single synchronous** websocket connection suffices – no async machinery
  required.  If you need async, run the client in a background thread or wrap
  it with `anyio.to_thread.run_sync()`.
• The CLI keeps zero runtime dependencies when `typer` is not available thanks
  to the `argparse` fallback implemented inside `tvstreamer.cli`.

Logging Example
---------------

```python
from tvstreamer import configure_logging

# Enable finest-grained TRACE level globally and raise wsclient to DEBUG only
configure_logging(debug=True, debug_module="tvstreamer.wsclient")

import tvstreamer

with tvstreamer.TvWSClient([("BINANCE:BTCUSDT", "1")]) as c:
    for ev in c.stream():
        print(ev)
```

This will emit colourised logs to the terminal *and* create timestamped log
files under `logs/`, each with a matching `.jsonl` mirror ready for ingestion
into ELK, Splunk, or your data-warehouse of choice.


License
-------

This project is licensed under the MIT License – see `LICENSE` for details.


[TradingView]: https://www.tradingview.com/
[`websocket-client`]: https://pypi.org/project/websocket-client/
[`typer`]: https://pypi.org/project/typer/
