import asyncio
import math
import re
import time
from dataclasses import dataclass

from atc import notes as flight_notes
from atc.data import taxi
from atc.data.airports import FT_PER_NM
from atc.geo import range_bearing
from atc.state.models import Position

HOLD_SHORT_FT = 400
STOPPED_KT = 3
LANDED_KT = 30
CLIMB_AGL_FT = 500
TOWER_AREA_NM = 10
CENTER_NM = 30
APPROACH_NM = 40
FINAL_HANDOFF_NM = 8
FINAL_HANDOFF_AGL_FT = 3500
DEVIATION_FT = 300
DEVIATION_FPM = 200
DEVIATION_SECONDS = 15
DEVIATION_MIN_AGL_FT = 1000
READBACK_SECONDS = (20, 50)
RUNWAY_AREA_NM = 10
FINAL_NM = 4
FINAL_CROSS_NM = 0.4
FINAL_AGL_FT = 2500
RUNWAY_CROSS_NM = 0.03
ASSIGNED = re.compile(r"\b(?:maintain|altitude)\s+(FL)?(\d{3,5})\b", re.I)


@dataclass(frozen=True, slots=True)
class Event:
    key: str
    text: str


def _freq(airport, role):
    return ", ".join(f"{k / 1000:.3f}" for k in airport.frequencies.get(role, ())) or "unknown"


def _frame(end, lat, lon):
    x = (lon - end.lon) * 60 * math.cos(math.radians(end.lat))
    y = (lat - end.lat) * 60
    h = math.radians(end.heading)
    return x * math.sin(h) + y * math.cos(h), x * math.cos(h) - y * math.sin(h)


def _on_runway(end, length_nm, craft):
    along, cross = _frame(end, craft.lat, craft.lon)
    return craft.on_ground and -0.05 <= along <= length_nm + 0.05 and abs(cross) <= RUNWAY_CROSS_NM


def _final_distance(end, airport, craft):
    along, cross = _frame(end, craft.lat, craft.lon)
    low = craft.alt_msl_ft - airport.elevation_ft < FINAL_AGL_FT
    if not craft.on_ground and low and -FINAL_NM <= along < 0 and abs(cross) <= FINAL_CROSS_NM:
        return -along
    return None


def _name(craft):
    return craft.callsign or getattr(craft, "id", "") or "the aircraft"


def _assigned(notes):
    for line in reversed(notes.clearances):
        match = ASSIGNED.search(line)
        if match:
            return int(match[2]) * (100 if match[1] else 1)
    return None


class Watcher:
    __slots__ = ("_tracker", "_store", "_notes_path", "_scope", "_active", "_since", "_touched", "_airborne")

    def __init__(self, tracker, store, notes_path, scope):
        self._tracker = tracker
        self._store = store
        self._notes_path = notes_path
        self._scope = scope
        self._active = set()
        self._since = {}
        self._touched = set()
        self._airborne = False

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        self._touched = set()
        position = self._tracker.resolve()
        snap = self._store.snapshot()
        a = snap.aircraft
        landed = a.on_ground and self._airborne and a.ground_speed_kt < LANDED_KT
        found = {}
        airports = self._scope()
        if position is not None and airports:
            notes = flight_notes.load(self._notes_path)
            for source in (
                self._handoffs(snap, airports, landed),
                self._deviation(snap, notes, now),
                self._readbacks(notes, now),
                self._runways(snap, airports),
            ):
                found.update(source)
        if not a.on_ground and a.alt_agl_ft > 50:
            self._airborne = True
        elif landed:
            self._airborne = False
        self._since = {k: v for k, v in self._since.items() if k in self._touched}
        new = [Event(k, t) for k, t in found.items() if k not in self._active]
        self._active = set(found)
        return new

    def _held(self, key, condition, now, seconds):
        if not condition:
            return False
        self._touched.add(key)
        start = self._since.setdefault(key, now)
        return now - start >= seconds

    def _handoffs(self, snap, airports, landed):
        a, position = snap.aircraft, snap.position
        airport, nm = min(
            ((ap, range_bearing(a.lat, a.lon, ap.lat, ap.lon)[0]) for ap in airports),
            key=lambda r: r[1],
        )
        dest = airports[-1]
        dest_nm = range_bearing(a.lat, a.lon, dest.lat, dest.lon)[0]
        if position is Position.GROUND and a.on_ground and a.ground_speed_kt < STOPPED_KT:
            g = taxi.graph(airport)
            near = min(
                (
                    (range_bearing(a.lat, a.lon, *airport.nodes[n])[0] * FT_PER_NM, n)
                    for n in g.runway_nodes
                    if n in g.adj
                ),
                default=None,
            )
            if near and near[0] <= HOLD_SHORT_FT:
                runways = "/".join(sorted(g.runway_nodes[near[1]]))
                yield (
                    f"handoff:hold:{runways}",
                    f"The aircraft has stopped {near[0]:.0f} ft from runway {runways}. If this is its "
                    f"assigned runway, hand it off to tower on {_freq(airport, 'tower')}.",
                )
        elif position is Position.TOWER:
            if landed:
                yield (
                    "handoff:landed",
                    f"The aircraft has landed and slowed to {a.ground_speed_kt:.0f} knots. Give exit and "
                    f"taxi instructions and hand it off to ground on {_freq(airport, 'ground')}.",
                )
            elif (
                not a.on_ground
                and a.alt_agl_ft > CLIMB_AGL_FT
                and a.vertical_speed_fpm > 0
                and nm < TOWER_AREA_NM
            ):
                yield (
                    "handoff:departure",
                    f"The aircraft is airborne {a.alt_agl_ft:.0f} ft above ground and climbing. Hand it "
                    f"off to departure on {_freq(airport, 'departure')}.",
                )
        elif position is Position.DEPARTURE and not a.on_ground and nm > CENTER_NM:
            yield (
                "handoff:center",
                f"The aircraft is {nm:.0f} nm from {airport.icao} and leaving departure airspace. "
                "Hand it off to center.",
            )
        elif position is Position.CENTER and not a.on_ground and dest_nm < APPROACH_NM:
            yield (
                "handoff:approach",
                f"The aircraft is {dest_nm:.0f} nm from {dest.icao}. Hand it off to approach on "
                f"{_freq(dest, 'approach')}.",
            )
        elif (
            position is Position.APPROACH
            and not a.on_ground
            and dest_nm < FINAL_HANDOFF_NM
            and a.alt_agl_ft < FINAL_HANDOFF_AGL_FT
        ):
            yield (
                "handoff:final",
                f"The aircraft is {dest_nm:.1f} nm from {dest.icao} at {a.alt_agl_ft:.0f} ft above "
                f"ground. If it is established on final, hand it off to tower on {_freq(dest, 'tower')}.",
            )

    def _deviation(self, snap, notes, now):
        a = snap.aircraft
        assigned = _assigned(notes)
        if assigned is None or a.on_ground or a.alt_agl_ft < DEVIATION_MIN_AGL_FT:
            return
        error = a.alt_msl_ft - assigned
        toward = abs(a.vertical_speed_fpm) >= DEVIATION_FPM and a.vertical_speed_fpm * error < 0
        key = f"altitude:{assigned}"
        if self._held(key, abs(error) > DEVIATION_FT and not toward, now, DEVIATION_SECONDS):
            side = "above" if error > 0 else "below"
            yield (
                key,
                f"Altitude deviation: assigned {assigned} ft, the aircraft is at {a.alt_msl_ft:.0f} ft, "
                f"{abs(error):.0f} ft {side}, vertical speed {a.vertical_speed_fpm:.0f} fpm. Query the pilot.",
            )

    def _readbacks(self, notes, now):
        for line in notes.readbacks:
            for i, seconds in enumerate(READBACK_SECONDS):
                key = f"readback{i}:{line}"
                if self._held(key, True, now, seconds):
                    yield key, f"No readback has been received for: {line}. Ask the pilot to read it back."

    def _runways(self, snap, airports):
        a = snap.aircraft
        if snap.position not in (Position.TOWER, Position.APPROACH):
            return
        for airport in airports:
            if range_bearing(a.lat, a.lon, airport.lat, airport.lon)[0] > RUNWAY_AREA_NM:
                continue
            for runway in airport.runways:
                length_nm = runway.length_ft / FT_PER_NM
                for end in runway.ends:
                    out = _final_distance(end, airport, a)
                    if out is not None and a.vertical_speed_fpm <= DEVIATION_FPM:
                        busy = [t for t in snap.traffic if _on_runway(end, length_nm, t)]
                        if busy:
                            who = ", ".join(_name(t) for t in busy)
                            yield (
                                f"runway:{end.name}:occupied",
                                f"Runway {end.name} is occupied by {who} while the aircraft is {out:.1f} nm "
                                "out on final. If it is not clear, send the aircraft around.",
                            )
                    if _on_runway(end, length_nm, a):
                        for t in snap.traffic:
                            out = _final_distance(end, airport, t)
                            if out is not None:
                                yield (
                                    f"runway:{end.name}:traffic",
                                    f"{_name(t)} is {out:.1f} nm out on final for runway {end.name} while the "
                                    f"aircraft is still on the runway. Clear the runway or send {_name(t)} around.",
                                )


async def watch(watcher, turn, interval=1.0):
    while True:
        try:
            for event in watcher.poll():
                await turn(event=event.text)
        except Exception as e:
            print(f"[watcher error: {e!r}]")
        await asyncio.sleep(interval)
