import asyncio
import os
import re
import subprocess
import tempfile
import wave

from atc.audio import radio
from atc.state.models import Position
from atc.validator import ACRONYMS

RATE_WPM = 200
PREFERRED = {
    Position.CLEARANCE: ("Samantha", "Kathy"),
    Position.GROUND: ("Daniel", "Fred"),
    Position.TOWER: ("Reed (English (US))", "Aman"),
    Position.DEPARTURE: ("Karen", "Moira"),
    Position.CENTER: ("Tessa", "Fred"),
    Position.APPROACH: ("Flo (English (US))", "Moira"),
}


def installed_voices():
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    names = {m[1] for line in out.splitlines() if (m := re.match(r"^(.+?)\s+[a-z]{2,3}_\w+\s+#", line))}
    return names | {name.split(" (")[0] for name in names}


def pick_voices(installed):
    return {p: next((v for v in names if v in installed), None) for p, names in PREFERRED.items()}


def pronounceable(text):
    return re.sub(r"\b[A-Z]{3,5}\b", lambda m: m[0] if m[0] in ACRONYMS else m[0].lower(), text)


async def _run(*args):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


class Speaker:
    def __init__(self, voices=None):
        self._voices = pick_voices(installed_voices()) if voices is None else voices
        self._queue = asyncio.Queue()

    def say(self, text, position):
        self._queue.put_nowait((text, position))

    async def synthesize(self, path, text, position):
        voice = self._voices.get(position)
        await _run(
            "say",
            *(["-v", voice] if voice else []),
            "-r",
            str(RATE_WPM),
            "-o",
            path,
            f"--data-format=LEI16@{radio.RATE}",
            pronounceable(text),
        )
        with wave.open(path) as w:
            pcm = w.readframes(w.getnframes())
        pcm = await asyncio.to_thread(radio.process, pcm)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(radio.RATE)
            w.writeframes(pcm)

    async def run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "speech.wav")
            while True:
                text, position = await self._queue.get()
                await self.synthesize(path, text, position)
                await _run("afplay", path)
