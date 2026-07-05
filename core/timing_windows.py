from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from core.effect_types import EffectOperation


class TimingWindow(str, Enum):
    TURN_START = "TURN_START"
    BEFORE_ATTACK = "BEFORE_ATTACK"
    ON_ATTACK = "ON_ATTACK"
    AFTER_ATTACK = "AFTER_ATTACK"
    ON_RETREAT = "ON_RETREAT"
    ON_EVOLVE = "ON_EVOLVE"
    POKEMON_CHECKUP = "POKEMON_CHECKUP"
    TURN_END = "TURN_END"


@dataclass(frozen=True)
class TimingEvent:
    window: TimingWindow
    actor: str
    payload: dict[str, Any] = field(default_factory=dict)


TimingHandler = Callable[[TimingEvent], list[EffectOperation]]


class TimingBus:
    def __init__(self) -> None:
        self._handlers: dict[TimingWindow, list[TimingHandler]] = {window: [] for window in TimingWindow}

    def register(self, window: TimingWindow, handler: TimingHandler) -> None:
        self._handlers[window].append(handler)

    def emit(self, event: TimingEvent) -> list[EffectOperation]:
        operations: list[EffectOperation] = []
        for handler in self._handlers[event.window]:
            operations.extend(handler(event))
        return operations
