from __future__ import annotations

import random
from typing import Any

from core.card_blueprints import build_card_from_blueprint, list_blueprints
from core.effects import apply_effect_program, apply_pokemon_checkup, create_demo_state
from core.text_compiler import compile_effect_text, supported_templates


def analyze_card_text(text: str) -> dict[str, Any]:
    program = compile_effect_text(text)
    return {
        "compiler": {
            "supported_templates": supported_templates(),
        },
        "program": program.to_dict(),
    }


def build_blueprint_card(blueprint_key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_card_from_blueprint(blueprint_key, variables)


def run_simulation(turn_limit: int = 10, seed: int | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    state = create_demo_state()
    event_log: list[dict[str, Any]] = []
    compiled_cards: list[dict[str, Any]] = []

    for turn in range(1, turn_limit + 1):
        actor = "p1" if turn % 2 == 1 else "p2"
        target = "p2" if actor == "p1" else "p1"

        blueprint_key = rng.choice(["toxic_strike", "volatile_strike", "tactical_draw"])
        variables = {
            "damage": rng.choice([20, 30, 40]),
            "bonus": rng.choice([20, 30, 40]),
            "draw_count": rng.choice([1, 2, 3]),
            "heal_amount": rng.choice([10, 20, 30]),
            "status": rng.choice(["Poisoned", "Burned", "Paralyzed"]),
            "self_status": "Confused",
        }

        built_card = build_card_from_blueprint(blueprint_key, variables)
        compiled_cards.append(
            {
                "turn": turn,
                "actor": actor,
                "blueprint_key": blueprint_key,
                "rendered_text": built_card["rendered_text"],
                "compiled_program": built_card["compiled_program"],
            }
        )

        program = compile_effect_text(built_card["rendered_text"])
        attack_events = apply_effect_program(program, state, actor, rng)
        checkup_events = apply_pokemon_checkup(state, actor, rng)
        opponent_checkup_events = apply_pokemon_checkup(state, target, rng)

        event_log.append(
            {
                "turn": turn,
                "actor": actor,
                "card_text": built_card["rendered_text"],
                "is_fully_resolved": program.is_fully_resolved,
                "events": attack_events + checkup_events + opponent_checkup_events,
                "hp": {
                    "you": state["players"]["p1"]["active"]["hp"],
                    "ai": state["players"]["p2"]["active"]["hp"],
                },
            }
        )

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
    }

