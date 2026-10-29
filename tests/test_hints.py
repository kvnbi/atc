from cases import place

from atc import spoken
from atc.context.hints import crossed, taxi_hint
from atc.llm.data_tools import taxi_tool
from atc.state.models import Position
from atc.state.store import StateStore


def ground_snapshot(ksfo, where="ramp"):
    lat, lon, heading = place(ksfo, where)
    store = StateStore()
    store.update_aircraft(lat=lat, lon=lon, heading_deg=heading, on_ground=True)
    store.set_position(Position.GROUND)
    return store


def test_spoken_taxiways_and_runways():
    assert spoken.taxiway("F1") == "foxtrot one"
    assert spoken.taxiway("a") == "alpha"
    assert spoken.runway("01L") == "zero one left"
    assert spoken.runway("28R") == "two eight right"
    assert spoken.runway("09") == "zero niner"
    assert crossed("01L/19R") == "zero one left or one niner right"


def test_taxi_hint_holds_no_digits_and_names_the_best_runway(ksfo):
    summaries = {"KSFO": {"runways": [{"runway": "28R", "headwind_kt": 12, "crosswind_kt": 0}]}}
    hint = taxi_hint((ksfo,), ground_snapshot(ksfo).snapshot(), summaries)
    assert hint.startswith("Suggested taxi to the best runway two eight right: taxiways ")
    assert not any(c.isdigit() for c in hint.rsplit(",", 1)[0])


def test_taxi_hint_only_on_the_ground_with_weather(ksfo):
    store = ground_snapshot(ksfo)
    summaries = {"KSFO": {"runways": [{"runway": "28R"}]}}
    assert taxi_hint((ksfo,), store.snapshot(), {}) == ""
    assert taxi_hint((), store.snapshot(), summaries) == ""
    store.set_position(Position.TOWER)
    assert taxi_hint((ksfo,), store.snapshot(), summaries) == ""
    store.set_position(Position.GROUND)
    store.update_aircraft(on_ground=False)
    assert taxi_hint((ksfo,), store.snapshot(), summaries) == ""


def test_taxi_tool_answers_in_spoken_words(ksfo):
    store = ground_snapshot(ksfo)
    result = taxi_tool(store.snapshot).handler("KSFO", "", "28R")
    assert result["hold_short_runway"] == "two eight right"
    assert all(not any(c.isdigit() for c in t) for t in result["taxiways"] + result["crossings"])
    assert result["distance_ft"] > 0
