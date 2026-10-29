import heapq
from dataclasses import dataclass
from functools import cache

from atc.data.airports import FT_PER_NM
from atc.geo import range_bearing

MAX_START_NM = 0.5


@dataclass(frozen=True, slots=True, eq=False)
class Graph:
    adj: dict
    runway_nodes: dict


@dataclass(frozen=True, slots=True)
class Route:
    taxiways: tuple
    crossings: tuple
    runway: str
    distance_ft: int


@cache
def graph(airport):
    nodes = airport.nodes
    adj, runway_nodes = {}, {}
    for e in airport.edges:
        if e.a not in nodes or e.b not in nodes:
            continue
        if e.runway:
            runway_nodes.setdefault(e.a, set()).add(e.name)
            runway_nodes.setdefault(e.b, set()).add(e.name)
            continue
        nm = range_bearing(*nodes[e.a], *nodes[e.b])[0]
        adj.setdefault(e.a, []).append((e.b, nm, e.name))
        if not e.oneway:
            adj.setdefault(e.b, []).append((e.a, nm, e.name))
    return Graph(
        {k: tuple(v) for k, v in adj.items()},
        {k: frozenset(v) for k, v in runway_nodes.items()},
    )


def _nearest(airport, g, lat, lon):
    best = min(g.adj, key=lambda n: range_bearing(lat, lon, *airport.nodes[n])[0], default=None)
    if best is None or range_bearing(lat, lon, *airport.nodes[best])[0] > MAX_START_NM:
        raise ValueError("position is not on the airport surface")
    return best


def _ramp(airport, text, lat, lon):
    text = text.strip().lower()
    exact = [r for r in airport.ramps if r.name.lower() == text]
    found = exact or [r for r in airport.ramps if text in r.name.lower()]
    if not found:
        raise ValueError(f"unknown parking {text}")
    return min(found, key=lambda r: range_bearing(lat, lon, r.lat, r.lon)[0])


def _entry(airport, g, end):
    candidates = [
        n
        for n, names in g.runway_nodes.items()
        if n in g.adj and any(end.name in name.split("/") for name in names)
    ]
    if not candidates:
        raise ValueError(f"no taxi access to runway {end.name}")
    return min(candidates, key=lambda n: range_bearing(end.lat, end.lon, *airport.nodes[n])[0])


def _path(g, start, goal):
    best = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    while heap:
        d, n = heapq.heappop(heap)
        if n == goal:
            break
        if d > best[n]:
            continue
        for m, w, name in g.adj.get(n, ()):
            nd = d + w
            if nd < best.get(m, float("inf")):
                best[m] = nd
                prev[m] = (n, name)
                heapq.heappush(heap, (nd, m))
    if goal not in best:
        return None
    hops = []
    n = goal
    while n != start:
        p, name = prev[n]
        hops.append((n, name))
        n = p
    hops.reverse()
    return best[goal], hops


def plan(airport, lat, lon, origin, destination):
    g = graph(airport)
    if origin.strip():
        ramp = _ramp(airport, origin, lat, lon)
        lat, lon = ramp.lat, ramp.lon
    start = _nearest(airport, g, lat, lon)
    end = airport.runway_end(destination) if destination[:1].isdigit() else None
    if end:
        goal, runway = _entry(airport, g, end), end.name
    else:
        ramp = _ramp(airport, destination, lat, lon)
        goal, runway = _nearest(airport, g, ramp.lat, ramp.lon), ""
    found = _path(g, start, goal)
    if found is None:
        raise ValueError("no taxi route")
    nm, hops = found
    taxiways, crossings = [], []
    for node, name in hops:
        if name and (not taxiways or taxiways[-1] != name):
            taxiways.append(name)
        if node != goal:
            for rwy in sorted(g.runway_nodes.get(node, ())):
                if not crossings or crossings[-1] != rwy:
                    crossings.append(rwy)
    return Route(tuple(taxiways), tuple(crossings), runway, round(nm * FT_PER_NM))
