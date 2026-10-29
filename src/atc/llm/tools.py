from dataclasses import dataclass
from inspect import isawaitable
from typing import Callable

from atc import notes as flight_notes


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    schema: dict
    handler: Callable

    def param(self):
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
            "strict": True,
        }


def transmit_tool(on_transmit):
    async def handler(text):
        text = text.strip()
        if not text:
            raise ValueError("empty transmission")
        out = on_transmit(text)
        if isawaitable(out):
            await out
        return "transmitted"

    return Tool(
        "transmit",
        "Speak one radio transmission to the pilot on the current frequency.",
        {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        handler,
    )


def notes_tool(path):
    def handler(ops):
        notes = flight_notes.load(path)
        missing = flight_notes.patch(notes, ops)
        flight_notes.save(path, notes)
        return "ok" if not missing else "not found: " + "; ".join(missing)

    return Tool(
        "update_notes",
        "Add or remove lines in the flight notes. Remove needs the exact existing text.",
        {
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["add", "remove"]},
                            "section": {"type": "string", "enum": list(flight_notes.NAMES)},
                            "text": {"type": "string"},
                        },
                        "required": ["op", "section", "text"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["ops"],
            "additionalProperties": False,
        },
        handler,
    )


def core_tools(notes_path, on_transmit):
    return (transmit_tool(on_transmit), notes_tool(notes_path))
