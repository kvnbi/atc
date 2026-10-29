import asyncio
import math

import pytest
from cases import place

from atc import notes as flight_notes
from atc.data import airports
from atc.events import Event, Watcher, watch
from atc.notes import Notes
from atc.state.models import Traffic
from atc.state.store import StateStore
from atc.state.tracking import Tracker


@pytest.fixture(scope="session")
def ksea():
    airport = airports.find("KSEA")
    if airport is None:
        pytest.skip("KSEA not found")
    return airport


class World:
    def __init__(self, tmp_path, scope, position="tower"):
        self.store = StateStore()
        self.path = tmp_path / "flight.md"
        flight_notes.save(self.path, Notes())
        self.watcher = Watcher(Tracker(self.store, lambda: scope, position), self.store, self.path, lambda: scope)

    def at(self, lat, lon, **fields):
        self.store.update_aircraft(lat=lat, lon=lon, **fields)
        return self

    def notes(self, **lists):
        flight_notes.save(self.path, Notes(**lists))

    def poll(self, now=0.0):
        return self.watcher.poll(now)


def keys(events):
    return [e.key for e in events]


def offset(lat, lon, north_nm, east_nm):
    return lat + north_nm / 60, lon + east_nm / (60 * math.cos(math.radians(lat)))


def final_point(airport, name, nm):
    end = airport.runway_end(name)
    h = math.radians(end.heading)
    return offset(end.lat, end.lon, -nm * math.cos(h), -nm * math.sin(h))


def midpoint(airport, name):
    runway = next(r for r in airport.runways if any(e.name == name for e in r.ends))
    a, b = runway.ends
    return (a.lat + b.lat) / 2, (a.lon + b.lon) / 2


def test_hold_short_handoff_to_tower(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,), "ground")
    lat, lon, _ = place(ksfo, "crossing")
    world.at(lat, lon, on_ground=True, ground_speed_kt=0.0)
    events = world.poll()
    assert keys(events)[0].startswith("handoff:hold:") and "120.500" in events[0].text
    assert world.poll() == []
    ramp = place(ksfo, "ramp")
    world.at(ramp[0], ramp[1])
    assert world.poll() == []
    world.at(lat, lon)
    assert len(world.poll()) == 1


def test_moving_aircraft_gets_no_hold_short_handoff(ksfo, tmp_path):
    lat, lon, _ = place(ksfo, "crossing")
    world = World(tmp_path, (ksfo,), "ground").at(lat, lon, on_ground=True, ground_speed_kt=12.0)
    assert world.poll() == []


def test_departure_handoff_after_takeoff(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,)).at(ksfo.lat, ksfo.lon, on_ground=False, alt_agl_ft=200.0, vertical_speed_fpm=1500.0)
    assert world.poll() == []
    world.at(ksfo.lat, ksfo.lon, alt_agl_ft=600.0)
    events = world.poll()
    assert keys(events) == ["handoff:departure"]
    assert "120.900" in events[0].text and "135.100" in events[0].text
    assert world.poll() == []


def test_landing_handoff_to_ground(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,)).at(
        ksfo.lat, ksfo.lon, on_ground=False, alt_agl_ft=200.0, vertical_speed_fpm=-600.0
    )
    assert world.poll() == []
    world.at(ksfo.lat, ksfo.lon, on_ground=True, alt_agl_ft=0.0, ground_speed_kt=60.0, vertical_speed_fpm=0.0)
    assert world.poll() == []
    world.at(ksfo.lat, ksfo.lon, ground_speed_kt=20.0)
    events = world.poll()
    assert keys(events) == ["handoff:landed"] and "121.800" in events[0].text
    assert world.poll() == []


def test_center_handoff_when_leaving_departure_airspace(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,), "departure")
    world.at(*offset(ksfo.lat, ksfo.lon, 10, 0), on_ground=False, alt_agl_ft=5000.0)
    assert world.poll() == []
    world.at(*offset(ksfo.lat, ksfo.lon, 36, 0))
    assert keys(world.poll()) == ["handoff:center"]


def test_approach_and_final_handoffs(ksfo, ksea, tmp_path):
    center = World(tmp_path / "a", (ksfo, ksea), "center") if (tmp_path / "a").mkdir() is None else None
    center.at(*offset(ksea.lat, ksea.lon, 60, 0), on_ground=False, alt_agl_ft=20000.0)
    assert center.poll() == []
    center.at(*offset(ksea.lat, ksea.lon, 30, 0))
    assert keys(center.poll())[0].startswith("handoff:sector:")
    events = center.poll()
    assert keys(events) == ["handoff:approach"] and "KSEA" in events[0].text
    (tmp_path / "b").mkdir()
    approach = World(tmp_path / "b", (ksfo, ksea), "approach")
    approach.at(*offset(ksea.lat, ksea.lon, 12, 0), on_ground=False, alt_agl_ft=2000.0)
    assert keys(approach.poll()) == ["approach:clearance"]
    approach.at(*offset(ksea.lat, ksea.lon, 6, 0))
    assert keys(approach.poll()) == ["handoff:final"]


def test_altitude_deviation_needs_time_and_wrong_direction(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    world.notes(clearances=["N123AB climb and maintain 8000"])
    world.at(ksfo.lat, ksfo.lon, on_ground=False, alt_agl_ft=8000.0, alt_msl_ft=8500.0, vertical_speed_fpm=0.0)
    assert world.poll(0.0) == [] and world.poll(10.0) == []
    events = world.poll(16.0)
    assert keys(events) == ["altitude:8000"] and "8500" in events[0].text and "above" in events[0].text
    assert world.poll(17.0) == []


def test_no_deviation_while_moving_toward_the_altitude(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    world.notes(clearances=["N123AB maintain 8000"])
    world.at(ksfo.lat, ksfo.lon, on_ground=False, alt_agl_ft=5000.0, alt_msl_ft=5000.0, vertical_speed_fpm=1500.0)

    def altitude(now):
        return [e for e in world.poll(now) if e.key.startswith("altitude")]

    assert [altitude(t) for t in (0.0, 20.0, 100.0)] == [[], [], []]
    world.at(ksfo.lat, ksfo.lon, alt_msl_ft=8600.0, vertical_speed_fpm=800.0)
    altitude(200.0)
    assert len(altitude(216.0)) == 1


def test_flight_level_assignment(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    world.notes(clearances=["N123AB maintain 8000", "N123AB climb and maintain FL240"])
    world.at(ksfo.lat, ksfo.lon, on_ground=False, alt_agl_ft=20000.0, alt_msl_ft=23000.0)
    world.poll(0.0)
    assert keys(world.poll(20.0)) == ["altitude:24000"]


def test_runway_occupied_while_on_final(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    lat, lon = final_point(ksfo, "28R", 1.0)
    world.at(lat, lon, on_ground=False, alt_agl_ft=300.0, alt_msl_ft=ksfo.elevation_ft + 300, vertical_speed_fpm=-600.0)
    mid = midpoint(ksfo, "28R")
    world.store.set_traffic([Traffic(id="t1", callsign="UAL482", lat=mid[0], lon=mid[1], on_ground=True)])
    events = world.poll()
    assert keys(events) == ["runway:28R:occupied"] and "UAL482" in events[0].text
    world.store.set_traffic([Traffic(id="t1", callsign="UAL482", lat=mid[0], lon=mid[1], alt_msl_ft=900, on_ground=False)])
    assert keys(world.poll()) == ["landing:28R"]
    world.store.set_traffic([])
    assert world.poll() == []


def test_traffic_on_final_while_aircraft_on_runway(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    mid = midpoint(ksfo, "28R")
    world.at(mid[0], mid[1], on_ground=True, alt_agl_ft=0.0, ground_speed_kt=5.0)
    lat, lon = final_point(ksfo, "28R", 1.5)
    world.store.set_traffic(
        [Traffic(id="t2", callsign="SWA901", lat=lat, lon=lon, alt_msl_ft=ksfo.elevation_ft + 400, heading_deg=298.0)]
    )
    events = world.poll()
    assert keys(events) == ["runway:28R:traffic"] and "SWA901" in events[0].text


def test_ground_position_gets_no_runway_events(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,), "ground")
    lat, lon = final_point(ksfo, "28R", 1.0)
    world.at(lat, lon, on_ground=False, alt_agl_ft=300.0, alt_msl_ft=ksfo.elevation_ft + 300)
    mid = midpoint(ksfo, "28R")
    world.store.set_traffic([Traffic(id="t1", lat=mid[0], lon=mid[1], on_ground=True)])
    assert world.poll() == []


def test_readback_timeout_fires_twice_then_resets(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,), "ground")
    line = "pending: N123AB taxi readback"
    world.notes(readbacks=[line])
    assert world.poll(0.0) == [] and world.poll(19.0) == []
    first = world.poll(21.0)
    assert len(first) == 1 and line in first[0].text
    assert world.poll(22.0) == []
    assert len(world.poll(51.0)) == 1
    assert world.poll(60.0) == []
    world.notes(readbacks=[])
    assert world.poll(61.0) == []
    world.notes(readbacks=[line])
    assert world.poll(62.0) == [] and world.poll(81.0) == [] and len(world.poll(83.0)) == 1


def test_no_events_without_a_controller(ksfo, tmp_path):
    store = StateStore()
    path = tmp_path / "flight.md"
    flight_notes.save(path, Notes(readbacks=["pending: x"]))
    store.update_aircraft(lat=ksfo.lat, lon=ksfo.lon, on_ground=False, alt_agl_ft=600.0, vertical_speed_fpm=1500.0)
    watcher = Watcher(Tracker(store, lambda: (ksfo,)), store, path, lambda: (ksfo,))
    assert watcher.poll(0.0) == [] and watcher.poll(100.0) == []


def test_watch_hands_events_to_the_turn():
    class Fake:
        def __init__(self):
            self.queue = [[Event("a", "first"), Event("b", "second")], [], [Event("c", "third")]]

        def poll(self):
            if self.queue:
                return self.queue.pop(0)
            raise RuntimeError("boom")

    heard = []

    async def turn(event):
        heard.append(event)

    async def scenario():
        task = asyncio.create_task(watch(Fake(), turn, interval=0.01))
        await asyncio.sleep(0.15)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert heard == ["first", "second", "third"]


def test_enroute_sector_changes_hand_off_to_the_next_center(ksfo, tmp_path):
    from atc.data import centers

    world = World(tmp_path, (ksfo,), "center")
    lat, lon = 38.5, -121.0
    world.at(lat, lon, on_ground=False, alt_agl_ft=20000.0, alt_msl_ft=24000.0)
    assert world.poll() == []
    assert world.poll() == []
    world.at(lat, lon + 2.0)
    events = world.poll()
    khz = centers.frequency(lat, lon + 2.0)
    assert keys(events)[0].startswith("handoff:sector:") and f"{khz / 1000:.3f}" in events[0].text
    assert world.poll() == []


def test_departure_handoff_to_center_names_the_sector_frequency(ksfo, tmp_path):
    from atc.data import centers

    world = World(tmp_path, (ksfo,), "departure")
    lat, lon = offset(ksfo.lat, ksfo.lon, 36, 0)
    world.at(lat, lon, on_ground=False, alt_agl_ft=9000.0)
    events = world.poll()
    assert keys(events) == ["handoff:center"]
    assert f"{centers.frequency(lat, lon) / 1000:.3f}" in events[0].text


def test_entering_center_does_not_trigger_a_sector_handoff(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,), "tower")
    world.at(38.5, -121.0, on_ground=False, alt_agl_ft=20000.0)
    world.poll()
    world.watcher._tracker.fixed = "center"
    assert world.poll() == []


def test_approach_clearance_is_requested_once_until_issued(ksfo, ksea, tmp_path):
    world = World(tmp_path, (ksfo, ksea), "approach")
    world.at(*offset(ksea.lat, ksea.lon, 20, 0), on_ground=False, alt_agl_ft=9000.0, alt_msl_ft=9000.0)
    events = world.poll()
    assert keys(events) == ["approach:clearance"] and "get_procedure" in events[0].text
    assert world.poll() == []
    world.notes(clearances=["N123AB cleared ILS runway 16L approach"])
    assert world.poll() == []
    world.at(*offset(ksea.lat, ksea.lon, 40, 0))
    assert world.poll() == []


def test_landing_clearance_due_on_clear_final_until_issued(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    lat, lon = final_point(ksfo, "28R", 2.0)
    world.at(lat, lon, on_ground=False, alt_agl_ft=600.0, alt_msl_ft=ksfo.elevation_ft + 600, vertical_speed_fpm=-700.0)
    events = world.poll()
    assert keys(events) == ["landing:28R"] and "2.0 nm" in events[0].text
    issued = World(tmp_path / "issued", (ksfo,)) if (tmp_path / "issued").mkdir() is None else None
    issued.at(lat, lon, on_ground=False, alt_agl_ft=600.0, alt_msl_ft=ksfo.elevation_ft + 600, vertical_speed_fpm=-700.0)
    issued.notes(clearances=["N123AB cleared to land runway 28R"])
    assert issued.poll() == []


def test_parallel_runways_resolve_to_the_one_flown(ksfo, tmp_path):
    world = World(tmp_path, (ksfo,))
    lat, lon = final_point(ksfo, "28L", 1.5)
    world.at(lat, lon, on_ground=False, alt_agl_ft=450.0, alt_msl_ft=ksfo.elevation_ft + 450, vertical_speed_fpm=-600.0)
    assert keys(world.poll()) == ["landing:28L"]


def test_watch_waits_for_a_clear_frequency_before_polling():
    state = {"clear": False, "polls": 0}

    class Fake:
        def poll(self):
            state["polls"] += 1
            return []

    async def ready():
        while not state["clear"]:
            await asyncio.sleep(0.01)

    async def scenario():
        task = asyncio.create_task(watch(Fake(), lambda event: None, interval=0.01, ready=ready))
        await asyncio.sleep(0.1)
        blocked = state["polls"]
        state["clear"] = True
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return blocked

    assert asyncio.run(scenario()) == 0 and state["polls"] > 0
