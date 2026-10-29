import os
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass(slots=True)
class Notes:
    clearances: list[str] = field(default_factory=list)
    readbacks: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    upcoming: list[str] = field(default_factory=list)


_SECTIONS = {f.name.capitalize(): f.name for f in fields(Notes)}


def dumps(notes):
    parts = ["# Flight Notes\n"]
    for title, name in _SECTIONS.items():
        parts.append(f"## {title}\n")
        parts.extend(f"- {' '.join(item.split())}" for item in getattr(notes, name))
        parts.append("")
    return "\n".join(parts)


def loads(text):
    notes = Notes()
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = getattr(notes, _SECTIONS.get(line[3:].strip(), ""), None)
        elif current is not None and line.startswith("- "):
            item = line[2:].strip()
            if item:
                current.append(item)
    return notes


def load(path):
    try:
        return loads(Path(path).read_text())
    except FileNotFoundError:
        return Notes()


def save(path, notes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dumps(notes))
    os.replace(tmp, path)
