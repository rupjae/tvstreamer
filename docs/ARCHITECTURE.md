tvstreamer – Internal Architecture
=================================

The code-base is intentionally small, yet following an explicit layering helps
contributors reason about responsibilities and extend the project without
creating tight coupling.

```
                ┌───────────────────────────┐
                │       User  Code          │
                │  (scripts, notebooks)     │
                └────────────┬──────────────┘
                             │  Public API
                             ▼
                ┌───────────────────────────┐
                │   tvstreamer.__init__     │
                │ *Facade / composition*    │
                │ - TvWSClient              │
                │ - StreamRouter            │
                │ - configure_logging       │
                │ - trace decorator         │
                └────────────┬──────────────┘
                             │ imports
     ┌───────────────────────┼───────────────────┼────────────────────────┐
     │                       │                   │                        │
     ▼                       ▼                   ▼                        ▼
┌──────────────┐   ┌─────────────────┐   ┌──────────────────────┐   ┌──────────────────┐
│ logging_utils│   │    wsclient     │   │    streaming         │   │      cli         │
│  (infra)     │   │ (domain logic)  │   │ (streaming facade)   │   │ (adapter layer)  │
└─────┬────────┘   └────────┬────────┘   └────────────┬─────────┘   └────────┬─────────┘
      │                    │                         │                         │
      ▼                    ▼                         ▼                         ▼
Rich / logging      websocket-client            StreamRouter               typer/argparse
```

Layers
------

1. **Facade (\_\_init\_\_.py)** – re-exports the few *public* symbols.  Anything
   not surfaced here is considered internal and may change at any time.
2. **Infrastructure (logging_utils)** – centralises logging concerns (custom
   TRACE level, coloured console handler, rotating file + JSONL mirrors).
3. **Domain Logic (wsclient)** – synchronous WebSocket client that implements
   TradingView’s private protocol.  Exposes a simple generator-based `stream()`
   interface so that callers can decide their own concurrency model.
4. **Streaming Facade (streaming)** – `StreamRouter` wraps `TvWSClient` and
   exposes iterator and callback APIs for Tick and Bar events, with filtering,
   back-pressure support, and graceful shutdown via context manager.
   (Currently synchronous only; async variant scheduled for Work-Order #4.)
5. **Adapter Layer (cli)** – thin CLI wrapper providing both a rich Typer
   experience *and* a zero-dependency argparse fallback for constrained
   environments.

Data Flow
---------

1. `TvWSClient.stream()` yields event dictionaries (`tick` / `bar`).
2. When invoked from the CLI, events are immediately serialised as JSON lines
   on *stdout* so that UNIX pipes (e.g. `jq`, `grep`, file redirection) work
   naturally.
3. Internally, every significant action is logged.  Each log record travels
   through the root logger where `_EnsureCodePathFilter` injects the mandatory
   `code_path` field before hitting the configured handlers.

Testing Strategy
----------------

* The **public contract** is guarded by lightweight smoke tests that ensure the
  package imports, logging files are created, and the `@trace` decorator works
  as specified.
* Heavier protocol-level tests are intentionally *out of scope* for this
  repository – they would require stubbing TradingView’s backend or shipping
  large golden fixtures.

Future Extensions
-----------------

* Async wrapper around `TvWSClient` for trio/anyio projects.
* Pluggable back-pressure handling (ring buffers, bounded queues).
* Richer CLI sub-commands (snapshot, export CSV, replay streams).

This document should evolve alongside the code-base.  If you touch more than a
couple of lines in a core module, update the diagram or bullet-points so that
newcomers stay on the same page.
