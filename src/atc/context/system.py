from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent / "prompts"
_FILES = ("role.md", "phraseology.md", "positions.md", "examples.md")


@cache
def system_prompt():
    return "\n\n".join((_DIR / name).read_text().strip() for name in _FILES)
