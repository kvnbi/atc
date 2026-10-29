import asyncio
import json
from pathlib import Path

from atc.state.models import Aircraft, Traffic


class Replay:
    __slots__ = ("_frames",)

    def __init__(self, frames):
        self._frames = tuple(frames)

    @classmethod
    def from_file(cls, path):
        lines = Path(path).read_text().splitlines()
        return cls(json.loads(line) for line in lines if line.strip())

    async def run(self, store, speed=1.0):
        if not self._frames:
            return
        loop = asyncio.get_running_loop()
        start = loop.time()
        first = self._frames[0]["t"]
        for frame in self._frames:
            delay = (frame["t"] - first) / speed - (loop.time() - start)
            if delay > 0:
                await asyncio.sleep(delay)
            store.set_aircraft(Aircraft(time=frame["t"], **frame["aircraft"]))
            store.set_traffic(Traffic(**t) for t in frame.get("traffic", ()))
