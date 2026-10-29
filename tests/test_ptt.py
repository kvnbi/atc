import asyncio
import time

from atc.audio.ptt import Recorder, Toggle, utterances


class FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.state = "new"

    def start(self):
        self.state = "started"

    def stop(self):
        self.state = "stopped"

    def close(self):
        self.state = "closed"


class Button:
    def __init__(self, windows):
        self.began = time.monotonic()
        self.windows = windows

    def __call__(self):
        now = time.monotonic() - self.began
        return any(a <= now < b for a, b in self.windows)


class FakeRecorder:
    def __init__(self, sizes):
        self.sizes = list(sizes)
        self.starts = 0

    def start(self):
        self.starts += 1

    def stop(self):
        return bytes(self.sizes.pop(0))


def collect(button, recorder, wait, **kwargs):
    heard = []

    async def scenario():
        async def consume():
            async for pcm in utterances(button, recorder, **kwargs):
                heard.append(len(pcm))

        task = asyncio.create_task(consume())
        await asyncio.sleep(wait)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    return heard


def test_recorder_collects_frames_and_clears_between_presses():
    streams = []

    def factory(**kwargs):
        streams.append(FakeStream(**kwargs))
        return streams[-1]

    recorder = Recorder(factory)
    recorder.start()
    streams[0].callback(b"\x01\x00" * 100, 100, None, None)
    streams[0].callback(b"\x02\x00" * 50, 50, None, None)
    assert streams[0].state == "started"
    assert len(recorder.stop()) == 300
    assert streams[0].state == "closed"
    recorder.start()
    streams[1].callback(b"\x00\x00" * 10, 10, None, None)
    assert len(recorder.stop()) == 20
    assert recorder.stop() == b"\x00\x00" * 10


def test_press_yields_audio_and_taps_are_ignored():
    recorder = FakeRecorder([20000, 4000])
    heard = collect(Button([(0.05, 0.15), (0.25, 0.30)]), recorder, 0.6)
    assert heard == [20000] and recorder.starts == 2


def test_long_hold_is_cut_off_and_waits_for_release():
    recorder = FakeRecorder([20000, 20000])
    heard = collect(Button([(0.05, 10.0)]), recorder, 0.4, max_seconds=0.1)
    assert heard == [20000] and recorder.starts == 1


def test_toggle():
    toggle = Toggle()
    assert toggle() is False
    toggle.down = True
    assert toggle() is True
