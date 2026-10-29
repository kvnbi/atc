import asyncio

from atc import spoken
from atc.context.hints import crossed
from atc.data import airports, nav, taxi, weather
from atc.geo import range_bearing
from atc.llm.tools import Tool

TRAFFIC_LIMIT = 10
STRING = {"type": "string"}


def _object(**props):
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _airport(icao):
    airport = airports.find(icao)
    if airport is None:
        raise ValueError(f"unknown airport {icao}")
    return airport


def taxi_tool(snapshot):
    def handler(icao, origin, destination):
        aircraft = snapshot().aircraft
        route = taxi.plan(_airport(icao), aircraft.lat, aircraft.lon, origin, destination)
        return {
            "taxiways": [spoken.taxiway(t) for t in route.taxiways],
            "crossings": [crossed(c) for c in route.crossings],
            "hold_short_runway": spoken.runway(route.runway) if route.runway else "",
            "distance_ft": route.distance_ft,
        }

    return Tool(
        "get_taxi_route",
        "Taxi route on the airport surface. origin is a parking name, or empty for the aircraft position. "
        "destination is a runway such as 28R or a parking name. Returns taxiways in order, already in spoken words, runways "
        "the route crosses (hold short of each until cleared to cross), the runway to hold short of at "
        "the end, and the distance in feet.",
        _object(icao=STRING, origin=STRING, destination=STRING),
        handler,
    )


def procedure_tool():
    def handler(icao, kind, name, transition):
        found = nav.procedures(icao)[kind]
        if not name:
            return {n: [t or "common" for t in p.transitions] for n, p in found.items()}
        procedure = found.get(name.upper())
        if procedure is None:
            raise ValueError(f"unknown {kind} {name}, available: {', '.join(found) or 'none'}")
        key = "" if transition.lower() == "common" else transition.upper()
        if not transition and len(procedure.transitions) == 1:
            key = next(iter(procedure.transitions))
        if key not in procedure.transitions:
            return {"transitions": [t or "common" for t in procedure.transitions]}
        return {"legs": [f"{leg.seq} {leg.text}" for leg in procedure.transitions[key]]}

    return Tool(
        "get_procedure",
        "Published procedures at an airport. kind is SID, STAR or APPCH. Leave name empty to list the "
        "procedures with their transitions. Give a name and a transition to get its legs; 'common' "
        "selects the part without a transition.",
        _object(
            icao=STRING,
            kind={"type": "string", "enum": list(nav.KINDS)},
            name=STRING,
            transition=STRING,
        ),
        handler,
    )


def weather_tool():
    async def handler(icao):
        return weather.summarize(await asyncio.to_thread(weather.fetch, icao), airports.find(icao))

    return Tool(
        "get_weather",
        "Current METAR for an airport with wind, altimeter, an estimate of the wind in magnetic degrees "
        "(the way controllers report it) and runways ranked by headwind.",
        _object(icao=STRING),
        handler,
    )


def traffic_tool(snapshot):
    def handler(radius_nm):
        state = snapshot()
        aircraft = state.aircraft
        rows = []
        for t in state.traffic:
            nm, bearing = range_bearing(aircraft.lat, aircraft.lon, t.lat, t.lon)
            if nm <= radius_nm:
                rows.append((nm, bearing, t))
        rows.sort(key=lambda r: r[0])
        return [
            {
                "callsign": t.callsign or t.id,
                "range_nm": round(nm, 1),
                "clock": round(((bearing - aircraft.heading_deg) % 360) / 30) or 12,
                "altitude_ft": round(t.alt_msl_ft),
                "heading": round(t.heading_deg),
                "speed_kt": round(t.ground_speed_kt),
                "on_ground": t.on_ground,
            }
            for nm, bearing, t in rows[:TRAFFIC_LIMIT]
        ]

    return Tool(
        "get_traffic",
        "Other aircraft within a radius in nautical miles, nearest first, with range, clock position "
        "relative to the aircraft heading, altitude, heading and speed.",
        _object(radius_nm={"type": "number"}),
        handler,
    )


def data_tools(snapshot):
    return (taxi_tool(snapshot), procedure_tool(), weather_tool(), traffic_tool(snapshot))
