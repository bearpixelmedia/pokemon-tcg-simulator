from __future__ import annotations

import hashlib
import json
import random
from enum import Enum
from typing import Any

from core.card_blueprints import list_blueprints
from core.effects import apply_effect_program, apply_pokemon_checkup, create_demo_state
from core.text_compiler import compile_effect_text


class TurnPhase(str, Enum):
    TURN_START = "TURN_START"
    ACTION_SELECTION = "ACTION_SELECTION"
    BEFORE_ATTACK = "BEFORE_ATTACK"
    ATTACK_RESOLUTION = "ATTACK_RESOLUTION"
    BETWEEN_TURNS_CHECKUP = "BETWEEN_TURNS_CHECKUP"
    TURN_END = "TURN_END"


def _phase_events(phase: TurnPhase, events: list[str]) -> dict[str, Any]:
    return {"phase": phase.value, "events": events}


def _state_checksum(state: dict[str, Any]) -> str:
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _event_log_checksum(event_log: list[dict[str, Any]]) -> str:
    encoded = json.dumps(event_log, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _random_action_for_blueprint(rng: random.Random, blueprint_key: str) -> dict[str, Any]:
    if blueprint_key == "toxic_strike":
        return {"damage": rng.choice([20, 30, 40]), "status": rng.choice(["Poisoned", "Burned", "Paralyzed"])}
    if blueprint_key == "volatile_strike":
        return {
            "damage": rng.choice([20, 30, 40]),
            "bonus": rng.choice([20, 30, 40]),
            "self_status": "Confused",
        }
    if blueprint_key == "tactical_draw":
        return {"draw_count": rng.choice([1, 2, 3]), "heal_amount": rng.choice([10, 20, 30])}
    if blueprint_key == "setup_search":
        return {"descriptor": rng.choice(["Basic Pokémon", "Supporter", "Item", "Basic Energy"])}
    if blueprint_key == "pivot_guard":
        return {"reduction": rng.choice([20, 30, 40])}
    if blueprint_key == "energy_recycle":
        return {"count": rng.choice([1, 2]), "descriptor": rng.choice(["Basic", "Special"])}
    return {}


def _build_turn_action(rng: random.Random) -> dict[str, Any]:
    blueprint_keys = [entry["key"] for entry in list_blueprints()]
    blueprint_key = rng.choice(blueprint_keys)
    return {
        "blueprint_key": blueprint_key,
        "variables": _random_action_for_blueprint(rng, blueprint_key),
    }


def _active_slot(state: dict[str, Any], actor: str) -> dict[str, Any]:
    return state["players"][actor]["active"]


def _attack_allowed(state: dict[str, Any], actor: str, rng: random.Random) -> tuple[bool, list[str]]:
    events: list[str] = []
    active = _active_slot(state, actor)
    statuses = list(active.get("status", []))

    if "Paralyzed" in statuses:
        events.append(f"{actor} cannot attack while Paralyzed.")
        return False, events

    if "Asleep" in statuses:
        events.append(f"{actor} cannot attack while Asleep.")
        return False, events

    if "Confused" in statuses:
        result = rng.choice(["heads", "tails"])
        events.append(f"{actor} is Confused and flipped {result}.")
        if result == "tails":
            active["hp"] = max(0, active["hp"] - 30)
            events.append(f"{actor} hurt itself in confusion for 30 damage.")
            return False, events

    return True, events


def run_turn_based_simulation(
    turn_limit: int = 10,
    seed: int | None = None,
    scripted_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rng_seed = seed if seed is not None else random.SystemRandom().randint(0, 2**31 - 1)
    rng = random.Random(rng_seed)
    state = create_demo_state()
    event_log: list[dict[str, Any]] = []
    compiled_cards: list[dict[str, Any]] = []
    turn_actions: list[dict[str, Any]] = []

    for turn in range(1, turn_limit + 1):
        actor = "p1" if turn % 2 == 1 else "p2"
        target = "p2" if actor == "p1" else "p1"
        turn_entry: dict[str, Any] = {"turn": turn, "actor": actor, "phases": []}

        turn_entry["phases"].append(_phase_events(TurnPhase.TURN_START, [f"{actor} started turn {turn}."]))

        if scripted_actions and turn - 1 < len(scripted_actions):
            action = dict(scripted_actions[turn - 1])
        else:
            action = _build_turn_action(rng)

        blueprint_key = action["blueprint_key"]
        variables = action.get("variables", {})
        turn_actions.append({"turn": turn, "actor": actor, "blueprint_key": blueprint_key, "variables": variables})
        turn_entry["phases"].append(
            _phase_events(
                TurnPhase.ACTION_SELECTION,
                [f"{actor} selected blueprint '{blueprint_key}' with variables {variables}."],
            )
        )

        from core.card_blueprints import build_card_from_blueprint  # local to avoid circular import risks

        built_card = build_card_from_blueprint(blueprint_key, variables)
        compiled_cards.append(
            {
                "turn": turn,
                "actor": actor,
                "blueprint_key": blueprint_key,
                "variables": variables,
                "rendered_text": built_card["rendered_text"],
                "compiled_program": built_card["compiled_program"],
            }
        )

        program = compile_effect_text(built_card["rendered_text"])
        turn_entry["card_text"] = built_card["rendered_text"]
        turn_entry["is_fully_resolved"] = program.is_fully_resolved

        can_attack, before_attack_events = _attack_allowed(state, actor, rng)
        turn_entry["phases"].append(_phase_events(TurnPhase.BEFORE_ATTACK, before_attack_events))

        attack_events: list[str]
        if can_attack:
            attack_events = apply_effect_program(program, state, actor, rng)
        else:
            attack_events = [f"{actor}'s attack step was skipped due to status restrictions."]
        turn_entry["phases"].append(_phase_events(TurnPhase.ATTACK_RESOLUTION, attack_events))

        checkup_events = apply_pokemon_checkup(state, actor, rng)
        opponent_checkup_events = apply_pokemon_checkup(state, target, rng)
        turn_entry["phases"].append(
            _phase_events(TurnPhase.BETWEEN_TURNS_CHECKUP, checkup_events + opponent_checkup_events)
        )

        turn_entry["phases"].append(_phase_events(TurnPhase.TURN_END, [f"{actor} ended turn {turn}."]))
        turn_entry["hp"] = {
            "you": state["players"]["p1"]["active"]["hp"],
            "ai": state["players"]["p2"]["active"]["hp"],
        }
        event_log.append(turn_entry)

        if state["players"]["p1"]["active"]["hp"] <= 0 or state["players"]["p2"]["active"]["hp"] <= 0:
            break

    p1_hp = state["players"]["p1"]["active"]["hp"]
    p2_hp = state["players"]["p2"]["active"]["hp"]
    if p1_hp == p2_hp:
        winner = "Draw"
    else:
        winner = "You" if p2_hp < p1_hp else "AI"

    return {
        "winner": winner,
        "turns": len(event_log),
        "final_hp": {"you": p1_hp, "ai": p2_hp},
        "event_log": event_log,
        "compiled_cards": compiled_cards,
        "available_blueprints": list_blueprints(),
        "replay": {
            "seed": rng_seed,
            "turn_limit": turn_limit,
            "turn_actions": turn_actions,
            "state_checksum": _state_checksum(state),
            "event_log_checksum": _event_log_checksum(event_log),
            "engine_version": "phase-machine-v1",
        },
    }


def verify_seed_replay(turn_limit: int = 10, seed: int | None = None) -> dict[str, Any]:
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**31 - 1)

    first = run_turn_based_simulation(turn_limit=turn_limit, seed=seed)
    second = run_turn_based_simulation(turn_limit=turn_limit, seed=seed)

    deterministic = (
        first["replay"]["state_checksum"] == second["replay"]["state_checksum"]
        and first["replay"]["event_log_checksum"] == second["replay"]["event_log_checksum"]
        and first["final_hp"] == second["final_hp"]
    )

    return {
        "deterministic": deterministic,
        "seed": seed,
        "turn_limit": turn_limit,
        "first": {
            "state_checksum": first["replay"]["state_checksum"],
            "event_log_checksum": first["replay"]["event_log_checksum"],
            "final_hp": first["final_hp"],
        },
        "second": {
            "state_checksum": second["replay"]["state_checksum"],
            "event_log_checksum": second["replay"]["event_log_checksum"],
            "final_hp": second["final_hp"],
        },
    }

