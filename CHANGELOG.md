# Changelog

All notable changes to this project will be documented in this file following the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
 - Initial changelog scaffold following Keep-a-Changelog guidelines.
 - Continuous integration now caches Poetry by lock hash, runs `pip-audit`,
   and uploads coverage to Codecov.

## [0.1.1] - 2025-07-07

### Added
 - Packaging metadata hardened with author details and Trove classifiers.
 - `tvws` console script and CLI optional-extra declared for PyPI release.

## [0.1.0] - 2025-07-06

### Added
 - First public preview with basic WebSocket streaming client, logging helpers,
   and CLI stub.
