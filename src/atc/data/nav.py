from dataclasses import dataclass
from functools import cache

from atc.data import default_data
from atc.geo import range_bearing

KINDS = ("SID", "STAR", "APPCH")
SIDES = {"L": "left", "R": "right"}


@dataclass(frozen=True, slots=True)
class Fix:
    ident: str
    lat: float
    lon: float
    area: str
    region: str
    kind: str


@dataclass(frozen=True, slots=True)
class Leg:
    seq: int
    fix: str
    region: str
    path: str
    text: str


@dataclass(frozen=True, slots=True)
class Procedure:
    kind: str
    name: str
    transitions: dict


@cache
def _points():
    base = default_data()
    points = {}
    for line in (base / "earth_fix.dat").read_text(errors="ignore").splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        try:
            lat, lon = float(p[0]), float(p[1])
        except ValueError:
            continue
        points.setdefault(p[2], []).append(Fix(p[2], lat, lon, p[3], p[4], "fix"))
    for line in (base / "earth_nav.dat").read_text(errors="ignore").splitlines():
        p = line.split()
        if len(p) < 10 or p[0] not in ("2", "3"):
            continue
        points.setdefault(p[7], []).append(
            Fix(p[7], float(p[1]), float(p[2]), p[8], p[9], "vor" if p[0] == "3" else "ndb")
        )
    return points


def locate(ident, region="", near=None):
    found = _points().get(ident.upper(), ())
    if region:
        found = [f for f in found if f.region == region] or found
    if not found:
        return None
    if near:
        return min(found, key=lambda f: range_bearing(near[0], near[1], f.lat, f.lon)[0])
    return found[0]


def _altitude(value):
    value = value.strip()
    if not value:
        return ""
    return value if value.startswith("FL") else str(int(value))


def _text(f):
    bits = [f[4] or "-", f[11]]
    if f[9]:
        bits.append(SIDES.get(f[9], f[9]))
    if f[20]:
        bits.append(f"course {int(f[20]) / 10:.0f}")
    if f[21] and f[11] in ("CF", "FC", "FD"):
        bits.append(f"{int(f[21]) / 10:.1f}nm")
    high, low = _altitude(f[23]), _altitude(f[24])
    if high:
        if f[22] == "+":
            bits.append(f"at or above {high}")
        elif f[22] == "-":
            bits.append(f"at or below {high}")
        elif f[22] == "B" and low:
            bits.append(f"between {low} and {high}")
        else:
            bits.append(f"at {high}")
    if f[27].strip():
        word = {"-": "max speed", "+": "min speed"}.get(f[26], "speed")
        bits.append(f"{word} {f[27].strip()}")
    return " ".join(bits)


@cache
def procedures(icao):
    path = default_data() / "CIFP" / f"{icao.upper()}.dat"
    if not path.is_file():
        return {kind: {} for kind in KINDS}
    raw = {kind: {} for kind in KINDS}
    for line in path.read_text(errors="ignore").splitlines():
        kind, _, rest = line.partition(":")
        if kind not in raw:
            continue
        f = [x.strip() for x in rest.rstrip(";").split(",")]
        if len(f) < 29:
            continue
        leg = Leg(int(f[0]), f[4], f[5], f[11], _text(f))
        raw[kind].setdefault(f[2], {}).setdefault(f[3], []).append(leg)
    return {
        kind: {
            name: Procedure(
                kind, name, {t: tuple(sorted(legs, key=lambda l: l.seq)) for t, legs in trans.items()}
            )
            for name, trans in names.items()
        }
        for kind, names in raw.items()
    }
