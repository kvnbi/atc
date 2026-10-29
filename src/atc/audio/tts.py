import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import time
import wave

from atc.audio import radio
from atc.state.models import Position
from atc.validator import ACRONYMS

RATE_WPM = 200
MIN_WORDS = 3
STALE_SECONDS = 6.0
IDLE_POLL_SECONDS = 0.1
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


def sentences(text):
    chunks = []
    for part in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not part:
            continue
        if chunks and len(part.split()) < MIN_WORDS:
            chunks[-1] += " " + part
        else:
            chunks.append(part)
    if len(chunks) > 1 and len(chunks[0].split()) < MIN_WORDS:
        chunks[1] = chunks[0] + " " + chunks[1]
        chunks.pop(0)
    return chunks


async def _run(*args):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


class Speaker:
    def __init__(self, voices=None):
        self._voices = pick_voices(installed_voices()) if voices is None else voices
        self._queue = asyncio.Queue()
        self._folder = tempfile.mkdtemp()
        self._callsign = ""
        self._prefixes = {}
        self._pending = None
        self._outstanding = 0

    async def wait_idle(self):
        while self._outstanding:
            await asyncio.sleep(IDLE_POLL_SECONDS)

    async def prepare(self, callsign):
        self._callsign = callsign.lower()
        for position in self._voices:
            path = os.path.join(self._folder, f"prefix-{position.value}.wav")
            await self.synthesize(path, callsign + ",", position)
            self._prefixes[position] = path

    def _enqueue(self, source, position, started, proactive):
        self._outstanding += 1
        self._queue.put_nowait((source, position, started, proactive, time.monotonic()))

    def begin(self, position, started=None, proactive=False):
        if self._pending is None and position in self._prefixes:
            self._pending = asyncio.get_running_loop().create_future()
            self._enqueue(self._pending, position, started, proactive)

    def end_turn(self):
        if self._pending is not None:
            if not self._pending.done():
                self._pending.set_result("")
            self._pending = None

    def say(self, text, position, started=None, proactive=False):
        if self._pending is not None:
            future, self._pending = self._pending, None
            if not future.done():
                future.set_result(text)
        else:
            self._enqueue(text, position, started, proactive)

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

    async def _speak(self, folder, source, position, started):
        ready = asyncio.Queue()
        prefix = self._prefixes.get(position)
        pending = isinstance(source, asyncio.Future)
        if pending:
            ready.put_nowait(prefix)

        async def produce():
            text = await source if pending else source
            if prefix and self._callsign and text.lower().startswith(self._callsign):
                text = text[len(self._callsign) :].lstrip(" ,.;")
                if not pending:
                    ready.put_nowait(prefix)
            for i, chunk in enumerate(sentences(text)):
                path = os.path.join(folder, f"{i}.wav")
                await self.synthesize(path, chunk, position)
                await ready.put(path)
            await ready.put(None)

        producer = asyncio.create_task(produce())
        try:
            while (path := await ready.get()) is not None:
                if started:
                    started()
                    started = None
                await _run("afplay", path)
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

    async def run(self):
        try:
            while True:
                source, position, started, proactive, queued = await self._queue.get()
                try:
                    if proactive and time.monotonic() - queued > STALE_SECONDS:
                        if isinstance(source, asyncio.Future) and not source.done():
                            source.set_result("")
                        continue
                    await self._speak(self._folder, source, position, started)
                finally:
                    self._outstanding -= 1
        finally:
            shutil.rmtree(self._folder, ignore_errors=True)
