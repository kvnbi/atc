from dataclasses import dataclass
from typing import Callable


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
