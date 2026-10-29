import math

SECTOR_DEGREES = 2.0
BASE_KHZ = 125000
SLOTS = 440
STEP_KHZ = 25


def sector(lat, lon):
    return math.floor(lat / SECTOR_DEGREES), math.floor(lon / SECTOR_DEGREES)


def frequency(lat, lon):
    row, col = sector(lat, lon)
    return BASE_KHZ + (row * 37 + col * 101) % SLOTS * STEP_KHZ
