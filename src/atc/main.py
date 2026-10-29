import argparse
import asyncio
import re
import sys
import time

import anthropic

from atc import notes as flight_notes
from atc.bridge.replay import Replay
from atc.bridge.xplane import XPlane
from atc.config import ROOT, get_settings
from atc.context.builder import ContextBuilder
from atc.data import airports
from atc.events import Watcher, watch
from atc.llm.client import LLM
from atc.llm.data_tools import data_tools
from atc.llm.tools import core_tools
from atc.state.models import Position
from atc.state.store import StateStore
from atc.state.tracking import Tracker
from atc.validator import Validator

SAMPLE = ROOT / "samples" / "ground_to_takeoff.jsonl"


def _scope(flight_plan):
    found = []
    for icao in re.findall(r"\b[A-Z]{4}\b", flight_plan):
        airport = airports.find(icao)
        if airport and airport not in found:
            found.append(airport)
    return tuple(found)


def _args(argv):
    parser = argparse.ArgumentParser(prog="atc")
    parser.add_argument("--position", choices=[p.value for p in Position])
    parser.add_argument("--flight-plan", default="")
    parser.add_argument("--callsign", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--replay", default=str(SAMPLE))
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def _source(args, settings, store):
    if args.live:
        source = XPlane(settings.xplane_host, settings.xplane_port, settings.xplane_listen_port)
        return source, asyncio.create_task(source.run(store))
    if args.no_replay:
        return None, None
    return None, asyncio.create_task(Replay.from_file(args.replay).run(store, args.speed))


async def main(argv=None):
    args = _args(argv)
    settings = get_settings()
    store = StateStore()
    if args.callsign:
        store.update_aircraft(callsign=args.callsign)
    notes_path = settings.notes_dir / "flight.md"
    if args.fresh:
        flight_notes.save(notes_path, flight_notes.Notes())
    said = []

    def say(text):
        said.append(text)
        print(f"\n{store.snapshot().position.value.upper()}: {text}\n")

    scope = _scope(args.flight_plan)
    tracker = Tracker(store, lambda: scope, args.position)
    builder = ContextBuilder(args.flight_plan)
    llm = LLM(settings=settings)
    validator = Validator(lambda: scope)
    tools = core_tools(notes_path, say, validator) + data_tools(store.snapshot)
    lock = asyncio.Lock()

    async def turn(call=None, event=None):
        async with lock:
            if tracker.resolve() is None:
                if call:
                    khz = store.snapshot().aircraft.com1_khz
                    print(f"[no controller on {khz / 1000:.3f}]" if khz else "[no frequency tuned]")
                return
            if event:
                print(f"[event: {event}]")
            said.clear()
            validator.begin()
            system, messages = builder.build(
                store.snapshot(), flight_notes.load(notes_path), call=call, event=event
            )
            start = time.perf_counter()
            try:
                result = await llm.run(system, messages, tools)
            except anthropic.APIError as e:
                print(f"error: {e}")
                return
            elapsed = time.perf_counter() - start
            for text, problems in validator.history:
                print(f"[rejected: {text!r}: {'; '.join(problems)}]")
            if not said:
                print("[silence]")
            print(
                f"[{result.stop_reason}, {result.steps} steps, {elapsed:.1f}s, "
                f"in {result.input_tokens} out {result.output_tokens} "
                f"cache read {result.cache_read_tokens} write {result.cache_write_tokens}]"
            )

    source, task = _source(args, settings, store)
    watcher = None if args.quiet else asyncio.create_task(watch(Watcher(tracker, store, notes_path, lambda: scope), turn))
    await asyncio.sleep(0)
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
                choice = line[5:].strip()
                try:
                    tracker.fixed = None if choice == "auto" else Position(choice)
                except ValueError as e:
                    print(e)
                continue
            if source and not source.connected:
                print("[no data from X-Plane]")
                continue
            await turn(call=line)
    finally:
        for background in (task, watcher):
            if background:
                background.cancel()
                await asyncio.gather(background, return_exceptions=True)


def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
