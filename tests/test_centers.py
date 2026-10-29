from atc.data import centers
from atc.state.models import Position
from atc.state.store import StateStore
from atc.state.tracking import Tracker, position_for


def test_frequencies_are_stable_valid_vhf_channels():
    seen = set()
    for lat in range(-60, 70, 2):
        for lon in range(-180, 180, 2):
            khz = centers.frequency(lat + 0.5, lon + 0.5)
            assert 125000 <= khz <= 135975 and khz % 25 == 0
            seen.add(khz)
    assert len(seen) > 100
    assert centers.frequency(38.5, -121.0) == centers.frequency(38.9, -120.1)
    assert centers.frequency(38.5, -121.0) != centers.frequency(38.5, -119.0)
    assert centers.frequency(38.5, -121.0) != centers.frequency(40.5, -121.0)


def test_tracker_recognizes_the_local_center_frequency(ksfo):
    store = StateStore()
    tracker = Tracker(store, lambda: (ksfo,))
    store.update_aircraft(lat=38.5, lon=-121.0, com1_khz=centers.frequency(38.5, -121.0))
    assert tracker.resolve() is Position.CENTER
    store.update_aircraft(com1_khz=centers.frequency(38.5, -121.0) + 25)
    assert tracker.resolve() is None
    assert position_for((ksfo,), 120500, 38.5, -121.0) is Position.TOWER
