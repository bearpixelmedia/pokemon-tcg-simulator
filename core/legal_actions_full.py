from __future__ import annotations

from typing import Any

from core.cost_engine import pay_cost
from core.targeting import validate_target_selector


def generate_legal_actions_full(state: dict[str, Any], actor: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    active = state["players"][actor]["active"]

    # Attack preview legality with simple active-energy cost assumption.
    attack_cost = 1
    can_pay_attack = int(active.get("energy_attached", 0)) >= attack_cost
    actions.append(
        {
            "action_type": "attack",
            "legal": can_pay_attack,
            "reason": "enough active energy" if can_pay_attack else "insufficient active energy",
            "cost_preview": {"active_energy": attack_cost},
        }
    )

    # Retreat legality with target and cost checks.
    retreat_target = validate_target_selector(state, actor, "self_bench")
    can_retreat = retreat_target.valid and int(active.get("energy_attached", 0)) >= int(active.get("retreat_cost", 1))
    actions.append(
        {
            "action_type": "retreat",
            "legal": can_retreat,
            "reason": "retreat available" if can_retreat else retreat_target.reason or "cannot pay retreat cost",
        }
    )

    # Supporter play preview (hand-card transaction semantics).
    cost_preview = pay_cost(state={"players": {actor: {"hand_size": state["players"][actor].get("hand_supporters", 0), "active": {"energy_attached": 0}}}}, actor=actor, requirements={"hand_cards": 1})
    actions.append(
        {
            "action_type": "play_supporter",
            "legal": cost_preview.paid,
            "reason": "supporter available" if cost_preview.paid else "no supporter in hand",
        }
    )

    actions.append({"action_type": "pass", "legal": True, "reason": "always legal"})
    return actions
