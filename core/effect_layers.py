from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class EffectLayer(IntEnum):
    TYPE = 10
    HP = 20
    COST = 30
    DAMAGE_MODIFIER = 40
    STATUS_IMMUNITY = 50
    MISC = 60


@dataclass(frozen=True)
class ContinuousRule:
    source: str
    layer: EffectLayer
    priority: int
    rule: dict[str, Any]


class ContinuousRuleEngine:
    def __init__(self) -> None:
        self._rules: list[ContinuousRule] = []

    def add_rule(self, rule: ContinuousRule) -> None:
        self._rules.append(rule)

    def remove_source(self, source: str) -> None:
        self._rules = [rule for rule in self._rules if rule.source != source]

    def resolve(self, base: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(base)
        for rule in sorted(self._rules, key=lambda r: (int(r.layer), r.priority, r.source)):
            for key, value in rule.rule.items():
                if isinstance(value, (int, float)) and isinstance(resolved.get(key), (int, float)):
                    resolved[key] = resolved[key] + value
                else:
                    resolved[key] = value
        return resolved
