from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EffectOperation:
    """Normalized action primitive produced from card wording."""

    op: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "params": self.params}


@dataclass
class EffectProgram:
    """Compiled representation of one card text block."""

    source_text: str
    operations: list[EffectOperation] = field(default_factory=list)
    template_name: str | None = None
    unresolved_text: str | None = None

    @property
    def is_fully_resolved(self) -> bool:
        return self.unresolved_text is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_text": self.source_text,
            "template_name": self.template_name,
            "is_fully_resolved": self.is_fully_resolved,
            "unresolved_text": self.unresolved_text,
            "operations": [operation.to_dict() for operation in self.operations],
        }

