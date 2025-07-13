from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Any


def to_json(obj: Any) -> str:
    """Return a JSON string ensuring dataclasses and datetimes are encoded as plain
    objects/ISO-8601 strings.

    >>> to_json(MyEvent(ts=datetime.datetime.utcnow()))
    '{"ts": "2025-07-08T12:34:56.123456Z", "price": 123.45}'
    """

    def _encoder(o: Any) -> Any:  # noqa: D401
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        # Convert Decimal to float for compactness / JS compatibility.
        try:
            from decimal import Decimal

            if isinstance(o, Decimal):
                return float(o)
        except ModuleNotFoundError:  # pragma: no cover – stdlib always present
            pass
        if isinstance(o, datetime.datetime):
            o = o.astimezone(datetime.timezone.utc)
            return o.isoformat().replace("+00:00", "Z")
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serialisable")

    return json.dumps(obj, default=_encoder, separators=(",", ":"))
