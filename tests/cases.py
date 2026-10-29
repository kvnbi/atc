import math
from dataclasses import dataclass

from atc.data import taxi
from atc.notes import Notes
from atc.state.models import Aircraft, Traffic

FLIGHT_PLAN = (
    "N123AB, Cessna 172, IFR, KSFO to KSEA, cruise 8000. "
    "Route: SSTIK5 departure, KAYEX transition, then direct KSEA. Assigned squawk 4521."
)
FREQUENCIES = {"clearance": 118200, "ground": 121800, "tower": 120500}
PLANNED = "N123AB IFR clearance to KSEA delivered, readback correct"
TAXI = "N123AB taxi runway 28R via C, hold short runway 19R"


@dataclass(frozen=True)
class Case:
    name: str
    position: str
    call: str
    where: str
    notes: Notes
    expect: tuple
    forbid: tuple = ()
    final_traffic: bool = False


CASES = (
    Case(
        "ifr_clearance",
        "clearance",
        "Clearance, Cessna one two three alpha bravo, IFR to Seattle, ready to copy.",
        "ramp",
        Notes(),
        (r"\bcleared\b", r"\bsquawk\b", r"\bSSTIK\b"),
    ),
    Case(
        "taxi",
        "ground",
        "Ground, Cessna one two three alpha bravo at the general aviation ramp, ready to taxi, IFR.",
        "ramp",
        Notes(clearances=[PLANNED]),
        (r"\btaxi\b", r"\brunway\b", r"\bhold short\b"),
    ),
    Case(
        "hold_short",
        "ground",
        "Ground, Cessna three alpha bravo, holding short runway one niner right, request crossing.",
        "crossing",
        Notes(clearances=[PLANNED, TAXI]),
        (r"\bhold (short|position)\b",),
        (r"(?<!not )\bcross runway one niner right\b", r"\bcleared to cross\b", r"\bone niner left\b"),
        final_traffic=True,
    ),
    Case(
        "takeoff_clearance",
        "tower",
        "Tower, Cessna three alpha bravo, holding short runway two eight right, ready for departure.",
        "runway",
        Notes(clearances=[PLANNED]),
        (r"\bcleared for takeoff\b", r"\brunway two eight right\b"),
        (r"\bline up\b",),
    ),
    Case(
        "bad_readback",
        "ground",
        "Taxi runway two eight right via charlie, Cessna three alpha bravo.",
        "ramp",
        Notes(clearances=[PLANNED, TAXI], readbacks=["pending: N123AB taxi readback"]),
        (r"\bnegative\b", r"\bhold short\b"),
    ),
)


def place(airport, where):
    g = taxi.graph(airport)
    if where == "ramp":
        ramp = next(r for r in airport.ramps if r.name == "GA Ramp")
        return ramp.lat, ramp.lon, 100.0
    end = airport.runway_end("28R")
    if where == "runway":
        lat, lon = airport.nodes[taxi._entry(airport, g, end)]
        return lat, lon, end.heading
    ramp = next(r for r in airport.ramps if r.name == "GA Ramp")
    _, hops = taxi._path(g, taxi._nearest(airport, g, ramp.lat, ramp.lon), taxi._entry(airport, g, end))
    nodes = [taxi._nearest(airport, g, ramp.lat, ramp.lon)] + [n for n, _ in hops]
    short = next(nodes[i - 1] for i, n in enumerate(nodes) if i and g.runway_nodes.get(n))
    lat, lon = airport.nodes[short]
    return lat, lon, 100.0


def final(airport):
    end = airport.runway_end("19R")
    back = math.radians((end.heading + 180) % 360)
    lat = end.lat + math.cos(back) / 60
    lon = end.lon + math.sin(back) / (60 * math.cos(math.radians(end.lat)))
    return Traffic(
        id="ai1",
        callsign="UAL482",
        lat=lat,
        lon=lon,
        alt_msl_ft=airport.elevation_ft + 300,
        heading_deg=end.heading,
        ground_speed_kt=130,
        on_ground=False,
    )


def aircraft(airport, case):
    lat, lon, heading = place(airport, case.where)
    return Aircraft(
        callsign="N123AB",
        lat=lat,
        lon=lon,
        alt_msl_ft=airport.elevation_ft,
        heading_deg=heading,
        on_ground=True,
        squawk=4521,
        com1_khz=FREQUENCIES[case.position],
    )
