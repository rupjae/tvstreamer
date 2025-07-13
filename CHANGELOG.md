# Changelog

All notable changes to this project will be documented in this file following the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Safari cookie-based auth support for `TvWSClient`.

## [0.9.3] - 2025-07-13
### Fixed
- `quote_add_symbols` now uses the two-parameter form after TradingView's June
  2025 protocol update, restoring live candle streams.

## [0.3.3] - 2025-07-09
### Fixed
- TradingView handshake and framing corrected for candle streams.
- `tvws candles live` no longer disconnects with `critical_error: quote_add_series` after TradingView protocol change (July 2025).

## [0.3.2] - 2025-07-08
### Fixed
- `Origin` header now sent on all TradingView WebSocket handshakes.
- CLI exposes `--origin` for custom values.

## [0.3.1] - 2025-07-08
### Fixed
- CLI now installs required websockets; candle & socket commands no longer crash.
- tvws stream/history emit valid JSON objects instead of stringified dataclasses.
### Improved
- Unsupported interval values raise a concise CLI error (status 2).

## [0.2.0] - 2025-07-08

### Added
- Initial changelog scaffold following Keep-a-Changelog guidelines.
- Continuous integration now caches Poetry by lock hash, runs `pip-audit`,
  and uploads coverage to Codecov.
- `Candle` dataclass converting TradingView frames into typed OHLCV bars.
- `CandleHub` in-process pub/sub helper and `CandleStream` for async
  broadcasting.
- `get_historic_candles` helper with caching to avoid redundant requests.
- `tvws candles` subcommands for live streaming and historic downloads.

## [0.1.1] - 2025-07-07

### Added
 - Packaging metadata hardened with author details and Trove classifiers.
 - `tvws` console script and CLI optional-extra declared for PyPI release.

## [0.1.0] - 2025-07-06

### Added
 - First public preview with basic WebSocket streaming client, logging helpers,
   and CLI stub.
