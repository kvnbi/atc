from types import SimpleNamespace

import numpy as np

from atc.audio import stt


def noise(seconds=1.0, level=3000):
    rng = np.random.default_rng(1)
    return rng.integers(-level, level, int(seconds * 16000)).astype(np.int16).tobytes()


class FakeModel:
    def __init__(self, text):
        self.text = text
        self.kwargs = None

    def transcribe(self, samples, **kwargs):
        self.kwargs = kwargs
        return [SimpleNamespace(text=self.text)], None


def test_silence_never_reaches_the_model():
    transcriber = stt.Transcriber()
    assert transcriber.transcribe(bytes(32000)) == ""
    assert transcriber.transcribe(b"") == ""
    assert transcriber._model is None


def test_transcript_is_normalized_and_prompted():
    transcriber = stt.Transcriber()
    transcriber._model = FakeModel(" Holding short runway 2-8 Right. ")
    text = transcriber.transcribe(noise(), "my prompt")
    assert text == "Holding short runway two eight Right."
    assert transcriber._model.kwargs["initial_prompt"] == "my prompt"
    assert transcriber._model.kwargs["language"] == "en"


def test_known_hallucinations_are_dropped():
    transcriber = stt.Transcriber()
    transcriber._model = FakeModel(" Thank you. ")
    assert transcriber.transcribe(noise()) == ""


def test_vocabulary_carries_callsign_runways_and_fixes(ksfo):
    prompt = stt.vocabulary(
        (ksfo,), "N123AB", "N123AB, Cessna 172, IFR, KSFO to KSEA, SSTIK5 departure, KAYEX transition"
    )
    assert "november one two three alpha bravo" in prompt
    assert "three alpha bravo" in prompt
    assert "two eight right" in prompt
    assert "SSTIK five" in prompt and "KAYEX" in prompt
    assert len(prompt) <= stt.MAX_PROMPT_CHARS
    assert stt.vocabulary((), "") == stt.BASE_PROMPT
