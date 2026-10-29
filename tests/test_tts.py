import asyncio
import shutil
import wave

import pytest

from atc.audio import radio, tts
from atc.state.models import Position

needs_say = pytest.mark.skipif(shutil.which("say") is None, reason="macOS say not found")


@needs_say
def test_installed_voices_are_listed_with_and_without_qualifiers():
    voices = tts.installed_voices()
    assert len(voices) > 5
    assert all(v.split(" (")[0] in voices for v in voices)


def test_pick_voices_uses_the_first_installed_choice():
    voices = tts.pick_voices({"Daniel", "Fred", "Samantha"})
    assert voices[Position.CLEARANCE] == "Samantha"
    assert voices[Position.GROUND] == "Daniel"
    assert voices[Position.CENTER] == "Fred"
    assert voices[Position.TOWER] is None


def test_fix_names_are_spoken_as_words_and_acronyms_are_spelled():
    assert tts.pronounceable("SSTIK five departure, ILS runway, KAYEX") == "sstik five departure, ILS runway, kayex"


def test_speaker_synthesizes_filters_and_plays(tmp_path):
    calls = []

    async def fake_run(*args):
        calls.append(args)
        if args[0] == "say":
            path = args[args.index("-o") + 1]
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(radio.RATE)
                w.writeframes(bytes(16000))

    original = tts._run
    tts._run = fake_run

    async def scenario():
        speaker = tts.Speaker({Position.GROUND: "Daniel"})
        speaker.say("Cessna three alpha bravo, taxi via charlie, SSTIK", Position.GROUND)
        speaker.say("Stand by.", Position.TOWER)
        task = asyncio.create_task(speaker.run())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if sum(1 for c in calls if c[0] == "afplay") == 2:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(scenario())
    finally:
        tts._run = original
    says = [c for c in calls if c[0] == "say"]
    assert says[0][1:3] == ("-v", "Daniel") and "sstik" in says[0][-1] and "-r" in says[0]
    assert "-v" not in says[1] and says[1][-1] == "Stand by."
    assert [c[0] for c in calls] == ["say", "afplay", "say", "afplay"]
