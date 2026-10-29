from math import atan2, cos, degrees, hypot, radians


def range_bearing(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * 60.0
    dx = (lon2 - lon1) * 60.0 * cos(radians((lat1 + lat2) / 2))
    return hypot(dx, dy), degrees(atan2(dx, dy)) % 360
