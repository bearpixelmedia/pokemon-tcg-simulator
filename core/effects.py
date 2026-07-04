from __future__ import annotations

import random
from typing import Any

from core.effect_types import EffectOperation, EffectProgram
_ROTATING_STATUSES = {"Asleep", "Confused", "Paralyzed"}


def create_demo_state() -> dict[str, Any]:
    return {
        "players": {
            "p1": {
                "name": "You",
                "hand_size": 5,
                "active": {"hp": 120, "max_hp": 120, "status": [], "energy_attached": 1},
                "bench_size": 2,
            },
            "p2": {
                "name": "AI",
                "hand_size": 5,
                "active": {"hp": 120, "max_hp": 120, "status": [], "energy_attached": 1},
                "bench_size": 2,
            },
        }
    }


def _opponent(actor: str) -> str:
    return "p2" if actor == "p1" else "p1"


def _target_slot(state: dict[str, Any], actor: str, target: str) -> dict[str, Any]:
    if target in {"self_active", "self_pokemon"}:
        return state["players"][actor]["active"]
    if target == "opponent_active":
        return state["players"][_opponent(actor)]["active"]
    if target == "opponent_bench":
        return state["players"][_opponent(actor)]["active"]
    raise ValueError(f"Unsupported target '{target}' for demo engine")


def _coerce_operation(operation: EffectOperation | dict[str, Any]) -> EffectOperation:
    if isinstance(operation, EffectOperation):
        return operation
    return EffectOperation(op=operation.get("op", "unknown"), params=operation.get("params", {}))


def _apply_status_to_slot(slot: dict[str, Any], status: str) -> None:
    statuses = [value for value in slot.get("status", []) if isinstance(value, str)]

    if status in _ROTATING_STATUSES:
        statuses = [existing for existing in statuses if existing not in _ROTATING_STATUSES]
    elif status in statuses:
        slot["status"] = statuses
        return

    if status not in statuses:
        statuses.append(status)
    slot["status"] = statuses

    if status == "Paralyzed":
        # Paralysis expires during Pokémon Checkup after the owner's next turn.
        slot["paralyzed_turns_remaining"] = 1


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
        _apply_status_to_slot(slot, status)
        events.append(f"{actor} applied {status} to {normalized.params['target']}.")
        return

    if normalized.op == "draw_cards":
        draw_count = int(normalized.params["count"])
        state["players"][actor]["hand_size"] += draw_count
        events.append(f"{actor} drew {draw_count} cards.")
        return

    if normalized.op == "draw_until_hand_size":
        target_size = int(normalized.params["count"])
        current = state["players"][actor]["hand_size"]
        if current < target_size:
            drawn = target_size - current
            state["players"][actor]["hand_size"] = target_size
            events.append(f"{actor} drew {drawn} cards to reach hand size {target_size}.")
        else:
            events.append(f"{actor} already has at least {target_size} cards in hand.")
        return

    if normalized.op == "search_deck_to_hand":
        count = int(normalized.params.get("count", 1))
        state["players"][actor]["hand_size"] += count
        descriptor = normalized.params.get("descriptor", "matching")
        events.append(f"{actor} searched deck for {count} {descriptor} card(s).")
        return

    if normalized.op == "shuffle_deck":
        events.append(f"{actor} shuffled their deck.")
        return

    if normalized.op == "switch_active_with_bench":
        target = normalized.params.get("target", "self_player")
        owner = actor if target == "self_player" else _opponent(actor)
        events.append(f"{owner} switched their Active Pokémon with a Benched Pokémon.")
        return

    if normalized.op == "discard_energy":
        slot = _target_slot(state, actor, normalized.params["target"])
        count = int(normalized.params.get("count", 1))
        if count < 0:
            discarded = slot.get("energy_attached", 0)
            slot["energy_attached"] = 0
        else:
            discarded = min(slot.get("energy_attached", 0), count)
            slot["energy_attached"] = max(0, slot.get("energy_attached", 0) - discarded)
        events.append(f"{actor} discarded {discarded} Energy from {normalized.params['target']}.")
        return

    if normalized.op == "attach_energy":
        count = int(normalized.params.get("count", 1))
        slot = state["players"][actor]["active"]
        slot["energy_attached"] = slot.get("energy_attached", 0) + count
        events.append(f"{actor} attached {count} Energy from {normalized.params.get('source', 'unknown')}.")
        return

    if normalized.op == "modify_incoming_damage_next_turn":
        slot = state["players"][actor]["active"]
        slot["incoming_damage_reduction_next_turn"] = int(normalized.params.get("amount", 0))
        events.append(
            f"{actor} gained {slot['incoming_damage_reduction_next_turn']} damage reduction for next turn."
        )
        return

    if normalized.op in {"ignore_weakness_resistance", "apply_temporary_rule", "select_opponent_bench"}:
        events.append(f"{actor} prepared effect: {normalized.op}.")
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
    statuses = list(target.get("status", []))

    # Pokémon Checkup special condition order:
    # Poisoned -> Burned -> Asleep -> Paralyzed
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

    if "Paralyzed" in statuses:
        remaining = int(target.get("paralyzed_turns_remaining", 1))
        remaining -= 1
        if remaining <= 0:
            target["status"] = [status for status in target["status"] if status != "Paralyzed"]
            target.pop("paralyzed_turns_remaining", None)
            events.append(f"{actor} recovered from Paralyzed.")
        else:
            target["paralyzed_turns_remaining"] = remaining

    return events

