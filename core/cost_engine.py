from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass
class CostResult:
    paid: bool
    events: list[str]


class CostTransaction:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state
        self._snapshot = copy.deepcopy(state)
        self._events: list[str] = []

    @property
    def events(self) -> list[str]:
        return self._events

    def rollback(self) -> None:
        self._state.clear()
        self._state.update(self._snapshot)
        self._events.append("Cost payment rolled back.")

    def pay_hand_cards(self, actor: str, count: int) -> bool:
        player = self._state["players"][actor]
        hand_size = int(player.get("hand_size", 0))
        if hand_size < count:
            self._events.append(f"{actor} failed hand-cost payment ({count}).")
            return False
        player["hand_size"] = hand_size - count
        self._events.append(f"{actor} paid hand cost of {count} card(s).")
        return True

    def pay_active_energy(self, actor: str, count: int) -> bool:
        active = self._state["players"][actor]["active"]
        attached = int(active.get("energy_attached", 0))
        if attached < count:
            self._events.append(f"{actor} failed energy-cost payment ({count}).")
            return False
        active["energy_attached"] = attached - count
        self._events.append(f"{actor} paid energy cost of {count}.")
        return True


def pay_cost(state: dict[str, Any], actor: str, requirements: dict[str, int]) -> CostResult:
    tx = CostTransaction(state)
    if requirements.get("hand_cards", 0) > 0 and not tx.pay_hand_cards(actor, requirements["hand_cards"]):
        tx.rollback()
        return CostResult(False, tx.events)
    if requirements.get("active_energy", 0) > 0 and not tx.pay_active_energy(actor, requirements["active_energy"]):
        tx.rollback()
        return CostResult(False, tx.events)
    tx.events.append("Cost payment succeeded.")
    return CostResult(True, tx.events)


def can_pay_attack_cost(active: dict[str, Any], attack: dict[str, Any]) -> tuple[bool, str]:
    cost_symbols = attack.get("cost", [])
    if not isinstance(cost_symbols, list):
        return False, "attack cost is malformed"
    required = len(cost_symbols)
    attached = int(active.get("energy_attached", 0))
    if attached < required:
        return False, f"requires {required} energy, has {attached}"
    return True, "attack cost can be paid"
