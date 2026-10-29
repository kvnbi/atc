from atc.data import centers
from atc.state.models import Position

ROLES = (
    ("tower", Position.TOWER),
    ("ground", Position.GROUND),
    ("clearance", Position.CLEARANCE),
    ("departure", Position.DEPARTURE),
    ("approach", Position.APPROACH),
)


def position_for(airports, khz, lat=None, lon=None):
    for airport in airports:
        for role, position in ROLES:
            if khz in airport.frequencies.get(role, ()):
                return position
    if lat is not None and khz == centers.frequency(lat, lon):
        return Position.CENTER
    return None


class Tracker:
    __slots__ = ("_store", "_scope", "fixed")

    def __init__(self, store, scope, fixed=None):
        self._store = store
        self._scope = scope
        self.fixed = fixed

    def resolve(self):
        if self.fixed is not None:
            position = Position(self.fixed)
        else:
            a = self._store.snapshot().aircraft
            position = position_for(self._scope(), a.com1_khz, a.lat, a.lon)
        self._store.set_position(position)
        return position
