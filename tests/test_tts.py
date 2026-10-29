import asyncio
import os
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


def test_sentences_split_and_short_fragments_merge():
    assert tts.sentences("Taxi via charlie, hold short runway one niner right.") == [
        "Taxi via charlie, hold short runway one niner right."
    ]
    assert tts.sentences("Cessna three alpha bravo, taxi via charlie. Hold short runway one niner right. Roger.") == [
        "Cessna three alpha bravo, taxi via charlie.",
        "Hold short runway one niner right. Roger.",
    ]
    assert tts.sentences("Stand by. Cessna three alpha bravo, traffic twelve o'clock.") == [
        "Stand by. Cessna three alpha bravo, traffic twelve o'clock."
    ]
    assert tts.sentences("") == []


def test_speech_starts_before_the_last_sentence_is_ready():
    events = []

    async def fake_run(*args):
        label = args[-1] if args[0] == "say" else "play"
        events.append(f"{args[0]}-start:{label[:6]}")
        await asyncio.sleep(0.03 if args[0] == "say" else 0.05)
        if args[0] == "say":
            with wave.open(args[args.index("-o") + 1], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(radio.RATE)
                w.writeframes(bytes(3200))
        events.append(f"{args[0]}-end:{label[:6]}")

    original = tts._run
    tts._run = fake_run

    async def scenario():
        speaker = tts.Speaker({})
        speaker.say(
            "Cessna three alpha bravo, taxi via charlie. Hold short runway one niner right. Contact tower now.",
            Position.GROUND,
            lambda: events.append("started"),
        )
        task = asyncio.create_task(speaker.run())
        for _ in range(200):
            await asyncio.sleep(0.02)
            if events.count("play-end:play") == 3:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(scenario())
    finally:
        tts._run = original
    assert events.count("started") == 1
    last_say_end = max(i for i, e in enumerate(events) if e.startswith("say-end"))
    assert events.index("started") < last_say_end


def test_callsign_prefix_is_played_while_the_rest_is_synthesized():
    events = []

    async def fake_run(*args):
        if args[0] == "say":
            events.append(("say", args[-1]))
            await asyncio.sleep(0.05)
            with wave.open(args[args.index("-o") + 1], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(radio.RATE)
                w.writeframes(bytes(3200))
        else:
            events.append(("play", os.path.basename(args[1])))

    original = tts._run
    tts._run = fake_run
    callsign = "november one two three alpha bravo"

    async def scenario():
        speaker = tts.Speaker({Position.GROUND: "Daniel"})
        await speaker.prepare(callsign)
        events.clear()
        speaker.say("November one two three alpha bravo, taxi via charlie.", Position.GROUND, lambda: events.append(("start", "")))
        speaker.say("Stand by.", Position.GROUND)
        task = asyncio.create_task(speaker.run())
        for _ in range(200):
            await asyncio.sleep(0.02)
            if sum(1 for e in events if e[0] == "play") == 3:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(scenario())
    finally:
        tts._run = original
    assert [e for e in events if e[0] == "say"] == [("say", "taxi via charlie."), ("say", "Stand by.")]
    plays = [e[1] for e in events if e[0] == "play"]
    assert plays[0] == "prefix-ground.wav" and len(plays) == 3
    assert events.index(("start", "")) < events.index(("say", "Stand by."))


def test_opening_the_callsign_early_speaks_it_before_the_text_exists():
    events = []

    async def fake_run(*args):
        if args[0] == "say":
            events.append(("say", args[-1]))
            await asyncio.sleep(0.03)
            with wave.open(args[args.index("-o") + 1], "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(radio.RATE)
                w.writeframes(bytes(3200))
        else:
            await asyncio.sleep(0.12)
            events.append(("play", os.path.basename(args[1])))

    original = tts._run
    tts._run = fake_run

    async def scenario():
        speaker = tts.Speaker({Position.GROUND: "Daniel"})
        await speaker.prepare("november one two three alpha bravo")
        events.clear()
        task = asyncio.create_task(speaker.run())
        speaker.begin(Position.GROUND, lambda: events.append(("start", "")))
        speaker.begin(Position.GROUND, lambda: events.append(("again", "")))
        await asyncio.sleep(0.05)
        events.append(("text", ""))
        speaker.say("November one two three alpha bravo, taxi via charlie.", Position.GROUND)
        for _ in range(200):
            await asyncio.sleep(0.02)
            if sum(1 for e in events if e[0] == "play") == 2:
                break
        speaker.begin(Position.GROUND)
        speaker.end_turn()
        await asyncio.sleep(0.2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(scenario())
    finally:
        tts._run = original
    names = [e[0] for e in events]
    assert names.index("start") < names.index("text") < names.index("say")
    assert "again" not in names
    assert [e for e in events if e[0] == "say"] == [("say", "taxi via charlie.")]
    assert [e[1] for e in events if e[0] == "play"] == ["prefix-ground.wav", "0.wav", "prefix-ground.wav"]
