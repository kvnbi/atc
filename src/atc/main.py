import argparse
import asyncio
import sys
import time

import anthropic

from atc import notes as flight_notes
from atc.bridge.replay import Replay
from atc.config import ROOT, get_settings
from atc.context.builder import ContextBuilder
from atc.llm.client import LLM
from atc.llm.data_tools import data_tools
from atc.llm.tools import core_tools
from atc.state.models import Position
from atc.state.store import StateStore

SAMPLE = ROOT / "samples" / "ground_to_takeoff.jsonl"


def _args(argv):
    parser = argparse.ArgumentParser(prog="atc")
    parser.add_argument("--position", choices=[p.value for p in Position], default="ground")
    parser.add_argument("--flight-plan", default="")
    parser.add_argument("--replay", default=str(SAMPLE))
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--fresh", action="store_true")
    return parser.parse_args(argv)


async def main(argv=None):
    args = _args(argv)
    settings = get_settings()
    store = StateStore()
    store.set_position(args.position)
    notes_path = settings.notes_dir / "flight.md"
    if args.fresh:
        flight_notes.save(notes_path, flight_notes.Notes())
    said = []

    def say(text):
        said.append(text)
        print(f"\n{store.snapshot().position.value.upper()}: {text}\n")

    builder = ContextBuilder(args.flight_plan)
    llm = LLM(settings=settings)
    tools = core_tools(notes_path, say) + data_tools(store.snapshot)
    replay = None
    if not args.no_replay:
        replay = asyncio.create_task(Replay.from_file(args.replay).run(store, args.speed))
    try:
        while True:
            print("> ", end="", flush=True)
            raw = await asyncio.to_thread(sys.stdin.readline)
            if not raw:
                break
            line = raw.strip()
            if not line:
                continue
            if line == "/quit":
                break
            if line.startswith("/pos "):
                try:
                    store.set_position(line[5:].strip())
                except ValueError as e:
                    print(e)
                continue
            said.clear()
            system, messages = builder.build(
                store.snapshot(), flight_notes.load(notes_path), call=line
            )
            start = time.perf_counter()
            try:
                result = await llm.run(system, messages, tools)
            except anthropic.APIError as e:
                print(f"error: {e}")
                continue
            elapsed = time.perf_counter() - start
            if not said:
                print("[silence]")
            print(
                f"[{result.stop_reason}, {result.steps} steps, {elapsed:.1f}s, "
                f"in {result.input_tokens} out {result.output_tokens} "
                f"cache read {result.cache_read_tokens} write {result.cache_write_tokens}]"
            )
    finally:
        if replay:
            replay.cancel()


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
