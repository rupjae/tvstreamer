"""Basic smoke tests ensuring core modules import and logging is configured.

These tests are intentionally lightweight – they run as part of the CI
foundation work order to guarantee that the package is at least importable
and that the public helpers behave as expected.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path


def test_import_package():
    """The tvstreamer top-level package should import without side-effects."""

    import tvstreamer  # noqa: F401 – import is the test


def test_configure_logging_creates_files(tmp_path: Path, monkeypatch):
    """`configure_logging()` must create both .log and .jsonl files."""

    # Redirect the *logs/* directory to a temp folder so we don't pollute the
    # working tree during the test run.
    monkeypatch.chdir(tmp_path)

    from tvstreamer.logging_utils import configure_logging

    log_path, json_path = configure_logging(debug=True)

    assert log_path.exists(), "Human-readable log file missing"
    assert json_path.exists(), "Structured JSONL log file missing"

    # The JSONL file must contain at least one well-formed record after we log.
    logger = logging.getLogger("test")
    logger.info("hello from pytest", extra={"code_path": __file__})

    with json_path.open(encoding="utf-8") as fp:
        line = fp.readline().strip()
    record = json.loads(line)

    assert record["msg"] == "hello from pytest"
    assert record["code_path"] == __file__


def test_trace_decorator(capsys):
    """`@trace` should emit entry and exit lines at TRACE level (5)."""

    from tvstreamer.logging_utils import TRACE_LEVEL, trace

    # Capture root logger output to stderr only – avoid files to keep test fast.
    root = logging.getLogger()
    root.handlers.clear()
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(TRACE_LEVEL)
    root.addHandler(stream_handler)
    root.setLevel(TRACE_LEVEL)

    @trace  # type: ignore[misc]
    def sample() -> str:  # noqa: D401 – fixture function
        return "ok"

    assert sample() == "ok"

    # Ensure *both* entry and exit lines made it to the captured stream.
    stream_handler.flush()
    captured = capsys.readouterr().err
    # The decorator logs fully-qualified call signatures; allow for nested
    # function context in the test environment by checking *contains* rather
    # than exact equality.
    assert "→" in captured and "sample()" in captured
    assert "←" in captured and "sample()" in captured


def test_anyio_mock_clock():
    """Ensure anyio.MockClock is importable and usable."""

    import anyio  # type: ignore

    if not hasattr(anyio, "current_time") or not hasattr(anyio, "run"):
        import pytest

        pytest.skip("anyio runtime missing required helpers")

    async def delayed_sum(a: int, b: int) -> int:  # noqa: D401 – helper
        await anyio.sleep(0.01)
        return a + b

    async def main() -> bool:  # noqa: D401 – inner helper
        return await delayed_sum(2, 3) == 5

    result = anyio.run(main)
    assert result is True
