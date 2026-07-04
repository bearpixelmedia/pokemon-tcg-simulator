from __future__ import annotations

import random
from typing import Any

from core.effect_types import EffectOperation, EffectProgram


def create_demo_state() -> dict[str, Any]:
    return {
        "players": {
            "p1": {
                "name": "You",
                "hand_size": 5,
                "active": {"hp": 120, "max_hp": 120, "status": []},
            },
            "p2": {
                "name": "AI",
                "hand_size": 5,
                "active": {"hp": 120, "max_hp": 120, "status": []},
            },
        }
    }


def _opponent(actor: str) -> str:
    return "p2" if actor == "p1" else "p1"


def _target_slot(state: dict[str, Any], actor: str, target: str) -> dict[str, Any]:
    if target == "self_active":
        return state["players"][actor]["active"]
    if target == "opponent_active":
        return state["players"][_opponent(actor)]["active"]
    raise ValueError(f"Unsupported target '{target}' for demo engine")


def _coerce_operation(operation: EffectOperation | dict[str, Any]) -> EffectOperation:
    if isinstance(operation, EffectOperation):
        return operation
    return EffectOperation(op=operation.get("op", "unknown"), params=operation.get("params", {}))


def apply_effect_program(
    program: EffectProgram,
    state: dict[str, Any],
    actor: str,
    rng: random.Random | None = None,
) -> list[str]:
    rng = rng or random.Random()
    events: list[str] = []
    for operation in program.operations:
        _apply_operation(operation, state, actor, rng, events)
    return events


def _apply_operation(
    operation: EffectOperation | dict[str, Any],
    state: dict[str, Any],
    actor: str,
    rng: random.Random,
    events: list[str],
) -> None:
    normalized = _coerce_operation(operation)

    if normalized.op == "deal_damage":
        slot = _target_slot(state, actor, normalized.params["target"])
        amount = int(normalized.params["amount"])
        slot["hp"] = max(0, slot["hp"] - amount)
        events.append(f"{actor} dealt {amount} damage to {normalized.params['target']}.")
        return

    if normalized.op == "heal_damage":
        slot = _target_slot(state, actor, normalized.params["target"])
        amount = int(normalized.params["amount"])
        slot["hp"] = min(slot["max_hp"], slot["hp"] + amount)
        events.append(f"{actor} healed {amount} damage on {normalized.params['target']}.")
        return

    if normalized.op == "apply_status":
        slot = _target_slot(state, actor, normalized.params["target"])
        status = normalized.params["status"]
        if status not in slot["status"]:
            slot["status"].append(status)
        events.append(f"{actor} applied {status} to {normalized.params['target']}.")
        return

    if normalized.op == "draw_cards":
        draw_count = int(normalized.params["count"])
        state["players"][actor]["hand_size"] += draw_count
        events.append(f"{actor} drew {draw_count} cards.")
        return

    if normalized.op == "flip_coin":
        result = rng.choice(["heads", "tails"])
        events.append(f"{actor} flipped {result}.")
        for branch_operation in normalized.params.get(result, []):
            _apply_operation(branch_operation, state, actor, rng, events)
        return

    events.append(f"{actor} has unsupported operation: {normalized.op}")


def apply_pokemon_checkup(
    state: dict[str, Any], actor: str, rng: random.Random | None = None
) -> list[str]:
    rng = rng or random.Random()
    events: list[str] = []
    target = state["players"][actor]["active"]
    statuses = list(target["status"])

    if "Poisoned" in statuses:
        target["hp"] = max(0, target["hp"] - 10)
        events.append(f"{actor} took 10 poison damage.")

    if "Burned" in statuses:
        target["hp"] = max(0, target["hp"] - 20)
        events.append(f"{actor} took 20 burn damage.")
        if rng.choice(["heads", "tails"]) == "heads":
            target["status"] = [status for status in target["status"] if status != "Burned"]
            events.append(f"{actor} recovered from Burned.")

    if "Asleep" in statuses and rng.choice(["heads", "tails"]) == "heads":
        target["status"] = [status for status in target["status"] if status != "Asleep"]
        events.append(f"{actor} woke up from Asleep.")

    return events

