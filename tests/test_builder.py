from atc.context.builder import LOG_LINES, MAX_TRAFFIC, ContextBuilder
from atc.data import weather
from atc.notes import Notes
from atc.state.models import Traffic
from atc.state.store import StateStore


def snapshot(traffic=()):
    store = StateStore()
    store.update_aircraft(callsign="N123AB", com1_khz=121800)
    store.set_traffic(traffic)
    store.set_position("ground")
    return store.snapshot()


def build(notes, traffic=(), **kwargs):
    system, messages = ContextBuilder("plan").build(snapshot(traffic), notes, call="test", **kwargs)
    return messages[0]["content"]


def test_empty_notes_take_one_line_and_filled_sections_only_appear():
    assert "Flight notes: empty" in build(Notes())
    text = build(Notes(clearances=["cleared"], upcoming=["handoff"]))
    assert "Clearances:\n- cleared" in text and "Upcoming:\n- handoff" in text
    assert "Readbacks:" not in text and "Log:" not in text


def test_only_the_recent_log_is_sent():
    text = build(Notes(log=[f"entry {i}" for i in range(LOG_LINES + 5)]))
    assert "entry 4" not in text and "entry 5" in text and f"entry {LOG_LINES + 4}" in text


def test_traffic_is_capped_and_nearest_first():
    traffic = [Traffic(id=f"t{i}", callsign=f"AAL{i}", lat=0.01 * (i + 1), lon=0.0) for i in range(MAX_TRAFFIC + 4)]
    lines = [line for line in build(Notes(), traffic).splitlines() if line.startswith("- AAL")]
    assert len(lines) == MAX_TRAFFIC and lines[0].startswith("- AAL0")


def test_weather_and_the_pilot_call_close_the_message():
    text = build(Notes(), weather="KSFO 30012KT")
    assert "Weather\nKSFO 30012KT" in text and text.rstrip().endswith('Pilot: "test"')


def test_weather_brief_names_the_best_runways(ksfo):
    out = weather.summarize("KSFO 281856Z 28010KT 10SM CLR 15/08 A3012", ksfo)
    text = weather.brief(out)
    assert text.startswith("KSFO 281856Z") and "Best runways: 28" in text and "magnetic about" in text
    assert weather.brief(weather.summarize("KSFO 281856Z VRB02KT 10SM CLR 15/08 A3012", ksfo)).startswith("KSFO")
