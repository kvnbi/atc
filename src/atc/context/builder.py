from atc import notes as flight_notes
from atc import spoken
from atc.context.system import system_prompt
from atc.geo import range_bearing

MAX_TRAFFIC = 5
LOG_LINES = 12


def _freq(khz):
    return f"{khz / 1000:.3f}" if khz else "none"


def _aircraft(a):
    return (
        f"Aircraft {a.callsign or 'unknown'}: lat {a.lat:.4f} lon {a.lon:.4f}, "
        f"{a.alt_msl_ft:.0f} ft MSL ({a.alt_agl_ft:.0f} ft AGL), heading {a.heading_deg:.0f}, "
        f"IAS {a.ias_kt:.0f} kt, ground speed {a.ground_speed_kt:.0f} kt, "
        f"vertical speed {a.vertical_speed_fpm:.0f} fpm, "
        f"{'on ground' if a.on_ground else 'airborne'}, gear {'down' if a.gear_down else 'up'}, "
        f"flaps {a.flap_ratio:.0%}, squawk {a.squawk:04d}"
    )


def _traffic(aircraft, traffic):
    rows = []
    for t in traffic:
        nm, brg = range_bearing(aircraft.lat, aircraft.lon, t.lat, t.lon)
        rows.append((nm, brg, t))
    rows.sort(key=lambda r: r[0])
    lines = [
        f"- {t.callsign or t.id}: {nm:.1f} nm, bearing {brg:03.0f}, {t.alt_msl_ft:.0f} ft, "
        f"heading {t.heading_deg:03.0f}, {t.ground_speed_kt:.0f} kt, "
        f"{'ground' if t.on_ground else 'air'}"
        for nm, brg, t in rows[:MAX_TRAFFIC]
    ]
    return "Traffic (nearest first):\n" + "\n".join(lines) if lines else "Traffic: none. Never mention traffic."


def _notes(notes):
    lines = []
    for name in flight_notes.NAMES:
        items = getattr(notes, name)[-LOG_LINES:] if name == "log" else getattr(notes, name)
        if items:
            lines.append(f"{name.capitalize()}:")
            lines += [f"- {item}" for item in items]
    return "Flight notes:\n" + "\n".join(lines) if lines else "Flight notes: empty"


class ContextBuilder:
    __slots__ = ("_system",)

    def __init__(self, flight_plan=""):
        self._system = [system_prompt()]
        if flight_plan:
            self._system.append(f"Flight plan\n{flight_plan.strip()}")

    def build(self, snapshot, notes, call=None, event=None, weather="", hint=""):
        if not (call or event):
            raise ValueError("call or event required")
        callsign = snapshot.aircraft.callsign
        parts = [
            f"Position: {snapshot.position.value}, tuned frequency {_freq(snapshot.aircraft.com1_khz)}",
            *([f"Callsign to speak: {spoken.callsign(callsign)}"] if callsign else []),
            _aircraft(snapshot.aircraft),
            _traffic(snapshot.aircraft, snapshot.traffic),
        ]
        if weather:
            parts.append(f"Weather\n{weather.strip()}")
        if hint:
            parts.append(hint)
        parts.append(_notes(notes))
        parts.append(f'Pilot: "{call.strip()}"' if call else f"Event: {event.strip()}")
        return list(self._system), [{"role": "user", "content": "\n\n".join(parts)}]
