import asyncio

import pytest

from atc.llm.tools import transmit_tool
from atc.validator import Validator


@pytest.fixture
def validator(ksfo):
    return Validator(lambda: (ksfo,))


@pytest.mark.parametrize(
    "text",
    [
        "Cessna three alpha bravo, runway two eight right, taxi via charlie, hold short runway one niner right.",
        "Cessna three alpha bravo, contact tower one two zero point five.",
        "Cessna three alpha bravo, cleared for takeoff runway two eight right.",
        "Cessna three alpha bravo, SSTIK five departure, maintain eight thousand, squawk four five two one.",
        "Cessna three alpha bravo, proceed direct SERFR, climb flight level two four zero.",
        "Cessna three alpha bravo, contact Oakland center one three three point four.",
        "Cessna three alpha bravo, turn left heading two seven zero, cleared ILS runway one niner left approach.",
    ],
)
def test_accepts(validator, text):
    assert validator.check(text) == []


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("Cessna three alpha bravo, runway three six right, cleared to land.", "36R"),
        ("Cessna three alpha bravo, contact tower one two zero point six.", "120.600"),
        ("Cessna three alpha bravo, runway 28R, cleared for takeoff.", "spell every number"),
        ("Cessna three alpha bravo, taxi via zulu nine.", "Z9"),
        ("Cessna three alpha bravo, proceed direct QQQQQ.", "QQQQQ"),
        ("Cessna three alpha bravo, ZZZZZ five departure.", "ZZZZ5"),
        ("Cessna three alpha bravo, maintain eight thousand five.", "8005"),
        ("Cessna three alpha bravo, maintain twenty thousand.", "flight level"),
        ("Cessna three alpha bravo, climb flight level one two zero.", "flight levels"),
        ("Cessna three alpha bravo, turn right heading three six five.", "heading 365"),
        ("Cessna three alpha bravo, squawk four five two eight.", "squawk 4528"),
        ("Cessna three alpha bravo, wind not available, cleared for takeoff.", "missing data"),
    ],
)
def test_rejects(validator, text, fragment):
    problems = validator.check(text)
    assert any(fragment in p for p in problems), problems


def test_without_airports_only_general_checks_run():
    v = Validator()
    assert v.check("Cessna three alpha bravo, runway three six right, cleared to land.") == []
    assert "spell every number as words" in v.check("runway 28R")[0]


def test_retry_budget():
    v = Validator()
    assert v.reject("a", ["x"]) is True
    assert v.reject("b", ["y"]) is False
    assert [t for t, _ in v.history] == ["a", "b"]
    v.begin()
    assert v.history == [] and v.reject("c", ["z"]) is True


def test_transmit_retry_then_stand_by(validator):
    spoken = []
    tool = transmit_tool(spoken.append, validator)
    bad = "Cessna three alpha bravo, runway three six right, cleared to land."
    with pytest.raises(ValueError, match="rejected"):
        asyncio.run(tool.handler(bad))
    assert spoken == []
    assert asyncio.run(tool.handler(bad)) == "transmitted"
    assert spoken == ["Stand by."]
    validator.begin()
    good = "Cessna three alpha bravo, runway two eight right, cleared to land."
    asyncio.run(tool.handler(good))
    assert spoken[-1] == good
