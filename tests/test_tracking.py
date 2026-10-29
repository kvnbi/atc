import pytest

from atc.state.models import Position
from atc.state.store import StateStore
from atc.state.tracking import Tracker, position_for


@pytest.mark.parametrize(
    "khz, expected",
    [
        (118200, Position.CLEARANCE),
        (121800, Position.GROUND),
        (128650, Position.GROUND),
        (120500, Position.TOWER),
        (135100, Position.DEPARTURE),
        (128325, Position.APPROACH),
        (113700, None),
        (122950, None),
        (121500, None),
        (0, None),
    ],
)
def test_position_for(ksfo, khz, expected):
    assert position_for((ksfo,), khz) is expected


def test_tracker_follows_radio(ksfo):
    store = StateStore()
    tracker = Tracker(store, lambda: (ksfo,))
    store.update_aircraft(com1_khz=121800)
    assert tracker.resolve() is Position.GROUND
    assert store.snapshot().position is Position.GROUND
    store.update_aircraft(com1_khz=120500)
    assert tracker.resolve() is Position.TOWER
    store.update_aircraft(com1_khz=121500)
    assert tracker.resolve() is None
    assert store.snapshot().position is None


def test_fixed_position_overrides_radio(ksfo):
    store = StateStore()
    tracker = Tracker(store, lambda: (ksfo,), "approach")
    store.update_aircraft(com1_khz=121800)
    assert tracker.resolve() is Position.APPROACH
    tracker.fixed = None
    assert tracker.resolve() is Position.GROUND


def test_no_airports_means_no_controller():
    store = StateStore()
    store.update_aircraft(com1_khz=121800)
    assert Tracker(store, lambda: ()).resolve() is None
