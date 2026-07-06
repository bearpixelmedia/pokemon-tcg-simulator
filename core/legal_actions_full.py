from __future__ import annotations

from typing import Any

from core.cost_engine import can_pay_attack_cost, pay_cost
from core.official_rules import MAX_BENCH_SIZE, validate_action_against_rules
from core.targeting import validate_target_selector


def generate_legal_actions_full(state: dict[str, Any], actor: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    player = state["players"][actor]
    active = state["players"][actor]["active"]
    bench_count = len(player.get("bench", [])) if isinstance(player.get("bench"), list) else int(player.get("bench_size", 0))
    statuses = set(active.get("status", []))

    attack_rule_legal, attack_rule_reason = validate_action_against_rules(state, actor, "attack")
    attacks = active.get("attacks", [])
    if not isinstance(attacks, list) or not attacks:
        attacks = [{"name": "Default Attack", "cost": ["C"], "damage": 20}]
    for attack in attacks:
        can_pay_attack, cost_reason = can_pay_attack_cost(active, attack if isinstance(attack, dict) else {})
        attack_name = attack.get("name", "attack") if isinstance(attack, dict) else "attack"
        attack_cost = attack.get("cost", []) if isinstance(attack, dict) else []
        actions.append(
            {
                "action_type": "attack",
                "attack_name": attack_name,
                "legal": bool(can_pay_attack and attack_rule_legal),
                "reason": attack_rule_reason if not attack_rule_legal else cost_reason,
                "cost_preview": {"symbols": attack_cost, "required_count": len(attack_cost)},
                "rule_refs": ["first_turn_no_attack", "attack_cost_symbols"],
            }
        )

    # Retreat legality with target and cost checks.
    retreat_target = validate_target_selector(state, actor, "self_bench")
    can_retreat = (
        retreat_target.valid
        and bench_count > 0
        and "Asleep" not in statuses
        and "Paralyzed" not in statuses
        and int(active.get("energy_attached", 0)) >= int(active.get("retreat_cost", 1))
    )
    retreat_rule_legal, retreat_rule_reason = validate_action_against_rules(state, actor, "retreat")
    actions.append(
        {
            "action_type": "retreat",
            "legal": bool(can_retreat and retreat_rule_legal),
            "reason": (
                retreat_rule_reason
                if not retreat_rule_legal
                else ("retreat available" if can_retreat else retreat_target.reason or "cannot pay retreat cost")
            ),
            "rule_refs": ["retreat_cost", "bench_required"],
        }
    )

    # Supporter play preview (hand-card transaction semantics).
    cost_preview = pay_cost(
        state={"players": {actor: {"hand_size": player.get("hand_supporters", 0), "active": {"energy_attached": 0}}}},
        actor=actor,
        requirements={"hand_cards": 1},
    )
    supporter_rule_legal, supporter_rule_reason = validate_action_against_rules(state, actor, "play_supporter")
    actions.append(
        {
            "action_type": "play_supporter",
            "legal": bool(cost_preview.paid and supporter_rule_legal),
            "reason": supporter_rule_reason if not supporter_rule_legal else ("supporter available" if cost_preview.paid else "no supporter in hand"),
            "rule_refs": ["first_turn_no_supporter", "supporter_once_per_turn"],
        }
    )

    can_stadium = int(player.get("hand_stadiums", 0)) > 0
    actions.append(
        {
            "action_type": "play_stadium",
            "legal": can_stadium,
            "reason": "stadium available" if can_stadium else "no stadium in hand",
            "rule_refs": ["stadium_play_once_per_turn"],
        }
    )

    can_tool = int(player.get("hand_tools", 0)) > 0 and not bool(active.get("tool_attached"))
    actions.append(
        {
            "action_type": "attach_tool",
            "legal": can_tool,
            "reason": "tool can be attached" if can_tool else "no tool in hand or active already has tool",
            "rule_refs": ["one_tool_per_pokemon"],
        }
    )

    can_evolve = active.get("stage", "Basic") in {"Basic", "Stage1"}
    actions.append(
        {
            "action_type": "evolve",
            "legal": can_evolve,
            "reason": "evolution stage available" if can_evolve else "pokemon cannot evolve further",
            "rule_refs": ["evolution_stage_rules"],
        }
    )

    can_devolve = active.get("stage", "Basic") in {"Stage1", "Stage2"}
    actions.append(
        {
            "action_type": "devolve",
            "legal": can_devolve,
            "reason": "devolution stage available" if can_devolve else "pokemon is already basic",
            "rule_refs": ["devolution_stage_rules"],
        }
    )

    can_bench = bench_count < MAX_BENCH_SIZE
    actions.append(
        {
            "action_type": "bench_pokemon",
            "legal": can_bench,
            "reason": "bench slot available" if can_bench else f"bench is full ({MAX_BENCH_SIZE})",
            "rule_refs": ["max_bench_size"],
        }
    )

    actions.append({"action_type": "pass", "legal": True, "reason": "always legal"})
    return actions
