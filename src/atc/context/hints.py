from atc import spoken
from atc.data import taxi
from atc.state.models import Position


def crossed(pair):
    return " or ".join(spoken.runway(end) for end in pair.split("/"))


def taxi_hint(airports, snapshot, summaries):
    a = snapshot.aircraft
    if snapshot.position is not Position.GROUND or not a.on_ground or not airports:
        return ""
    airport = airports[0]
    ranked = summaries.get(airport.icao, {}).get("runways")
    if not ranked:
        return ""
    runway = ranked[0]["runway"]
    try:
        route = taxi.plan(airport, a.lat, a.lon, "", runway)
    except ValueError:
        return ""
    return (
        f"Suggested taxi to the best runway {spoken.runway(runway)}: taxiways "
        f"{', '.join(spoken.taxiway(t) for t in route.taxiways) or 'none'}, runways crossed "
        f"{', '.join(crossed(c) for c in route.crossings) or 'none'}, {route.distance_ft} feet."
    )
