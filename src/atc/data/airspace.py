from dataclasses import dataclass
from functools import cache

from atc.data import default_data


@dataclass(frozen=True, slots=True, eq=False)
class Airspace:
    cls: str
    name: str
    floor: int
    ceiling: int
    points: tuple
    bbox: tuple


def _altitude(text):
    words = text.upper().split()
    if not words or words[0] in ("GND", "SFC"):
        return 0
    word = words[0]
    if word in ("UNLIM", "UNL"):
        return 99999
    if word.startswith("FL"):
        return int(word[2:]) * 100
    try:
        return int(word)
    except ValueError:
        return 0


def _degrees(text, hemisphere):
    d, m, s = text.split(":")
    value = int(d) + int(m) / 60 + int(s) / 3600
    return -value if hemisphere in "SW" else value


def _inside(lat, lon, points):
    inside = False
    j = len(points) - 1
    for i, (yi, xi) in enumerate(points):
        yj, xj = points[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@cache
def airspaces():
    found = []
    cls = name = ""
    floor = ceiling = 0
    points = []

    def flush():
        if len(points) >= 3:
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            found.append(
                Airspace(
                    cls,
                    name,
                    floor,
                    ceiling,
                    tuple(points),
                    (min(lats), max(lats), min(lons), max(lons)),
                )
            )

    for line in (default_data() / "airspaces" / "airspace.txt").read_text(errors="ignore").splitlines():
        tag = line[:2]
        if tag == "DP":
            p = line.split()
            points.append((_degrees(p[1], p[2]), _degrees(p[3], p[4])))
        elif tag == "AC":
            flush()
            cls, name, floor, ceiling, points = line[3:].strip(), "", 0, 0, []
        elif tag == "AN":
            name = line[3:].strip()
        elif tag == "AL":
            floor = _altitude(line[3:])
        elif tag == "AH":
            ceiling = _altitude(line[3:])
    flush()
    return tuple(found)


def at(lat, lon, altitude_ft):
    return [
        a
        for a in airspaces()
        if a.floor <= altitude_ft <= a.ceiling
        and a.bbox[0] <= lat <= a.bbox[1]
        and a.bbox[2] <= lon <= a.bbox[3]
        and _inside(lat, lon, a.points)
    ]
