from __future__ import annotations

from typing import Any, Callable

from core.cost_engine import evaluate_attack_cost
from core.official_rules import MAX_BENCH_SIZE, validate_action_against_rules
from core.targeting import validate_target_selector
from core.trainer_lifecycle import can_attach_tool, can_play_stadium, can_play_supporter


def _add_reason(container: list[dict[str, str]], code: str, detail: str) -> None:
    container.append({"code": code, "detail": detail})


def _reason_summary(reasons: list[dict[str, str]], legal_message: str) -> str:
    if reasons:
        return reasons[0]["detail"]
    return legal_message


def _count_hand_cards(player: dict[str, Any], matcher: Callable[[dict[str, Any]], bool], fallback_key: str) -> int:
    hand_cards = player.get("hand_cards", [])
    if isinstance(hand_cards, list) and hand_cards:
        has_type_metadata = any(
            isinstance(card, dict) and (card.get("subtype") or card.get("trainer_type"))
            for card in hand_cards
        )
        matched = sum(1 for card in hand_cards if isinstance(card, dict) and matcher(card))
        if has_type_metadata:
            return matched
        # Legacy demos often only track aggregate hand_* counters.
        if matched <= 0:
            return max(0, int(player.get(fallback_key, 0)))
        return matched
    return max(0, int(player.get(fallback_key, 0)))


def _is_supporter(card: dict[str, Any]) -> bool:
    if str(card.get("subtype", "")).lower() == "supporter":
        return True
    if str(card.get("trainer_type", "")).lower() == "supporter":
        return True
    return False


def _is_stadium(card: dict[str, Any]) -> bool:
    if str(card.get("subtype", "")).lower() == "stadium":
        return True
    if str(card.get("trainer_type", "")).lower() == "stadium":
        return True
    return False


def _is_tool(card: dict[str, Any]) -> bool:
    if str(card.get("subtype", "")).lower() in {"tool", "pokemon tool"}:
        return True
    if str(card.get("trainer_type", "")).lower() in {"tool", "pokemon tool"}:
        return True
    return False


def _has_basic_in_hand(player: dict[str, Any]) -> bool:
    hand_cards = player.get("hand_cards", [])
    if isinstance(hand_cards, list) and hand_cards:
        return any(isinstance(card, dict) and bool(card.get("is_basic", False)) for card in hand_cards)
    return int(player.get("hand_basics", 0)) > 0


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
        attack_name = attack.get("name", "attack") if isinstance(attack, dict) else "attack"
        attack_cost_eval = evaluate_attack_cost(active, attack if isinstance(attack, dict) else {})
        attack_cost = attack_cost_eval.required_symbols
        reasons: list[dict[str, str]] = []
        if not attack_rule_legal:
            _add_reason(reasons, "official_rule", attack_rule_reason)
        if not attack_cost_eval.payable:
            _add_reason(reasons, attack_cost_eval.code, attack_cost_eval.reason)
        legal = not reasons
        actions.append(
            {
                "action_type": "attack",
                "attack_name": attack_name,
                "legal": legal,
                "reason": _reason_summary(reasons, "attack legal"),
                "illegal_reasons": reasons,
                "cost_preview": {
                    "symbols": attack_cost,
                    "required_count": len(attack_cost),
                    "attached_symbols": attack_cost_eval.attached_symbols,
                    "missing_symbols": attack_cost_eval.missing_symbols,
                },
                "rule_refs": ["first_turn_no_attack", "attack_cost_symbols"],
            }
        )

    # Retreat legality with target and cost checks.
    retreat_target = validate_target_selector(state, actor, "self_bench")
    retreat_rule_legal, retreat_rule_reason = validate_action_against_rules(state, actor, "retreat")
    retreat_reasons: list[dict[str, str]] = []
    if not retreat_rule_legal:
        _add_reason(retreat_reasons, "official_rule", retreat_rule_reason)
    if not retreat_target.valid:
        _add_reason(retreat_reasons, "invalid_target", retreat_target.reason)
    if "Asleep" in statuses or "Paralyzed" in statuses:
        _add_reason(retreat_reasons, "status_blocks_retreat", "active status blocks retreat")
    if int(active.get("energy_attached", 0)) < int(active.get("retreat_cost", 1)):
        _add_reason(retreat_reasons, "insufficient_retreat_energy", "cannot pay retreat cost")
    if bench_count <= 0:
        _add_reason(retreat_reasons, "bench_required", "requires at least one benched Pokémon")
    can_retreat = not retreat_reasons
    actions.append(
        {
            "action_type": "retreat",
            "legal": can_retreat,
            "reason": _reason_summary(retreat_reasons, "retreat available"),
            "illegal_reasons": retreat_reasons,
            "rule_refs": ["retreat_cost", "bench_required"],
        }
    )

    supporter_count = _count_hand_cards(player, _is_supporter, "hand_supporters")
    supporter_rule_legal, supporter_rule_reason = validate_action_against_rules(state, actor, "play_supporter")
    supporter_ok, supporter_reason = can_play_supporter(state, actor)
    supporter_reasons: list[dict[str, str]] = []
    if not supporter_rule_legal:
        _add_reason(supporter_reasons, "official_rule", supporter_rule_reason)
    if not supporter_ok:
        _add_reason(supporter_reasons, "supporter_lifecycle", supporter_reason)
    if supporter_count <= 0:
        _add_reason(supporter_reasons, "no_supporter_card", "no supporter card in hand")
    actions.append(
        {
            "action_type": "play_supporter",
            "legal": not supporter_reasons,
            "reason": _reason_summary(supporter_reasons, "supporter available"),
            "illegal_reasons": supporter_reasons,
            "rule_refs": ["first_turn_no_supporter", "supporter_once_per_turn"],
        }
    )

    stadium_count = _count_hand_cards(player, _is_stadium, "hand_stadiums")
    stadium_rule_legal, stadium_rule_reason = validate_action_against_rules(state, actor, "play_stadium")
    can_stadium_play, stadium_reason = can_play_stadium(state, actor)
    stadium_reasons: list[dict[str, str]] = []
    if not stadium_rule_legal:
        _add_reason(stadium_reasons, "official_rule", stadium_rule_reason)
    if not can_stadium_play:
        _add_reason(stadium_reasons, "stadium_lifecycle", stadium_reason)
    if stadium_count <= 0:
        _add_reason(stadium_reasons, "no_stadium_card", "no stadium card in hand")
    can_stadium = not stadium_reasons
    actions.append(
        {
            "action_type": "play_stadium",
            "legal": can_stadium,
            "reason": _reason_summary(stadium_reasons, "stadium available"),
            "illegal_reasons": stadium_reasons,
            "rule_refs": ["stadium_play_once_per_turn"],
        }
    )

    tool_count = _count_hand_cards(player, _is_tool, "hand_tools")
    tool_rule_legal, tool_rule_reason = validate_action_against_rules(state, actor, "attach_tool")
    can_attach, tool_reason = can_attach_tool(state, actor)
    tool_reasons: list[dict[str, str]] = []
    if not tool_rule_legal:
        _add_reason(tool_reasons, "official_rule", tool_rule_reason)
    if not can_attach:
        _add_reason(tool_reasons, "tool_lifecycle", tool_reason)
    if tool_count <= 0:
        _add_reason(tool_reasons, "no_tool_card", "no tool card in hand")
    can_tool = not tool_reasons
    actions.append(
        {
            "action_type": "attach_tool",
            "legal": can_tool,
            "reason": _reason_summary(tool_reasons, "tool can be attached"),
            "illegal_reasons": tool_reasons,
            "rule_refs": ["one_tool_per_pokemon"],
        }
    )

    evolve_reasons: list[dict[str, str]] = []
    evolve_rule_legal, evolve_rule_reason = validate_action_against_rules(state, actor, "evolve")
    if not evolve_rule_legal:
        _add_reason(evolve_reasons, "official_rule", evolve_rule_reason)
    if active.get("stage", "Basic") not in {"Basic", "Stage1"}:
        _add_reason(evolve_reasons, "invalid_stage", "pokemon cannot evolve further")
    if bool(active.get("just_played_this_turn", False)):
        _add_reason(evolve_reasons, "turn_in_play_requirement", "pokemon must be in play since start of turn")
    if bool(active.get("evolved_this_turn", False)):
        _add_reason(evolve_reasons, "already_evolved", "pokemon already evolved this turn")
    can_evolve = not evolve_reasons
    actions.append(
        {
            "action_type": "evolve",
            "legal": can_evolve,
            "reason": _reason_summary(evolve_reasons, "evolution available"),
            "illegal_reasons": evolve_reasons,
            "rule_refs": ["evolution_stage_rules"],
        }
    )

    devolve_reasons: list[dict[str, str]] = []
    devolve_rule_legal, devolve_rule_reason = validate_action_against_rules(state, actor, "devolve")
    if not devolve_rule_legal:
        _add_reason(devolve_reasons, "official_rule", devolve_rule_reason)
    if active.get("stage", "Basic") not in {"Stage1", "Stage2"}:
        _add_reason(devolve_reasons, "already_basic", "pokemon is already basic")
    can_devolve = not devolve_reasons
    actions.append(
        {
            "action_type": "devolve",
            "legal": can_devolve,
            "reason": _reason_summary(devolve_reasons, "devolution available"),
            "illegal_reasons": devolve_reasons,
            "rule_refs": ["devolution_stage_rules"],
        }
    )

    bench_reasons: list[dict[str, str]] = []
    bench_rule_legal, bench_rule_reason = validate_action_against_rules(state, actor, "bench_pokemon")
    if not bench_rule_legal:
        _add_reason(bench_reasons, "official_rule", bench_rule_reason)
    if bench_count >= MAX_BENCH_SIZE:
        _add_reason(bench_reasons, "bench_full", f"bench is full ({MAX_BENCH_SIZE})")
    if not _has_basic_in_hand(player):
        _add_reason(bench_reasons, "no_basic_in_hand", "no basic pokemon available to bench")
    can_bench = not bench_reasons
    actions.append(
        {
            "action_type": "bench_pokemon",
            "legal": can_bench,
            "reason": _reason_summary(bench_reasons, "bench slot available"),
            "illegal_reasons": bench_reasons,
            "rule_refs": ["max_bench_size"],
        }
    )

    actions.append({"action_type": "pass", "legal": True, "reason": "always legal", "illegal_reasons": []})
    return actions
