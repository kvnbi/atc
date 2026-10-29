import asyncio
from types import SimpleNamespace as NS

import pytest

from atc.config import get_settings
from atc.llm.client import LLM
from atc.llm.tools import Tool


def use(i, name, **inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


def stop(block):
    return NS(type="content_block_stop", content_block=block)


def final(*blocks, reason="tool_use", tokens=(10, 5)):
    usage = NS(
        input_tokens=tokens[0], output_tokens=tokens[1], cache_read_input_tokens=3, cache_creation_input_tokens=0
    )
    return NS(content=list(blocks), stop_reason=reason, usage=usage)


class FakeStream:
    def __init__(self, events, message, order, gap, fail):
        self.events, self.message, self.order, self.gap, self.fail = events, message, order, gap, fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for event in self.events:
            yield event
            await asyncio.sleep(self.gap)
        if self.fail:
            raise RuntimeError("connection lost")

    async def get_final_message(self):
        self.order.append("final")
        return self.message


class FakeClient:
    def __init__(self, *turns, gap=0.0, fail=False):
        self.turns = list(turns)
        self.order = []
        self.sent = []
        self.gap = gap
        self.fail = fail
        self.messages = self

    def stream(self, **kwargs):
        self.sent.append(list(kwargs["messages"]))
        events, message = self.turns.pop(0)
        return FakeStream(events, message, self.order, self.gap, self.fail)


def tool(name, handler, ends_turn=False):
    return Tool(name, name, {"type": "object", "properties": {}, "required": [], "additionalProperties": False}, handler, ends_turn)


def run(client, tools, **kwargs):
    return asyncio.run(LLM(client, get_settings(), **kwargs).run(["s"], [{"role": "user", "content": "q"}], tools))


def test_tools_start_as_soon_as_their_block_is_complete():
    order = []
    speak, notes = use("a", "transmit"), use("b", "update_notes")
    client = FakeClient(([stop(speak), stop(notes)], final(speak, notes)), gap=0.03)
    client.order = order
    tools = (tool("transmit", lambda: order.append("transmit"), True), tool("update_notes", lambda: order.append("notes")))
    result = run(client, tools)
    assert order.index("transmit") < order.index("final")
    assert result.stop_reason == "end_turn" and result.steps == 1


def test_usage_is_summed_and_text_returned():
    client = FakeClient(([], final(NS(type="text", text="Roger."), reason="end_turn", tokens=(7, 2))))
    result = run(client, ())
    assert (result.text, result.input_tokens, result.output_tokens, result.cache_read_tokens) == ("Roger.", 7, 2, 3)


def test_a_rejected_transmit_is_retried_with_the_error_returned():
    def transmit(text=""):
        if not state:
            state.append(1)
            raise ValueError("rejected")
        return "ok"

    state = []
    first, second = use("a", "transmit"), use("b", "transmit")
    client = FakeClient(([stop(first)], final(first)), ([stop(second)], final(second)))
    result = run(client, (tool("transmit", transmit, True),))
    assert result.steps == 2 and result.stop_reason == "end_turn"
    returned = client.sent[1][-1]["content"][0]
    assert returned["is_error"] and "rejected" in returned["content"]


def test_a_dropped_stream_cancels_started_tools():
    cancelled = []

    async def slow():
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    block = use("a", "slow")
    client = FakeClient(([stop(block)], final(block)), gap=0.01, fail=True)
    with pytest.raises(RuntimeError):
        run(client, (tool("slow", slow),))
    assert cancelled == [True]


def test_step_cap():
    block = use("a", "lookup")
    client = FakeClient(*[([stop(block)], final(block)) for _ in range(10)])
    result = run(client, (tool("lookup", lambda: "x"),))
    assert result.stop_reason == "max_steps" and result.steps == get_settings().max_tool_steps


def test_tool_start_hook_fires_when_the_block_opens_not_when_it_closes():
    order = []
    block = use("a", "transmit")
    start = NS(type="content_block_start", content_block=NS(type="tool_use", name="transmit"))
    text = NS(type="content_block_start", content_block=NS(type="text", name=""))
    client = FakeClient(([text, start, stop(block)], final(block)))
    client.order = order
    llm = LLM(client, get_settings())
    llm.on_tool_start = lambda name: order.append(f"open:{name}")
    tools = (tool("transmit", lambda: order.append("run"), True),)
    asyncio.run(llm.run(["s"], [{"role": "user", "content": "q"}], tools))
    assert order[:2] == ["open:transmit", "run"] and order.count("open:transmit") == 1
