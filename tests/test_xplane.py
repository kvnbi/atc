import asyncio
import re
import struct

import pytest

from atc.bridge import xplane
from atc.config import get_settings
from atc.state.store import StateStore

OWN_VALUES = {
    "sim/flightmodel/position/latitude": 37.62,
    "sim/flightmodel/position/longitude": -122.37,
    "sim/flightmodel/position/elevation": 100.0,
    "sim/flightmodel/position/y_agl": 0.0,
    "sim/flightmodel/position/true_psi": 280.0,
    "sim/flightmodel/position/indicated_airspeed": 0.0,
    "sim/flightmodel/position/groundspeed": 5.14444,
    "sim/flightmodel/position/vh_ind_fpm": 0.0,
    "sim/flightmodel/failures/onground_any": 1.0,
    "sim/cockpit/switches/gear_handle_status": 1.0,
    "sim/cockpit2/controls/flap_handle_request_ratio": 0.25,
    "sim/cockpit/radios/transponder_code": 4521.0,
    "sim/cockpit2/radios/actuators/com1_frequency_hz_833": 121800.0,
}
TARGET = "sim/cockpit2/tcas/targets"
TRAFFIC_VALUES = {
    f"{TARGET}/position/lat[3]": 37.63,
    f"{TARGET}/position/lon[3]": -122.38,
    f"{TARGET}/position/ele[3]": 500.0,
    f"{TARGET}/position/psi[3]": 90.0,
    f"{TARGET}/position/V_msc[3]": 77.17,
    f"{TARGET}/position/vertical_speed[3]": 0.0,
    f"{TARGET}/position/weight_on_wheels[3]": 0.0,
    f"{TARGET}/position/lat[5]": 0.0,
    f"{TARGET}/position/lon[5]": 0.0,
    **{f"{TARGET}/flight_id[{24 + k}]": float(ord(c)) for k, c in enumerate("UAL482")},
}


class FakeXPlane(asyncio.DatagramProtocol):
    def __init__(self, values):
        self.values = values
        self.requests = {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if data[:5] != b"RREF\x00":
            return
        hz, index, raw = struct.unpack("<ii400s", data[5:413])
        name = raw.split(b"\x00")[0].decode()
        self.requests[index] = (name, hz)
        if hz and name in self.values:
            self.transport.sendto(b"RREF," + struct.pack("<if", index, self.values[name]), addr)


def test_names_exist_in_datarefs_file():
    path = get_settings().xplane_dir / "Resources" / "plugins" / "DataRefs.txt"
    if not path.is_file():
        pytest.skip("DataRefs.txt not found")
    known = {line.split("\t")[0] for line in path.read_text(errors="ignore").splitlines()}
    names = {re.sub(r"\[\d+\]$", "", name) for name, _ in xplane.XPlane()._specs}
    assert names - known == set()


def test_telemetry_and_traffic_round_trip():
    async def scenario():
        loop = asyncio.get_running_loop()
        fake = FakeXPlane({**OWN_VALUES, **TRAFFIC_VALUES})
        server, _ = await loop.create_datagram_endpoint(lambda: fake, local_addr=("127.0.0.1", 0))
        port = server.get_extra_info("sockname")[1]
        store = StateStore()
        bridge = xplane.XPlane("127.0.0.1", port, 0)
        assert not bridge.connected
        task = asyncio.create_task(bridge.run(store))
        for _ in range(100):
            await asyncio.sleep(0.02)
            if store.snapshot().traffic and store.snapshot().aircraft.com1_khz:
                break
        snap = store.snapshot()
        connected = bridge.connected
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0.05)
        server.close()
        return snap, connected, fake.requests

    snap, connected, requests = asyncio.run(scenario())
    a = snap.aircraft
    assert connected
    assert a.lat == pytest.approx(37.62, abs=1e-4) and a.lon == pytest.approx(-122.37, abs=1e-4)
    assert a.alt_msl_ft == pytest.approx(328.084, abs=0.01)
    assert a.heading_deg == 280.0 and a.ground_speed_kt == pytest.approx(10.0, abs=0.01)
    assert a.on_ground and a.gear_down and a.flap_ratio == 0.25
    assert a.squawk == 4521 and a.com1_khz == 121800
    assert len(snap.traffic) == 1
    t = snap.traffic[0]
    assert t.id == "t3" and t.callsign == "UAL482"
    assert t.lat == pytest.approx(37.63, abs=1e-4) and t.heading_deg == 90.0
    assert t.ground_speed_kt == pytest.approx(150.0, abs=0.1) and not t.on_ground
    assert t.alt_msl_ft == pytest.approx(1640.42, abs=0.01)
    assert len(requests) == len(xplane.XPlane()._specs)
    assert all(hz == 0 for _, hz in requests.values())
