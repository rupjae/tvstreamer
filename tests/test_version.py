"""Ensure the runtime version string stays in sync with pyproject.toml."""

from __future__ import annotations

import pathlib as _pl


# tomllib is stdlib in 3.11+; fall back to *tomli* on older versions.
try:
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover – <3.11 runtime
    import tomli as tomllib  # type: ignore


def _read_version_from_pyproject() -> str:
    """Return the version defined in *pyproject.toml* (tool.poetry.version)."""

    root = _pl.Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as fp:
        data = tomllib.load(fp)
    return data["tool"]["poetry"]["version"]


def test_runtime_version_matches_pyproject():
    import tvstreamer

    assert tvstreamer.__version__ == _read_version_from_pyproject()
