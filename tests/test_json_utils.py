from __future__ import annotations

import dataclasses
from datetime import datetime, timezone, timedelta
import json

from tvstreamer.json_utils import to_json


@dataclasses.dataclass
class Inner:
    ts: datetime


@dataclasses.dataclass
class Wrapper:
    inner: Inner
    id: int


def test_to_json_nested_dataclass():
    obj = Wrapper(Inner(datetime(2020, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))), id=1)
    payload = to_json(obj)
    data = json.loads(payload)
    assert data["inner"]["ts"].endswith("Z")
