import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from inspect import isawaitable

from anthropic import AsyncAnthropic

from atc.config import get_settings


@dataclass(frozen=True, slots=True)
class Result:
    text: str
    stop_reason: str
    steps: int
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def _tool_result(tool_use_id, content, is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


async def _call(tools, block):
    tool = tools.get(block.name)
    if tool is None:
        return _tool_result(block.id, f"unknown tool {block.name}", True)
    try:
        out = tool.handler(**block.input)
        if isawaitable(out):
            out = await out
    except Exception as e:
        return _tool_result(block.id, f"{type(e).__name__}: {e}", True)
    return _tool_result(block.id, out if isinstance(out, str) else json.dumps(out))


class LLM:
    __slots__ = ("_client", "_model", "_max_steps", "_max_tokens", "_effort", "_thinking", "on_request", "on_tool_start")

    def __init__(self, client=None, settings=None, max_tokens=2048):
        settings = settings or get_settings()
        self._client = client or AsyncAnthropic(api_key=settings.api_key or None)
        self._model = settings.model
        self._max_steps = settings.max_tool_steps
        self._max_tokens = max_tokens
        self._effort = settings.effort
        self._thinking = settings.thinking
        self.on_request = None
        self.on_tool_start = None

    async def _stream(self, messages, request, by_name):
        started = {}
        try:
            async with self._client.messages.stream(messages=messages, **request) as stream:
                async for event in stream:
                    if (
                        event.type == "content_block_start"
                        and event.content_block.type == "tool_use"
                        and self.on_tool_start
                    ):
                        self.on_tool_start(event.content_block.name)
                    elif event.type == "content_block_stop" and event.content_block.type == "tool_use":
                        block = event.content_block
                        started[block.id] = asyncio.create_task(_call(by_name, block))
                response = await stream.get_final_message()
        except BaseException:
            for task in started.values():
                task.cancel()
            raise
        return response, started

    async def run(self, system, messages, tools=()):
        request = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": [
                {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
                for text in system
            ],
            "output_config": {"effort": self._effort},
        }
        if self._thinking:
            request["thinking"] = {"type": self._thinking}
        if tools:
            request["tools"] = [t.param() for t in sorted(tools, key=lambda t: t.name)]
        by_name = {t.name: t for t in tools}
        messages = list(messages)
        usage = Counter()
        for step in range(1, self._max_steps + 1):
            if self.on_request:
                self.on_request()
            response, started = await self._stream(messages, request, by_name)
            u = response.usage
            usage["in"] += u.input_tokens
            usage["out"] += u.output_tokens
            usage["read"] += u.cache_read_input_tokens or 0
            usage["write"] += u.cache_creation_input_tokens or 0
            text = "".join(b.text for b in response.content if b.type == "text")
            if response.stop_reason != "tool_use":
                return self._result(text, response.stop_reason, step, usage)
            calls = [b for b in response.content if b.type == "tool_use"]
            results = await asyncio.gather(*(started.get(b.id) or _call(by_name, b) for b in calls))
            if any(
                by_name[c.name].ends_turn and "is_error" not in r
                for c, r in zip(calls, results)
                if c.name in by_name
            ):
                return self._result(text, "end_turn", step, usage)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": list(results)})
        return self._result("", "max_steps", self._max_steps, usage)

    @staticmethod
    def _result(text, stop_reason, steps, usage):
        return Result(
            text,
            stop_reason,
            steps,
            usage["in"],
            usage["out"],
            usage["read"],
            usage["write"],
        )
