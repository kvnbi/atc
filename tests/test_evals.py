import asyncio
import re

import pytest
from cases import CASES, FLIGHT_PLAN, aircraft, final

from atc import notes as flight_notes
from atc.config import get_settings
from atc.context.builder import ContextBuilder
from atc.llm.client import LLM
from atc.llm.data_tools import data_tools
from atc.llm.tools import core_tools
from atc.state.store import StateStore
from atc.validator import Validator

FILLER = re.compile(r"\b(please|thank|sorry|certainly|happy to|glad|sure)\b", re.I)
ADDRESS = re.compile(r"\b(cessna|november|alpha bravo)\b", re.I)
MAX_WORDS = 45


async def run(case, airport, tmp_path):
    store = StateStore()
    store.set_aircraft(aircraft(airport, case))
    store.set_position(case.position)
    if case.final_traffic:
        store.set_traffic([final(airport)])
    path = tmp_path / "flight.md"
    flight_notes.save(path, case.notes)
    said = []
    validator = Validator(lambda: (airport,), traffic=lambda: bool(store.snapshot().traffic))
    tools = core_tools(path, said.append, validator) + data_tools(store.snapshot)
    system, messages = ContextBuilder(FLIGHT_PLAN).build(store.snapshot(), case.notes, call=case.call)
    await LLM(settings=get_settings()).run(system, messages, tools)
    return said, validator.history


@pytest.mark.live
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_case(case, ksfo, tmp_path):
    if not get_settings().api_key:
        pytest.skip("no API key")
    said, history = asyncio.run(run(case, ksfo, tmp_path))
    text = " ".join(said)
    failures = []
    if len(said) != 1:
        failures.append(f"{len(said)} transmissions")
    if len(history) > 1:
        failures.append("fell back to stand by")
    if len(text.split()) > MAX_WORDS:
        failures.append("too long")
    if FILLER.search(text):
        failures.append("filler words")
    if not ADDRESS.search(text):
        failures.append("does not address the aircraft")
    failures += Validator(lambda: (ksfo,)).check(text)
    failures += [f"missing {p}" for p in case.expect if not re.search(p, text, re.I)]
    failures += [f"forbidden {p}" for p in case.forbid if re.search(p, text, re.I)]
    assert not failures, f"{text!r} {failures} retries={history}"
