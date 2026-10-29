import asyncio
import math
import struct
import time

from atc.state.models import Traffic

M_TO_FT = 3.28084
MS_TO_KT = 1.943844
FPM_PER_MS = 196.85
TARGETS = 20
CALLSIGN_CHARS = 7
OWN_HZ, TRAFFIC_HZ, CALLSIGN_HZ = 5, 2, 1
RESEND_SECONDS = 5.0
STALE_SECONDS = 3.0

OWN = (
    ("sim/flightmodel/position/latitude", "lat", float),
    ("sim/flightmodel/position/longitude", "lon", float),
    ("sim/flightmodel/position/elevation", "alt_msl_ft", lambda v: v * M_TO_FT),
    ("sim/flightmodel/position/y_agl", "alt_agl_ft", lambda v: v * M_TO_FT),
    ("sim/flightmodel/position/true_psi", "heading_deg", float),
    ("sim/flightmodel/position/indicated_airspeed", "ias_kt", float),
    ("sim/flightmodel/position/groundspeed", "ground_speed_kt", lambda v: v * MS_TO_KT),
    ("sim/flightmodel/position/vh_ind_fpm", "vertical_speed_fpm", float),
    ("sim/flightmodel/failures/onground_any", "on_ground", lambda v: v > 0.5),
    ("sim/cockpit/switches/gear_handle_status", "gear_down", lambda v: v > 0.5),
    ("sim/cockpit2/controls/flap_handle_request_ratio", "flap_ratio", float),
    ("sim/cockpit/radios/transponder_code", "squawk", lambda v: int(round(v))),
    ("sim/cockpit2/radios/actuators/com1_frequency_hz_833", "com1_khz", lambda v: int(round(v))),
)
TARGET_FIELDS = ("lat", "lon", "ele", "psi", "V_msc", "vertical_speed", "weight_on_wheels")
TARGET_BASE = "sim/cockpit2/tcas/targets"


class XPlane(asyncio.DatagramProtocol):
    def __init__(self, host="127.0.0.1", port=49000, listen_port=49001):
        self._address = (host, port)
        self._listen_port = listen_port
        self._transport = None
        self._store = None
        self._last = float("-inf")
        self._values = {}
        self._specs = []
        self._own = {}
        self._slots = {}
        for name, field, convert in OWN:
            self._own[len(self._specs)] = (field, convert)
            self._specs.append((name, OWN_HZ))
        for slot in range(1, TARGETS + 1):
            ids = {}
            for field in TARGET_FIELDS:
                ids[field] = len(self._specs)
                self._specs.append((f"{TARGET_BASE}/position/{field}[{slot}]", TRAFFIC_HZ))
            ids["chars"] = []
            for k in range(CALLSIGN_CHARS):
                ids["chars"].append(len(self._specs))
                self._specs.append((f"{TARGET_BASE}/flight_id[{slot * 8 + k}]", CALLSIGN_HZ))
            self._slots[slot] = ids

    @property
    def connected(self):
        return time.monotonic() - self._last < STALE_SECONDS

    @property
    def port(self):
        return self._transport.get_extra_info("sockname")[1]

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, addr):
        if data[:5] != b"RREF,":
            return
        body = data[5 : 5 + (len(data) - 5) // 8 * 8]
        for index, value in struct.iter_unpack("<if", body):
            self._values[index] = value
        self._last = time.monotonic()
        if self._store:
            self._apply()

    def _subscribe(self, on):
        for index, (name, hz) in enumerate(self._specs):
            packet = struct.pack("<4sxii400s", b"RREF", hz if on else 0, index, name.encode())
            self._transport.sendto(packet, self._address)

    def _apply(self):
        fields = {
            field: convert(self._values[i])
            for i, (field, convert) in self._own.items()
            if i in self._values
        }
        if fields:
            self._store.update_aircraft(time=time.time(), **fields)
        self._store.set_traffic(self._traffic())

    def _callsign(self, ids):
        chars = []
        for i in ids["chars"]:
            code = int(self._values.get(i, 0))
            if code <= 0:
                break
            chars.append(chr(code))
        return "".join(chars).strip()

    def _traffic(self):
        found = []
        for slot, ids in self._slots.items():
            v = {field: self._values.get(ids[field]) for field in TARGET_FIELDS}
            if v["lat"] is None or v["lon"] is None or (v["lat"] == 0 and v["lon"] == 0):
                continue
            total = v["V_msc"] or 0.0
            climb = (v["vertical_speed"] or 0.0) / FPM_PER_MS
            found.append(
                Traffic(
                    id=f"t{slot}",
                    callsign=self._callsign(ids),
                    lat=v["lat"],
                    lon=v["lon"],
                    alt_msl_ft=(v["ele"] or 0.0) * M_TO_FT,
                    heading_deg=v["psi"] or 0.0,
                    ground_speed_kt=math.sqrt(max(total * total - climb * climb, 0.0)) * MS_TO_KT,
                    on_ground=(v["weight_on_wheels"] or 0.0) > 0.5,
                )
            )
        return found

    async def run(self, store):
        self._store = store
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=("0.0.0.0", self._listen_port))
        try:
            while True:
                self._subscribe(True)
                await asyncio.sleep(RESEND_SECONDS)
        finally:
            self._subscribe(False)
            self._transport.close()
