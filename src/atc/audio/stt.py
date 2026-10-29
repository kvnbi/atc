import numpy as np

from atc import spoken
from atc.data import nav

BASE_PROMPT = "Aviation radio. Hold short runway. Cleared for takeoff. Squawk four five two one. Niner."
MIN_RMS = 150.0
HALLUCINATIONS = frozenset({"you", "thank you", "thanks for watching", "bye"})
MAX_FIXES = 12
MAX_PROMPT_CHARS = 700


class Transcriber:
    __slots__ = ("_name", "_model")

    def __init__(self, model="base.en"):
        self._name = model
        self._model = None

    def load(self):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(self._name, device="cpu", compute_type="int8")

    def transcribe(self, pcm, prompt=""):
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0 or float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) < MIN_RMS:
            return ""
        if self._model is None:
            self.load()
        segments, _ = self._model.transcribe(
            samples.astype(np.float32) / 32768.0,
            language="en",
            beam_size=1,
            initial_prompt=prompt or None,
            condition_on_previous_text=False,
        )
        text = spoken.normalize(" ".join(s.text.strip() for s in segments))
        return "" if text.lower().strip(" .!?") in HALLUCINATIONS else text


def vocabulary(airports, callsign="", flight_plan=""):
    parts = []
    if callsign:
        parts.append(f"{spoken.callsign(callsign)}.")
        if callsign.upper().startswith("N"):
            parts.append(f"{spoken.spell(callsign[-3:])}.")
    if airports:
        first = airports[0]
        ends = [e.name for r in first.runways for e in r.ends]
        parts.append(
            "Runways "
            + ", ".join(spoken.normalize(f"{n[:-1]} {spoken.SIDE_WORDS[n[-1]]}" if n[-1] in "LRC" else n) for n in ends)
            + "."
        )
    idents = []
    for token in flight_plan.replace(",", " ").replace(".", " ").split():
        if token.isalnum() and token[:3].isalpha() and token[:3].isupper() and len(token) > 3 and token not in idents:
            idents.append(token)
    for airport in airports[:1]:
        for kind in ("SID", "STAR"):
            idents += [n for n in nav.procedures(airport.icao)[kind] if n not in idents]
    if idents:
        parts.append(", ".join(spoken.normalize(i) for i in idents[:MAX_FIXES]) + ".")
    return " ".join([BASE_PROMPT, *parts])[-MAX_PROMPT_CHARS:]
