import asyncio
import io
import json
import urllib.error
from types import SimpleNamespace as NS

import pytest

from atc import main, simbrief, spoken

SAMPLE = {
    "fetch": {"userid": "123456", "status": "Success"},
    "general": {
        "icao_airline": "UAL",
        "flight_number": "482",
        "initial_altitude": "35000",
        "route": "SSTIK SSTIK5 KAYEX J1 SEA",
        "sid_ident": "SSTIK5",
        "star_ident": "HAWKZ3",
    },
    "origin": {"icao_code": "KSFO", "plan_rwy": "28R"},
    "destination": {"icao_code": "KSEA", "plan_rwy": "16L"},
    "alternate": {"icao_code": "KPDX"},
    "aircraft": {"icaocode": "B738", "reg": "N12345"},
    "atc": {"callsign": "UAL482"},
}


def sample(**changes):
    data = json.loads(json.dumps(SAMPLE))
    for path, value in changes.items():
        node = data
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return data


def test_parse_reads_the_plan_fields():
    plan = simbrief.parse(SAMPLE)
    assert (plan.callsign, plan.aircraft, plan.origin, plan.destination, plan.alternate) == (
        "UAL482",
        "B738",
        "KSFO",
        "KSEA",
        "KPDX",
    )
    assert (plan.cruise_ft, plan.sid, plan.star) == (35000, "SSTIK5", "HAWKZ3")
    assert plan.airports == ("KSFO", "KSEA")
    assert plan.text == (
        "UAL482, B738, IFR, KSFO to KSEA, cruise 35000. Route: SSTIK5 departure, SSTIK SSTIK5 KAYEX J1 SEA, "
        "HAWKZ3 arrival. Planned runways 28R out, 16L in."
    )


def test_callsign_falls_back_to_the_airline_and_number_then_the_registration():
    assert simbrief.parse(sample(atc__callsign={})).callsign == "UAL482"
    data = sample(atc__callsign={}, general__icao_airline={}, general__flight_number={})
    assert simbrief.parse(data).callsign == "N12345"


def test_empty_values_and_alternate_lists_are_tolerated():
    data = sample(general__route={}, general__sid_ident={}, general__star_ident={}, general__initial_altitude={})
    data["alternate"] = [{"icao_code": "KOAK"}]
    plan = simbrief.parse(data)
    assert plan.alternate == "KOAK" and plan.cruise_ft == 0
    assert plan.text == "UAL482, B738, IFR, KSFO to KSEA. Planned runways 28R out, 16L in."
    data["alternate"] = []
    assert simbrief.parse(data).alternate == ""


def test_errors_are_reported_plainly():
    with pytest.raises(ValueError, match="Unknown UserID"):
        simbrief.parse(sample(fetch__status="Error: Unknown UserID"))
    with pytest.raises(ValueError, match="no origin"):
        simbrief.parse(sample(origin__icao_code={}))


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_asks_for_json_v2_by_username_or_pilot_id(monkeypatch):
    urls = []

    def fake(url, timeout):
        urls.append(url)
        return Reply(json.dumps(SAMPLE).encode())

    monkeypatch.setattr(simbrief.urllib.request, "urlopen", fake)
    assert simbrief.load("some_pilot").callsign == "UAL482"
    assert simbrief.load("123456").callsign == "UAL482"
    assert "username=some_pilot" in urls[0] and "json=v2" in urls[0] and "client=atc" in urls[0]
    assert "userid=123456" in urls[1]


def test_fetch_failures_become_value_errors(monkeypatch):
    def not_found(url, timeout):
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)

    def offline(url, timeout):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(simbrief.urllib.request, "urlopen", not_found)
    with pytest.raises(ValueError, match="no plan found for nobody"):
        simbrief.fetch("nobody")
    monkeypatch.setattr(simbrief.urllib.request, "urlopen", offline)
    with pytest.raises(ValueError, match="could not read"):
        simbrief.fetch("nobody")
    monkeypatch.setattr(simbrief.urllib.request, "urlopen", lambda url, timeout: Reply(b"<xml/>"))
    with pytest.raises(ValueError, match="could not read"):
        simbrief.fetch("nobody")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("UAL482", "United four eight two"),
        ("AAL1A", "American one alpha"),
        ("BAW9", "Speedbird niner"),
        ("N123AB", "november one two three alpha bravo"),
        ("XYZ12", "xray yankee zulu one two"),
    ],
)
def test_spoken_callsigns(text, expected):
    assert spoken.callsign(text) == expected


def test_main_uses_the_plan_unless_the_user_overrides_it(ksfo, monkeypatch):
    plan = simbrief.parse(SAMPLE)
    monkeypatch.setattr(simbrief, "load", lambda user: plan)
    text, callsign, scope = asyncio.run(main._plan(NS(simbrief="pilot", flight_plan="", callsign="")))
    assert (text, callsign) == (plan.text, "UAL482")
    assert [a.icao for a in scope] == ["KSFO", "KSEA"]
    text, callsign, _ = asyncio.run(main._plan(NS(simbrief="pilot", flight_plan="custom", callsign="N1")))
    assert (text, callsign) == ("custom", "N1")


def test_main_without_simbrief_reads_airports_from_the_text(ksfo):
    text, callsign, scope = asyncio.run(main._plan(NS(simbrief="", flight_plan="KSFO to KSEA", callsign="N1")))
    assert (text, callsign) == ("KSFO to KSEA", "N1") and [a.icao for a in scope] == ["KSFO", "KSEA"]


def test_main_stops_with_a_clear_message_when_simbrief_fails(monkeypatch):
    def boom(user):
        raise ValueError("SimBrief: no plan found for pilot (HTTP 400)")

    monkeypatch.setattr(simbrief, "load", boom)
    with pytest.raises(SystemExit, match="no plan found"):
        asyncio.run(main._plan(NS(simbrief="pilot", flight_plan="", callsign="")))
