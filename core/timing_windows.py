from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from core.effect_types import EffectOperation
from core.priority_stack_policy import stack_order_key


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


class TimingHandlerKind(str, Enum):
    REPLACEMENT = "replacement"
    PREVENTION = "prevention"
    NORMAL = "normal"


@dataclass(frozen=True)
class TimingHandlerRegistration:
    handler: TimingHandler
    priority: int = 100
    kind: TimingHandlerKind = TimingHandlerKind.NORMAL


class TimingBus:
    def __init__(self) -> None:
        self._handlers: dict[TimingWindow, list[TimingHandlerRegistration]] = {
            window: [] for window in TimingWindow
        }

    def register(
        self,
        window: TimingWindow,
        handler: TimingHandler,
        priority: int = 100,
        kind: TimingHandlerKind = TimingHandlerKind.NORMAL,
    ) -> None:
        self._handlers[window].append(
            TimingHandlerRegistration(handler=handler, priority=priority, kind=kind)
        )

    def emit(self, event: TimingEvent) -> list[EffectOperation]:
        operations: list[EffectOperation] = []
        ordered_handlers = sorted(
            enumerate(self._handlers[event.window]),
            key=lambda item: stack_order_key({"kind": item[1].kind.value, "priority": item[1].priority}, item[0]),
        )
        for _, entry in ordered_handlers:
            operations.extend(entry.handler(event))
        return operations
