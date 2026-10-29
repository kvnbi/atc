import re
import time
import urllib.request
from math import cos, radians, sin
from statistics import median

URL = "https://aviationweather.gov/api/data/metar?ids={}&format=raw"
TTL = 300
_cache = {}
_WIND = re.compile(r"\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b")
_ALTIMETER = re.compile(r"\b(A|Q)(\d{4})\b")


def fetch(icao):
    icao = icao.upper()
    now = time.monotonic()
    hit = _cache.get(icao)
    if hit and now - hit[0] < TTL:
        return hit[1]
    request = urllib.request.Request(URL.format(icao), headers={"User-Agent": "atc"})
    with urllib.request.urlopen(request, timeout=5) as response:
        text = response.read().decode().strip()
    if not text:
        raise ValueError(f"no METAR for {icao}")
    metar = text.splitlines()[0]
    _cache[icao] = (now, metar)
    return metar


def parse(metar):
    out = {"metar": metar}
    wind = _WIND.search(metar)
    if wind:
        out["wind_true"] = None if wind[1] == "VRB" else int(wind[1])
        out["wind_kt"] = int(wind[2])
        if wind[3]:
            out["gust_kt"] = int(wind[3])
    altimeter = _ALTIMETER.search(metar)
    if altimeter:
        unit, value = altimeter.groups()
        out["altimeter"] = f"{int(value) / 100:.2f} inHg" if unit == "A" else f"{int(value)} hPa"
    return out


def variation(airport):
    offsets = [
        (end.heading - int(end.name[:2]) * 10 + 180) % 360 - 180
        for runway in airport.runways
        for end in runway.ends
        if end.name[:2].isdigit()
    ]
    return median(offsets) if offsets else 0.0


def rank(airport, direction, speed):
    rows = []
    for runway in airport.runways:
        for end in runway.ends:
            angle = radians(direction - end.heading)
            rows.append(
                {
                    "runway": end.name,
                    "headwind_kt": round(speed * cos(angle)),
                    "crosswind_kt": round(abs(speed * sin(angle))),
                }
            )
    rows.sort(key=lambda r: -r["headwind_kt"])
    return rows[:4]
