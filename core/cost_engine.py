from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass
class CostResult:
    paid: bool
    events: list[str]


@dataclass
class AttackCostResult:
    payable: bool
    code: str
    reason: str
    required_symbols: list[str]
    attached_symbols: list[str]
    missing_symbols: list[str]


_ENERGY_SYMBOL_MAP = {
    "c": "C",
    "colorless": "C",
    "r": "R",
    "fire": "R",
    "f": "F",
    "fighting": "F",
    "w": "W",
    "water": "W",
    "l": "L",
    "lightning": "L",
    "p": "P",
    "psychic": "P",
    "d": "D",
    "darkness": "D",
    "m": "M",
    "metal": "M",
    "g": "G",
    "grass": "G",
    "n": "N",
    "dragon": "N",
}


def _normalize_energy_symbol(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower().replace("{", "").replace("}", "")
    token = token.replace(" energy", "").strip()
    if not token:
        return None
    return _ENERGY_SYMBOL_MAP.get(token, token.upper() if len(token) == 1 else None)


def _attached_energy_provides(active: dict[str, Any]) -> list[list[str]]:
    attached_cards = active.get("attached_energy_cards", [])
    provided: list[list[str]] = []
    if isinstance(attached_cards, list) and attached_cards:
        for card in attached_cards:
            if not isinstance(card, dict):
                continue
            symbols: list[str] = []
            raw_provides = card.get("provides")
            if isinstance(raw_provides, list):
                symbols = [symbol for symbol in (_normalize_energy_symbol(entry) for entry in raw_provides) if symbol]
            if not symbols:
                normalized_type = _normalize_energy_symbol(card.get("energy_type"))
                if normalized_type:
                    symbols = [normalized_type]
            if not symbols:
                # Unknown energy defaults to a single Colorless unit.
                symbols = ["C"]
            provided.append(symbols)
    if not provided:
        provided = [["C"] for _ in range(max(0, int(active.get("energy_attached", 0))))]
    return provided


def evaluate_attack_cost(active: dict[str, Any], attack: dict[str, Any]) -> AttackCostResult:
    raw_cost = attack.get("cost", [])
    if raw_cost is None:
        raw_cost = []
    if not isinstance(raw_cost, list):
        return AttackCostResult(
            payable=False,
            code="malformed_attack_cost",
            reason="attack cost is malformed",
            required_symbols=[],
            attached_symbols=[],
            missing_symbols=[],
        )

    required_symbols = [symbol for symbol in (_normalize_energy_symbol(entry) for entry in raw_cost) if symbol]
    colorless_required = sum(1 for symbol in required_symbols if symbol == "C")
    typed_requirements: dict[str, int] = {}
    for symbol in required_symbols:
        if symbol == "C":
            continue
        typed_requirements[symbol] = typed_requirements.get(symbol, 0) + 1

    attached_energy = _attached_energy_provides(active)
    used_indexes: set[int] = set()
    missing_symbols: list[str] = []

    for symbol, required_count in typed_requirements.items():
        for _ in range(required_count):
            match_index = next(
                (
                    idx
                    for idx, options in enumerate(attached_energy)
                    if idx not in used_indexes and symbol in options
                ),
                None,
            )
            if match_index is None:
                missing_symbols.append(symbol)
            else:
                used_indexes.add(match_index)

    remaining_energy = len(attached_energy) - len(used_indexes)
    if remaining_energy < colorless_required:
        missing_symbols.extend(["C"] * (colorless_required - remaining_energy))

    attached_symbols = [options[0] if options else "C" for options in attached_energy]
    if missing_symbols:
        return AttackCostResult(
            payable=False,
            code="insufficient_energy",
            reason=f"missing energy symbols: {', '.join(missing_symbols)}",
            required_symbols=required_symbols,
            attached_symbols=attached_symbols,
            missing_symbols=missing_symbols,
        )
    return AttackCostResult(
        payable=True,
        code="ok",
        reason="attack cost can be paid",
        required_symbols=required_symbols,
        attached_symbols=attached_symbols,
        missing_symbols=[],
    )


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
        hand_cards = player.get("hand_cards", [])
        if isinstance(hand_cards, list) and hand_cards:
            if len(hand_cards) < count:
                self._events.append(f"{actor} failed hand-cost payment ({count}).")
                return False
            del hand_cards[:count]
            player["hand_size"] = len(hand_cards)
            self._events.append(f"{actor} paid hand cost of {count} card(s).")
            return True

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
        attached_cards = active.get("attached_energy_cards", [])
        if isinstance(attached_cards, list) and attached_cards:
            del attached_cards[:count]
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
    result = evaluate_attack_cost(active, attack)
    return result.payable, result.reason
