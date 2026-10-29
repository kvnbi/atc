from atc.state.models import Position

ROLES = (
    ("tower", Position.TOWER),
    ("ground", Position.GROUND),
    ("clearance", Position.CLEARANCE),
    ("departure", Position.DEPARTURE),
    ("approach", Position.APPROACH),
)


def position_for(airports, khz):
    for airport in airports:
        for role, position in ROLES:
            if khz in airport.frequencies.get(role, ()):
                return position
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
            position = position_for(self._scope(), self._store.snapshot().aircraft.com1_khz)
        self._store.set_position(position)
        return position
