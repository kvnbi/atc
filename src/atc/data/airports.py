import mmap
from dataclasses import dataclass
from functools import cache

from atc.config import get_settings
from atc.geo import range_bearing

FT_PER_NM = 6076.12
HEADERS = (b"\n1 ", b"\n16 ", b"\n17 ")
ROLES = ("atis", "unicom", "clearance", "ground", "tower", "approach", "departure")
FREQ_CODES = {
    **{str(1050 + i): (role, 1) for i, role in enumerate(ROLES)},
    **{str(50 + i): (role, 10) for i, role in enumerate(ROLES)},
}


@dataclass(frozen=True, slots=True)
class RunwayEnd:
    name: str
    lat: float
    lon: float
    heading: float


@dataclass(frozen=True, slots=True)
class Runway:
    ends: tuple
    width_m: float
    length_ft: int


@dataclass(frozen=True, slots=True)
class Edge:
    a: int
    b: int
    oneway: bool
    runway: bool
    name: str


@dataclass(frozen=True, slots=True)
class Ramp:
    lat: float
    lon: float
    heading: float
    kind: str
    name: str


@dataclass(frozen=True, slots=True, eq=False)
class Airport:
    icao: str
    name: str
    elevation_ft: float
    lat: float
    lon: float
    transition_alt: int
    runways: tuple
    frequencies: dict
    nodes: dict
    edges: tuple
    ramps: tuple

    def runway_end(self, name):
        name = _rwy(name)
        for runway in self.runways:
            for end in runway.ends:
                if end.name == name:
                    return end
        return None


def _rwy(name):
    name = name.upper()
    return "0" + name if name[0].isdigit() and not name[1:2].isdigit() else name


@cache
def _sources():
    root = get_settings().xplane_dir
    glob = root / "Global Scenery" / "Global Airports" / "Earth nav data" / "apt.dat"
    found = []
    ini = root / "Custom Scenery" / "scenery_packs.ini"
    if ini.is_file():
        for line in ini.read_text(errors="ignore").splitlines():
            if not line.startswith("SCENERY_PACK "):
                continue
            pack = line[13:].strip()
            if pack == "*GLOBAL_AIRPORTS*":
                found.append(glob)
                continue
            path = root / pack / "Earth nav data" / "apt.dat"
            if path.is_file():
                found.append(path)
    if glob not in found:
        found.append(glob)
    return tuple(p for p in found if p.is_file() and p.stat().st_size)


def _block(path, icao):
    needle = f" {icao} ".encode()
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        pos = mm.find(needle)
        while pos != -1:
            start = mm.rfind(b"\n", 0, pos) + 1
            end = mm.find(b"\n", pos)
            parts = mm[start:end].split(None, 5)
            if len(parts) > 4 and parts[0] in (b"1", b"16", b"17") and parts[4] == icao.encode():
                stops = [i for i in (mm.find(h, end) for h in HEADERS) if i != -1]
                return mm[start : min(stops) if stops else len(mm)]
            pos = mm.find(needle, pos + 1)
    return None


def _parse(raw):
    rows = raw.decode("utf-8", "ignore").splitlines()
    head = rows[0].split(None, 5)
    meta, runways, nodes, edges, ramps, freqs = {}, [], {}, [], [], {}
    for row in rows[1:]:
        p = row.split()
        if not p:
            continue
        code = p[0]
        if code == "100" and len(p) >= 20:
            ends = [(_rwy(p[8]), float(p[9]), float(p[10])), (_rwy(p[17]), float(p[18]), float(p[19]))]
            nm, bearing = range_bearing(ends[0][1], ends[0][2], ends[1][1], ends[1][2])
            headings = (bearing, (bearing + 180) % 360)
            runways.append(
                Runway(
                    tuple(RunwayEnd(n, la, lo, h) for (n, la, lo), h in zip(ends, headings)),
                    float(p[1]),
                    round(nm * FT_PER_NM),
                )
            )
        elif code == "1302" and len(p) > 2:
            meta[p[1]] = " ".join(p[2:])
        elif code == "1201":
            nodes[int(p[4])] = (float(p[1]), float(p[2]))
        elif code == "1202" and len(p) > 4:
            edges.append(Edge(int(p[1]), int(p[2]), p[3] == "oneway", p[4] == "runway", " ".join(p[5:])))
        elif code == "1300" and len(p) > 5:
            ramps.append(Ramp(float(p[1]), float(p[2]), float(p[3]), p[4], " ".join(p[6:])))
        elif code in FREQ_CODES and len(p) > 1:
            role, mult = FREQ_CODES[code]
            freqs.setdefault(role, set()).add(int(p[1]) * mult)
    if "datum_lat" in meta:
        lat, lon = float(meta["datum_lat"]), float(meta["datum_lon"])
    elif runways:
        lat, lon = runways[0].ends[0].lat, runways[0].ends[0].lon
    else:
        lat = lon = 0.0
    try:
        transition = int(meta.get("transition_alt", 0))
    except ValueError:
        transition = 0
    return Airport(
        head[4],
        head[5] if len(head) > 5 else "",
        float(head[1]),
        lat,
        lon,
        transition,
        tuple(runways),
        {role: tuple(sorted(values)) for role, values in freqs.items()},
        nodes,
        tuple(edges),
        tuple(ramps),
    )


@cache
def find(icao):
    icao = icao.upper()
    for path in _sources():
        raw = _block(path, icao)
        if raw:
            return _parse(raw)
    return None
