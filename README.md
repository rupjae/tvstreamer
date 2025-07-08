# tvstreamer

Modern TradingView WebSocket client & CLI toolkit.

<!-- CI status -->
[![CI status](https://github.com/rupjae/tvstreamer/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rupjae/tvstreamer/actions/workflows/ci.yml)

<!-- Codecov coverage -->
[![codecov](https://codecov.io/gh/rupjae/tvstreamer/branch/main/graph/badge.svg)](https://codecov.io/gh/rupjae/tvstreamer)


tvstreamer is a **tiny, dependency-light** helper library that lets you stream
real-time market data from [TradingView]’s *undocumented* WebSocket endpoint.

<!-- TOC -->
- [Quick Start](#quick-start)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Logging](#logging)
- [Development](#development)
- [Project Architecture](#project-architecture-birds-eye-view)
- [FAQ](#faq)
- [License](#license)
<!-- /TOC -->

### Quick start

Start streaming market data in seconds:

```python
from tvstreamer import TvWSClient
from tvstreamer.events import Tick, Bar

# Subscribe to BTC/USDT 1-minute candles **and** MSFT daily bars
subs = [
    ("BINANCE:BTCUSDT", "1"),   # 1-minute resolution
    ("NYSE:MSFT",       "1D"),  # 1-day   resolution
]

with TvWSClient(subs, n_init_bars=500) as client:
    for event in client.stream():
        if isinstance(event, Tick):
            handle_tick(event)
        elif isinstance(event, Bar):
            handle_bar(event)
```

#### Candle utilities

```python
import anyio
import websockets
from tvstreamer import CandleStream, get_historic_candles

async def live() -> None:
    async with CandleStream(websockets.connect, [("BINANCE:BTCUSDT", "5m")]) as cs:
        async for c in cs.subscribe():
            print(c.close)

async def hist() -> None:
    data = await get_historic_candles("BINANCE:BTCUSDT", "1h", limit=100)
    print(data[-1].close)

anyio.run(live)
anyio.run(hist)
```

### CLI quick demo

```bash
$ tvws -s BINANCE:BTCUSDT -s NYSE:MSFT -i 1D \
      | jq '.'   # pretty-print the JSON stream
```

> **Heads-up** ─ TradingView has no public, officially supported streaming API.
> This project reverse-engineers the WebSocket contract observed in the web
> application. End-points or message formats may break at any time without
> warning.


Features
--------

* **One file, one purpose.** The public surface is purposefully minimal - a
  single `TvWSClient` class and a matching `tvws` CLI wrapper.
* **Zero async complexity.** The client runs synchronously and can therefore be dropped into a background thread or process of your choosing.
* **Lean dependency tree.** Only [`websocket-client`] (runtime) and *optionally* [`typer`] (rich CLI) are required.
* **Structured logging out of the box.** `configure_logging()` follows the project-wide guidelines and writes coloured **Rich** console output *plus* rotating `.log` and `.jsonl` files under `logs/`.


Installation
------------

```bash
# PyPI (recommended)
pip install tvstreamer
pip install tvstreamer[cli]

# Candle streaming commands require the optional `websockets` dependency
# installed via the `[cli]` extra:
#
#     pip install tvstreamer[cli]

# From source - editable for local development
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
from tvstreamer.events import Tick, Bar

client = TvWSClient([("BINANCE:BTCUSDT", "1")], n_init_bars=300)
client.connect()

for ev in client.stream():
    if isinstance(ev, Tick):
        print("last price:", ev.price)
    elif isinstance(ev, Bar) and ev.closed:
        print("closed candle at", ev.ts, "close=", ev.close)
```

Close the connection with `client.close()` or simply use a `with` context as
shown earlier.

### Streaming Facade

The `StreamRouter` offers iterator-based filtering and callback subscriptions
on top of `TvWSClient`. It supports graceful shutdown via context manager
and back-pressure via bounded queues.

```python
from tvstreamer import StreamRouter
from tvstreamer.events import Tick, Bar

subs = [("BINANCE:BTCUSDT", "1"), ("NYSE:MSFT", "1D")]
with StreamRouter(subs) as router:
    # Iterate only closed bars for BTCUSDT @1m
    for bar in router.iter_closed_bars(("BINANCE:BTCUSDT", "1")):
        print("closed bar:", bar)

    # Subscribe to ticks for MSFT@1D via callback
    def on_tick(evt: Tick) -> None:
        print("tick event:", evt)

    router.subscribe(("NYSE:MSFT", "1D"), on_event=on_tick, tick=True)
```

See the low-level `TvWSClient` example above for direct generator-based access to events if you need finer control.

### In-memory hubs

`CandleHub` and `TickHub` let you broadcast events to multiple consumers in the
same process.  Calls to ``publish`` are non-blocking; if a subscriber queue is
full the event is dropped and a TRACE log is emitted.

```python
from tvstreamer import CandleHub

hub = CandleHub(maxsize=100)
recv = hub.subscribe()
await hub.publish(candle)
latest = await recv.receive()
```

### CandleStream

`CandleStream` asynchronously forwards decoded candles through a hub so multiple
consumers can share a single websocket connection.

```python
import anyio
from tvstreamer import CandleHub, CandleStream

async def connect():
    ...  # return an ``async with`` websocket connection

async def main() -> None:
    hub = CandleHub()
    async with CandleStream(connect, [("BINANCE:BTCUSDT", "1m")], hub=hub) as cs:
        async for candle in cs.subscribe():
            print(candle.close)

anyio.run(main)
```

### Command-line

```bash
```bash
# Subscribe to two symbols, show raw frames for debug purposes
	tvws -s BINANCE:ETHUSDT -s BINANCE:BTCUSDT -i 5 -d

# Fetch historical bars snapshot for a symbol (no live stream)
        tvws history BINANCE:BTCUSDT 1 100

# Fetch initial history (500 candles) then continue streaming
        tvws -s NYSE:MSFT -i 1D -n 500 | tee msft.jsonl

# Stream BTC/USDT 5‑minute candle closes
        tvws candles live --symbol BINANCE:BTCUSDT --interval 5m

# Fetch last 100 NVDA hourly candles as a table
        tvws candles hist --symbol NASDAQ:NVDA --interval 1h --limit 100
        # install 'rich' for coloured table output
```

`tvws stream` and `tvws history` output valid line-delimited JSON for easy
piping into scripts or tools like `jq`.

Run `tvws --help` for the full list of options.

## Demo application

A simple demo script is available at `examples/demo_stream.py`. Run:

```bash
python examples/demo_stream.py
```

It subscribes to BTC/USDT (1-minute) and MSFT (1-day) and prints Tick and Bar events to the console.

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

The GitHub Actions workflow caches dependencies, tests on Python 3.9–3.11,
enforces `mypy --strict`, runs `pip-audit`, and uploads coverage to
Codecov.

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
• A **single synchronous** websocket connection suffices - no async machinery
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

FAQ
---

### Why do I get 403?

TradingView rejects WebSocket handshakes without an `Origin` header. The
library sends `https://www.tradingview.com` by default; override it with
`--origin` if needed.


License
-------

This project is licensed under the MIT License - see `LICENSE` for details.


[TradingView]: https://www.tradingview.com/
[`websocket-client`]: https://pypi.org/project/websocket-client/
[`typer`]: https://pypi.org/project/typer/
