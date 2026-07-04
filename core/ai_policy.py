from __future__ import annotations

import random
from typing import Any

from core.card_blueprints import list_blueprints


def _estimate_attack_damage(blueprint_key: str) -> int:
    if blueprint_key == "volatile_strike":
        return 50
    if blueprint_key == "toxic_strike":
        return 35
    if blueprint_key == "pivot_guard":
        return 20
    if blueprint_key == "energy_recycle":
        return 10
    if blueprint_key == "setup_search":
        return 10
    return 25


def generate_legal_actions(state: dict[str, Any], actor: str) -> list[dict[str, Any]]:
    player = state["players"][actor]
    active = player["active"]
    statuses = set(active.get("status", []))
    actions: list[dict[str, Any]] = [{"action_type": "pass"}]

    for blueprint in list_blueprints():
        actions.append({"action_type": "attack", "blueprint_key": blueprint["key"]})

    if player.get("bench_size", 0) > 0 and "Asleep" not in statuses and "Paralyzed" not in statuses:
        if int(active.get("energy_attached", 0)) >= int(active.get("retreat_cost", 1)):
            actions.append({"action_type": "retreat"})

    stage = active.get("stage", "Basic")
    if stage in {"Basic", "Stage1"}:
        actions.append({"action_type": "evolve"})
    if stage in {"Stage1", "Stage2"}:
        actions.append({"action_type": "devolve"})

    return actions


def choose_action_heuristic(
    state: dict[str, Any],
    actor: str,
    actions: list[dict[str, Any]],
    rng: random.Random,
) -> dict[str, Any]:
    player = state["players"][actor]
    opponent = state["players"]["p2" if actor == "p1" else "p1"]
    hp = int(player["active"].get("hp", 0))
    opponent_hp = int(opponent["active"].get("hp", 0))
    stage = player["active"].get("stage", "Basic")

    retreat_action = next((action for action in actions if action["action_type"] == "retreat"), None)
    evolve_action = next((action for action in actions if action["action_type"] == "evolve"), None)

    attack_actions = [action for action in actions if action["action_type"] == "attack"]
    if attack_actions:
        attack_actions.sort(
            key=lambda action: _estimate_attack_damage(action["blueprint_key"]),
            reverse=True,
        )
        finishing_attack = next(
            (
                action
                for action in attack_actions
                if _estimate_attack_damage(action["blueprint_key"]) >= opponent_hp
            ),
            None,
        )
        if finishing_attack:
            return finishing_attack

    if retreat_action and hp <= 40:
        return retreat_action

    if evolve_action and stage == "Basic" and rng.random() < 0.35:
        return evolve_action

    if attack_actions:
        top_damage = _estimate_attack_damage(attack_actions[0]["blueprint_key"])
        top_options = [
            action
            for action in attack_actions
            if _estimate_attack_damage(action["blueprint_key"]) == top_damage
        ]
        return rng.choice(top_options)

    return {"action_type": "pass"}

