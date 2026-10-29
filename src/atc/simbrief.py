import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

URL = "https://www.simbrief.com/api/xml.fetcher.php?{query}"
TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class Plan:
    callsign: str
    aircraft: str
    origin: str
    destination: str
    alternate: str
    cruise_ft: int
    route: str
    sid: str
    star: str
    origin_runway: str
    destination_runway: str

    @property
    def airports(self):
        return tuple(code for code in (self.origin, self.destination) if code)

    @property
    def text(self):
        parts = [self.callsign, self.aircraft, "IFR", f"{self.origin} to {self.destination}"]
        if self.cruise_ft:
            parts.append(f"cruise {self.cruise_ft}")
        text = ", ".join(p for p in parts if p) + "."
        route = [f"{self.sid} departure" if self.sid else "", self.route, f"{self.star} arrival" if self.star else ""]
        route = ", ".join(r for r in route if r)
        if route:
            text += f" Route: {route}."
        runways = [f"{r} out" for r in (self.origin_runway,) if r] + [f"{r} in" for r in (self.destination_runway,) if r]
        if runways:
            text += f" Planned runways {', '.join(runways)}."
        return text


def _node(data, *path):
    for key in path:
        data = data.get(key) if isinstance(data, dict) else None
    return data


def _text(value):
    return "" if value is None or isinstance(value, (dict, list)) else str(value).strip()


def _first(*values):
    return next((v for v in map(_text, values) if v), "")


def parse(data):
    status = _text(_node(data, "fetch", "status"))
    if status and status != "Success":
        raise ValueError(f"SimBrief: {status}")
    alternate = _node(data, "alternate")
    if isinstance(alternate, list):
        alternate = alternate[0] if alternate else {}
    airline = _text(_node(data, "general", "icao_airline"))
    number = _text(_node(data, "general", "flight_number"))
    altitude = _text(_node(data, "general", "initial_altitude"))
    plan = Plan(
        callsign=_first(_node(data, "atc", "callsign"), airline + number if airline and number else "", _node(data, "aircraft", "reg")),
        aircraft=_text(_node(data, "aircraft", "icaocode")),
        origin=_text(_node(data, "origin", "icao_code")).upper(),
        destination=_text(_node(data, "destination", "icao_code")).upper(),
        alternate=_text(_node(alternate, "icao_code")).upper(),
        cruise_ft=int(float(altitude)) if altitude.replace(".", "", 1).isdigit() else 0,
        route=_first(_node(data, "general", "route"), _node(data, "atc", "route")),
        sid=_text(_node(data, "general", "sid_ident")),
        star=_text(_node(data, "general", "star_ident")),
        origin_runway=_text(_node(data, "origin", "plan_rwy")),
        destination_runway=_text(_node(data, "destination", "plan_rwy")),
    )
    if not plan.origin or not plan.destination:
        raise ValueError("SimBrief: the plan has no origin or destination")
    return plan


def fetch(user):
    key = "userid" if user.isdigit() else "username"
    query = urllib.parse.urlencode({key: user, "client": "atc", "json": "v2"})
    try:
        with urllib.request.urlopen(URL.format(query=query), timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        raise ValueError(f"SimBrief: no plan found for {user} (HTTP {e.code})") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise ValueError(f"SimBrief: could not read the plan ({e})") from e


def load(user):
    return parse(fetch(user))
