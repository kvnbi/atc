import asyncio
import time

RATE = 16000
POLL_SECONDS = 0.02
MIN_SECONDS = 0.3
MAX_SECONDS = 30.0


class Toggle:
    __slots__ = ("down",)

    def __init__(self):
        self.down = False

    def __call__(self):
        return self.down


class Recorder:
    __slots__ = ("_factory", "_stream", "_buffer")

    def __init__(self, factory=None):
        self._factory = factory
        self._stream = None
        self._buffer = bytearray()

    def _callback(self, indata, frames, time_info, status):
        self._buffer += bytes(indata)

    def start(self):
        if self._factory is None:
            import sounddevice

            self._factory = sounddevice.RawInputStream
        self._buffer = bytearray()
        self._stream = self._factory(samplerate=RATE, channels=1, dtype="int16", callback=self._callback)
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return bytes(self._buffer)


async def utterances(is_down, recorder, min_seconds=MIN_SECONDS, max_seconds=MAX_SECONDS):
    while True:
        while not is_down():
            await asyncio.sleep(POLL_SECONDS)
        recorder.start()
        began = time.monotonic()
        while is_down() and time.monotonic() - began < max_seconds:
            await asyncio.sleep(POLL_SECONDS)
        pcm = recorder.stop()
        if len(pcm) >= min_seconds * RATE * 2:
            yield pcm
        while is_down():
            await asyncio.sleep(POLL_SECONDS)
