from dataclasses import dataclass, replace

from atc.state.models import Aircraft, Position, Traffic


@dataclass(frozen=True, slots=True)
class Snapshot:
    aircraft: Aircraft
    traffic: tuple[Traffic, ...]
    position: Position


class StateStore:
    __slots__ = ("_aircraft", "_traffic", "_position", "_snapshot")

    def __init__(self):
        self._aircraft = Aircraft()
        self._traffic = ()
        self._position = Position.CLEARANCE
        self._snapshot = None

    def set_aircraft(self, aircraft):
        self._aircraft = aircraft
        self._snapshot = None

    def update_aircraft(self, **fields):
        self._aircraft = replace(self._aircraft, **fields)
        self._snapshot = None

    def set_traffic(self, traffic):
        self._traffic = tuple(traffic)
        self._snapshot = None

    def set_position(self, position):
        position = Position(position)
        if position is not self._position:
            self._position = position
            self._snapshot = None

    def snapshot(self):
        if self._snapshot is None:
            self._snapshot = Snapshot(self._aircraft, self._traffic, self._position)
        return self._snapshot
