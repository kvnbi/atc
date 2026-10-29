import asyncio
import shutil
import subprocess
import wave

import pytest

from atc.audio import radio, stt, tts
from atc.state.models import Position

pytestmark = [
    pytest.mark.audio,
    pytest.mark.skipif(shutil.which("say") is None, reason="macOS say not found"),
]
TRIES = 3
CLEARANCE = (
    "Clearance, Cessna three alpha bravo, request I F R clearance to Seattle via the SSTIK five "
    "departure, KAYEX transition. Squawk four five two one, departure one three five point one."
)


@pytest.fixture(scope="module")
def transcriber():
    model = stt.Transcriber()
    model.load()
    return model


def synth(path, text, voice):
    subprocess.run(
        ["say", "-v", voice, "-o", str(path), "--data-format=LEI16@16000", text], check=True, capture_output=True
    )
    with wave.open(str(path)) as w:
        return w.readframes(w.getnframes())


def test_vocabulary_bias_recovers_fix_names(transcriber, tmp_path):
    pcm = synth(tmp_path / "a.wav", CLEARANCE, "Daniel")
    prompt = stt.vocabulary((), "N123AB", "N123AB, SSTIK5 departure, KAYEX transition")
    text = transcriber.transcribe(pcm, prompt)
    assert "KAYEX" in text and "SSTIK" in text
    assert "one three five point one" in text.lower()


def test_numbers_come_back_as_words(transcriber, tmp_path):
    pcm = synth(tmp_path / "b.wav", "Tower, Cessna one two three alpha bravo, holding short runway two eight right.", "Samantha")
    text = transcriber.transcribe(pcm, stt.vocabulary((), "N123AB")).lower()
    assert "runway two eight right" in text and not any(c.isdigit() for c in text)


def test_radio_filtered_speech_is_still_understood(transcriber, tmp_path):
    pcm = synth(tmp_path / "c.wav", "Cessna three alpha bravo, runway two eight right, cleared for takeoff.", "Alex")
    heard = [transcriber.transcribe(radio.process(pcm), stt.vocabulary((), "N123AB")).lower() for _ in range(TRIES)]
    assert any("runway two eight right" in t and "cleared for takeoff" in t for t in heard), heard


@pytest.mark.parametrize("position", list(Position))
def test_every_position_voice_survives_the_radio(transcriber, tmp_path, position):
    path = str(tmp_path / f"{position.value}.wav")
    speaker = tts.Speaker()
    heard = []
    for _ in range(TRIES):
        asyncio.run(speaker.synthesize(path, "Cessna three alpha bravo, runway two eight right, hold short.", position))
        with wave.open(path) as w:
            pcm = w.readframes(w.getnframes())
        heard.append(transcriber.transcribe(pcm, stt.vocabulary((), "N123AB")).lower())
        if "runway two eight right" in heard[-1] and "hold short" in heard[-1]:
            return
    pytest.fail(f"{position.value} voice never understood: {heard}")
