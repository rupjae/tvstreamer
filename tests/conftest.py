"""
Global test fixtures to isolate logging side-effects and ensure clean state.
"""

import logging


import pytest


@pytest.fixture(autouse=True)
def disable_logging() -> None:
    """Clear and close all logging handlers before and after each test."""
    root = logging.getLogger()
    # Close existing handlers
    for h in root.handlers:
        try:
            h.close()
        except Exception:
            pass
    root.handlers.clear()
    root.setLevel(logging.CRITICAL)
    yield
    # Tear down any handlers added during test
    for h in root.handlers:
        try:
            h.close()
        except Exception:
            pass
    root.handlers.clear()
