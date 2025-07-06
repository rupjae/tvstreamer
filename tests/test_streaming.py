import time
from datetime import datetime

import pytest

import tvstreamer.streaming as streaming_mod
from tvstreamer.events import Tick, Bar
from tvstreamer.streaming import StreamRouter


@pytest.fixture
def dummy_stream(monkeypatch):
    # Prepare a fixed sequence: one Tick, then one closed Bar
    events = [
        Tick(ts=datetime.utcnow(), price=1.0, volume=1, symbol="FOO"),
        Bar(
            ts=datetime.utcnow(),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
            symbol="FOO",
            interval="1",
            closed=True,
        ),
    ]

    class DummyClient:
        def __init__(self, subs):
            pass

        def connect(self):
            pass

        def close(self):
            pass

        def stream(self):
            yield from events

    monkeypatch.setattr(streaming_mod, "TvWSClient", DummyClient)
    return events


def test_iterators_and_shutdown(dummy_stream):
    # iter_ticks yields the Tick event, iter_closed_bars yields the Bar event
    # Test ticks iterator
    router1 = StreamRouter([("FOO", "1")], queue_maxsize=1)
    with router1:
        ticks = list(router1.iter_ticks("FOO"))
    assert len(ticks) == 1 and isinstance(ticks[0], Tick)
    assert router1._dispatch_thread is not None
    assert not router1._dispatch_thread.is_alive()

    # Test closed bars iterator
    router2 = StreamRouter([("FOO", "1")], queue_maxsize=1)
    with router2:
        bars = list(router2.iter_closed_bars(("FOO", "1")))
    assert len(bars) == 1 and isinstance(bars[0], Bar)
    assert router2._dispatch_thread is not None
    assert not router2._dispatch_thread.is_alive()


def test_subscribe_and_unsubscribe(dummy_stream):
    received: list[Bar] = []

    def on_bar(evt: Bar) -> None:
        received.append(evt)

    router = StreamRouter([("FOO", "1")], queue_maxsize=1)
    dispose = router.subscribe(("FOO", "1"), on_bar, tick=False)
    # Ensure subscription handle removes the callback
    assert dispose is not None
    dispose()
    assert not router._callbacks

    # With context, callback is invoked for Bar
    dispose = None
    with StreamRouter([("FOO", "1")], queue_maxsize=1) as r2:
        dispose = r2.subscribe(("FOO", "1"), on_bar)
        # allow dispatch to run
        time.sleep(0.01)
    assert any(isinstance(evt, Bar) for evt in received)
