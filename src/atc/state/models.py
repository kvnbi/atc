from dataclasses import dataclass
from enum import StrEnum


class Position(StrEnum):
    CLEARANCE = "clearance"
    GROUND = "ground"
    TOWER = "tower"
    DEPARTURE = "departure"
    CENTER = "center"
    APPROACH = "approach"


@dataclass(frozen=True, slots=True)
class Aircraft:
    callsign: str = ""
    time: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    alt_msl_ft: float = 0.0
    alt_agl_ft: float = 0.0
    heading_deg: float = 0.0
    ias_kt: float = 0.0
    ground_speed_kt: float = 0.0
    vertical_speed_fpm: float = 0.0
    on_ground: bool = True
    gear_down: bool = True
    flap_ratio: float = 0.0
    squawk: int = 0
    com1_khz: int = 0


@dataclass(frozen=True, slots=True)
class Traffic:
    id: str
    callsign: str = ""
    lat: float = 0.0
    lon: float = 0.0
    alt_msl_ft: float = 0.0
    heading_deg: float = 0.0
    ground_speed_kt: float = 0.0
    on_ground: bool = False
