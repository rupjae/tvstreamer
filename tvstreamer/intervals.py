from __future__ import annotations

"""Interval utilities for TradingView resolutions."""

from typing import Set

__all__ = ["validate", "ALLOWED_INTERVALS"]

ALLOWED_INTERVALS: Set[str] = {
    "1",
    "3",
    "5",
    "15",
    "30",
    "60",
    "120",
    "240",
    "D",
    "W",
    "M",
}


def validate(raw: str) -> str:
    """Return TradingView resolution code for *raw* interval."""

    cleaned = raw.strip().lower()
    if cleaned.endswith("m"):
        cleaned = cleaned[:-1]
    elif cleaned.endswith("h") and cleaned[:-1].isdigit():
        cleaned = str(int(cleaned[:-1]) * 60)
    elif cleaned.endswith("d") and cleaned[:-1].isdigit():
        cleaned = str(int(cleaned[:-1]) * 1440)
    elif cleaned.endswith("w") and cleaned[:-1].isdigit():
        cleaned = str(int(cleaned[:-1]) * 10080)
    elif cleaned.endswith("mo") and cleaned[:-2].isdigit():
        cleaned = "M"

    if cleaned.isdigit():
        if cleaned not in ALLOWED_INTERVALS:
            raise ValueError(f"Unsupported interval: {raw}")
        return cleaned
    cleaned = cleaned.upper()
    if cleaned not in ALLOWED_INTERVALS:
        raise ValueError(f"Unsupported interval: {raw}")
    return cleaned
