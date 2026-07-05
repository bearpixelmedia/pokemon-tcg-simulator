from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from core.effect_types import EffectOperation, EffectProgram
from core.script_fallbacks import resolve_script_fallback
from core.unresolved_registry import register_unresolved_clause

_STATUS_MAP = {
    "poisoned": "Poisoned",
    "burned": "Burned",
    "paralyzed": "Paralyzed",
    "asleep": "Asleep",
    "confused": "Confused",
}
_POKEMON_TOKEN = r"(?:Pokemon|Pokémon)"
_OPTIONAL_TEMPLATE = re.compile(r"^You may (?P<effect>.+)\.$", re.IGNORECASE)
_CONDITIONAL_TEMPLATE = re.compile(r"^If (?P<condition>.+?), (?P<effect>.+)\.$", re.IGNORECASE)
_ONCE_DURING_TURN_TEMPLATE = re.compile(
    r"^Once during your turn,(?: if (?P<condition>.+?),)? you may (?P<effect>.+)\.$",
    re.IGNORECASE,
)
_AS_OFTEN_DURING_TURN_TEMPLATE = re.compile(
    r"^As often as you like during your turn,(?: if (?P<condition>.+?),)? you may (?P<effect>.+)\.$",
    re.IGNORECASE,
)
_WHEN_PLAY_FROM_HAND_TO_BENCH_TEMPLATE = re.compile(
    rf"^When you play this {_POKEMON_TOKEN} from your hand onto your Bench during your turn, you may (?P<effect>.+)\.$",
    re.IGNORECASE,
)


def normalize_card_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("’", "'")
    cleaned = cleaned.replace("•", ". ")
    cleaned = re.sub(r"\[([A-Z])\]", r"{\1}", cleaned)
    cleaned = re.sub(r"^[•\-]\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


@dataclass(frozen=True)
class TextTemplate:
    name: str
    description: str
    pattern: re.Pattern[str]
    builder: Callable[[re.Match[str]], list[EffectOperation]]


def _coerce_count(raw: str) -> int:
    lowered = raw.strip().lower()
    if lowered in {"a", "an"}:
        return 1
    if lowered == "all":
        return -1
    return int(lowered)


def _build_triggered_effect(
    trigger: str,
    effect_text: str,
    condition: str | None = None,
) -> tuple[list[EffectOperation], str | None]:
    nested_text = effect_text.strip()
    if not nested_text.endswith("."):
        nested_text = f"{nested_text}."
    nested_program = compile_effect_text(nested_text)
    if not nested_program.is_fully_resolved or not nested_program.operations:
        return [], None
    return (
        [
            EffectOperation(
                op="triggered_effect",
                params={
                    "trigger": trigger,
                    "condition": (condition or "").strip(),
                    "operations": [operation.to_dict() for operation in nested_program.operations],
                },
            )
        ],
        "triggered_clause",
    )


def _script_hook_from_clause(hook_id: str, clause: str, extra: dict[str, str] | None = None) -> tuple[list[EffectOperation], str]:
    params: dict[str, str] = {"hook_id": hook_id, "clause": clause}
    if extra:
        params.update(extra)
    return ([EffectOperation(op="script_hook", params=params)], f"script_fallback_{hook_id}")


def _script_hook_builder(hook_id: str, group_names: tuple[str, ...] = ()) -> Callable[[re.Match[str]], list[EffectOperation]]:
    def _builder(match: re.Match[str]) -> list[EffectOperation]:
        params: dict[str, str] = {"hook_id": hook_id, "clause": match.group(0)}
        for name in group_names:
            value = match.groupdict().get(name)
            if value is not None:
                params[name] = value
        return [EffectOperation(op="script_hook", params=params)]

    return _builder


def _looks_like_tcg_clause(clause: str) -> bool:
    return bool(
        re.search(
            r"\b(?:pokemon|pokémon|energy|attack|ability|bench|active|prize|deck|discard|special condition|retreat|stadium|supporter|tool)\b",
            clause,
            flags=re.IGNORECASE,
        )
    )


def _damage_to_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="deal_damage",
            params={"target": "opponent_active", "amount": int(match.group("damage"))},
        )
    ]


def _damage_to_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(op="deal_damage", params={"target": "self_active", "amount": int(match.group("damage"))})
    ]


def _damage_to_self_also(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(op="deal_damage", params={"target": "self_active", "amount": int(match.group("damage"))})
    ]


def _bonus_damage_to_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="deal_damage",
            params={
                "target": "opponent_active",
                "amount": int(match.group("damage")),
                "kind": "bonus",
            },
        )
    ]


def _damage_to_bench(match: re.Match[str]) -> list[EffectOperation]:
    count_raw = match.groupdict().get("count")
    return [
        EffectOperation(
            op="deal_damage",
            params={
                "target": "opponent_bench",
                "amount": int(match.group("damage")),
                "count": int(count_raw) if count_raw else 1,
            },
        )
    ]


def _draw_cards(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="draw_cards",
            params={"target": "self_player", "count": int(match.group("count"))},
        )
    ]


def _draw_one_card(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="draw_cards", params={"target": "self_player", "count": 1})]


def _draw_until_hand_size(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="draw_until_hand_size",
            params={"target": "self_player", "count": int(match.group("count"))},
        )
    ]


def _heal_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="heal_damage",
            params={"target": "self_active", "amount": int(match.group("amount"))},
        )
    ]


def _heal_any_self_pokemon(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="heal_damage",
            params={"target": "self_pokemon", "amount": int(match.group("amount"))},
        )
    ]


def _status_to_opponent(match: re.Match[str]) -> list[EffectOperation]:
    status = _STATUS_MAP[match.group("status").lower()]
    return [
        EffectOperation(
            op="apply_status",
            params={"target": "opponent_active", "status": status},
        )
    ]


def _status_to_self(match: re.Match[str]) -> list[EffectOperation]:
    status = _STATUS_MAP[match.group("status").lower()]
    return [EffectOperation(op="apply_status", params={"target": "self_active", "status": status})]


def _search_deck_to_hand_single(match: re.Match[str]) -> list[EffectOperation]:
    descriptor = normalize_card_text(match.group("descriptor"))
    return [
        EffectOperation(
            op="search_deck_to_hand",
            params={"count": 1, "descriptor": descriptor, "reveal": True},
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _search_deck_to_hand_multi(match: re.Match[str]) -> list[EffectOperation]:
    descriptor = normalize_card_text(match.group("descriptor"))
    return [
        EffectOperation(
            op="search_deck_to_hand",
            params={
                "count": int(match.group("count")),
                "descriptor": descriptor,
                "reveal": True,
                "allow_less": True,
            },
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _shuffle_deck(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="shuffle_deck", params={"target": "self_player"})]


def _switch_self_active(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="switch_active_with_bench", params={"target": "self_player"})]


def _switch_opponent_active(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="switch_active_with_bench", params={"target": "opponent_player"})]


def _search_deck_to_bench_multi(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="search_deck_to_bench",
            params={
                "count": int(match.group("count")),
                "descriptor": normalize_card_text(match.group("descriptor")),
                "allow_less": True,
            },
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _search_deck_to_bench_single(match: re.Match[str]) -> list[EffectOperation]:
    descriptor = normalize_card_text(match.group("descriptor"))
    return [
        EffectOperation(
            op="search_deck_to_bench",
            params={"count": 1, "descriptor": descriptor, "allow_less": False},
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _search_deck_pokemon_to_hand_single(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="search_deck_to_hand",
            params={"count": 1, "descriptor": "Pokémon", "reveal": True},
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _discard_energy_from_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="discard_energy",
            params={"target": "self_active", "count": _coerce_count(match.group("count"))},
        )
    ]


def _discard_energy_from_opponent(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_energy", params={"target": "opponent_active", "count": 1})]


def _attach_energy_from_hand(match: re.Match[str]) -> list[EffectOperation]:
    raw_count = match.group("count")
    count = int(raw_count) if raw_count else 1
    return [
        EffectOperation(
            op="attach_energy",
            params={
                "source": "hand",
                "target": "self_pokemon",
                "count": count,
                "descriptor": normalize_card_text(match.group("descriptor")),
            },
        )
    ]


def _attach_energy_from_discard(match: re.Match[str]) -> list[EffectOperation]:
    raw_count = match.group("count")
    count = int(raw_count) if raw_count else 1
    return [
        EffectOperation(
            op="attach_energy",
            params={
                "source": "discard",
                "target": "self_pokemon",
                "count": count,
                "descriptor": normalize_card_text(match.group("descriptor")),
            },
        )
    ]


def _choose_opponent_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="select_opponent_bench", params={"count": int(match.group("count"))})]


def _prevent_damage_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="modify_incoming_damage_next_turn",
            params={"target": "self_active", "amount": int(match.group("amount"))},
        )
    ]


def _prevent_damage_flat(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="modify_incoming_damage_next_turn",
            params={"target": "self_active", "amount": int(match.group("amount"))},
        )
    ]


def _prevent_all_damage_and_effects_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="script_hook",
            params={"hook_id": "prevent-all-damage-next-turn", "target": "self_active"},
        )
    ]


def _defending_cannot_retreat_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "opponent_active", "rule": "cannot_retreat_next_turn"},
        )
    ]


def _no_weakness_resistance(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="ignore_weakness_resistance", params={"target": "attack"})]


def _ignore_damage_effects_on_opponent_active(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="ignore_defending_effects", params={"target": "opponent_active"})]


def _ignore_resistance(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="ignore_resistance", params={"target": "attack"})]


def _ignore_weakness_resistance_and_effects(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="ignore_weakness_resistance", params={"target": "attack"}),
        EffectOperation(op="ignore_defending_effects", params={"target": "opponent_active"}),
    ]


def _cannot_attack_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "cannot_attack_next_turn"},
        )
    ]


def _defending_cannot_attack_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "opponent_active", "rule": "cannot_attack_next_turn"},
        )
    ]


def _discard_tools_from_opponent_active(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_tools", params={"target": "opponent_active", "count": -1})]


def _damage_per_self_counter(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_self_damage_counter",
            params={"target": "opponent_active", "amount_per_counter": int(match.group("damage"))},
        )
    ]


def _turn_damage_bonus_to_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={
                "target": "self_player",
                "rule": "attacks_bonus_damage_this_turn",
                "amount": int(match.group("amount")),
            },
        )
    ]


def _ability_once_per_turn_note(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={})]


def _item_lock_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "opponent_player", "rule": "cannot_play_item_cards_next_turn"},
        )
    ]


def _attack_does_nothing(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={})]


def _move_energy_to_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="move_energy",
            params={
                "source": "self_active",
                "target": "self_bench",
                "count": int(match.group("count")),
            },
        )
    ]


def _discard_random_opponent_hand(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_random_card", params={"target": "opponent_hand", "count": 1})]


def _discard_top_opponent_deck(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="mill_top_deck", params={"target": "opponent_deck", "count": 1})]


def _coin_damage_for_heads(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="flip_coins_for_damage",
            params={
                "coin_count": int(match.group("coins")),
                "damage_per_heads": int(match.group("damage")),
            },
        )
    ]


def _prevent_that_damage(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "prevent_that_damage"})]


def _flip_coin_only(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="flip_coin", params={"heads": [], "tails": []})]


def _parenthetical_noop(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={})]


def _evolve_from_hand_ability_note(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={"note": "ability_on_evolve_from_hand"})]


def _survive_with_remaining_hp(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={
                "target": "self_active",
                "rule": "survive_with_remaining_hp",
                "remaining_hp": int(match.group("hp")),
            },
        )
    ]


def _cannot_attack_unless_condition(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={
                "target": "self_active",
                "rule": "conditional_attack_gate",
                "minimum_count": int(match.group("count")),
                "condition": normalize_card_text(match.group("condition")),
            },
        )
    ]


def _discard_up_to_bench_energy(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="discard_energy",
            params={"target": "self_bench", "count": int(match.group("count")), "allow_less": True},
        )
    ]


def _damage_bonus_per_discarded_energy(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_discarded_energy",
            params={"target": "opponent_active", "amount_per_energy": int(match.group("amount"))},
        )
    ]


def _cannot_use_attack_if_go_second_first_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "cannot_use_attack_if_go_second_first_turn"},
        )
    ]


def _damage_per_benched_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_benched",
            params={"target": "opponent_active", "amount_per_bench": int(match.group("amount")), "scope": "self"},
        )
    ]


def _prevent_damage_from_basic_non_type(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={
                "target": "self_active",
                "rule": "prevent_damage_from_basic_non_type_next_turn",
                "excluded_type": match.group("type"),
            },
        )
    ]


def _attach_basic_energy_from_hand_to_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="attach_energy",
            params={
                "source": "hand",
                "target": "self_active",
                "count": 1,
                "descriptor": normalize_card_text(match.group("descriptor")),
            },
        )
    ]


def _damage_more_per_energy_on_both_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_attached_energy",
            params={"target": "both_active", "amount_per_energy": int(match.group("amount")), "kind": "bonus"},
        )
    ]


def _damage_more_per_prize_taken(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_prize_taken",
            params={"target": "opponent_active", "amount_per_prize": int(match.group("amount"))},
        )
    ]


def _attach_energy_from_discard_to_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="attach_energy",
            params={
                "source": "discard",
                "target": "self_bench",
                "count": int(match.group("count")),
                "descriptor": normalize_card_text(match.group("descriptor")),
                "allow_less": True,
            },
        )
    ]


def _damage_more_per_benched_both(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_benched",
            params={"target": "opponent_active", "amount_per_bench": int(match.group("amount")), "scope": "both"},
        )
    ]


def _opponent_reveals_hand(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="reveal_hand", params={"target": "opponent_player"})]


def _damage_more_per_energy_on_opponent_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_attached_energy",
            params={"target": "opponent_active", "amount_per_energy": int(match.group("amount")), "kind": "bonus"},
        )
    ]


def _attach_energy_from_deck_for_each_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="attach_energy_per_benched_pokemon",
            params={"source": "deck", "descriptor": normalize_card_text(match.group("descriptor"))},
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _damage_per_specific_energy_on_all_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_attached_energy",
            params={
                "target": "all_self_pokemon",
                "amount_per_energy": int(match.group("amount")),
                "kind": "base",
                "descriptor": match.group("type"),
            },
        )
    ]


def _discard_stadium_in_play(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_stadium", params={})]


def _set_weakness_override(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={
                "target": "opponent_board",
                "rule": "weakness_override",
                "from_type": match.group("from_type"),
                "to_type": match.group("to_type"),
            },
        )
    ]


def _evolve_from_deck(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="evolve_from_deck", params={"target": "self_active"}),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _damage_per_tool_on_all_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_tool_attached",
            params={"target": "opponent_active", "amount_per_tool": int(match.group("amount"))},
        )
    ]


def _discard_card_from_hand_cost(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_cards", params={"target": "self_hand", "count": 1})]


def _copy_benched_attack(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "copy-benched-attack"})]


def _choose_random_opponent_hand_card(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="choose_random_opponent_hand_card", params={})]


def _reveal_and_shuffle_selected_opponent_card(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="shuffle_selected_opponent_hand_card_into_deck", params={})]


def _choose_random_and_shuffle_into_deck(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="shuffle_random_opponent_hand_card_into_deck", params={})]


def _return_attached_energy_to_hand(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="return_attached_energy_to_hand", params={"target": "self_active", "count": 1})]


def _scoop_up_self(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="scoop_up_self", params={})]


def _tool_card_rule_setup(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "tool_card_pokemon_form", "hp": int(match.group("hp"))},
        )
    ]


def _tool_card_special_conditions_and_retreat(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "immune_special_conditions_and_cannot_retreat"},
        )
    ]


def _discard_tool_card_from_play_option(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "discard_from_play_option"})]


def _damage_per_energy_on_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_attached_energy",
            params={"target": "self_active", "amount_per_energy": int(match.group("amount")), "kind": "base"},
        )
    ]


def _pivot_and_move_any_energy(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "pivot-and-move-any-energy"})]


def _switch_it_with_active(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="switch_active_with_bench", params={"target": "self_player"})]


def _move_any_energy_from_other_to_self(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="move_energy", params={"source": "self_other", "target": "self_active", "count": -1})]


def _ignore_effects_damage_from_attacks_used(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="ignore_defending_effects", params={"target": "opponent_active"})]


def _festival_grounds_attack_twice(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "festival-grounds-attack-twice"})]


def _for_each_bench_attach_from_deck(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="attach_energy_per_benched_pokemon",
            params={"source": "deck", "descriptor": normalize_card_text(match.group("descriptor"))},
        )
    ]


def _future_attack_bonus(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={
                "target": "self_player",
                "rule": "future_pokemon_attack_bonus",
                "amount": int(match.group("amount")),
            },
        )
    ]


def _damage_to_opponent_pokemon_count(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="deal_damage",
            params={"target": "opponent_any_pokemon", "amount": int(match.group("damage")), "count": int(match.group("count"))},
        )
    ]


def _ignore_effects_on_those_pokemon(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="ignore_weakness_resistance_and_effects_on_targets", params={})]


def _damage_more_per_self_counter(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_self_damage_counter",
            params={"target": "opponent_active", "amount_per_counter": int(match.group("amount")), "kind": "bonus"},
        )
    ]


def _discard_any_amount_energy_from_self(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="discard_energy", params={"target": "self_pokemon", "count": -1})]


def _damage_base_per_discarded_energy(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_discarded_energy",
            params={"target": "opponent_active", "amount_per_energy": int(match.group("amount")), "kind": "base"},
        )
    ]


def _heal_equal_to_damage_dealt(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="heal_equal_last_damage_dealt", params={"target": "self_active"})]


def _attack_cost_reduction_per_prize(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "attack_cost_reduction_per_prize", "attack_name": normalize_card_text(match.group("attack"))},
        )
    ]


def _prevent_damage_from_basic(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "prevent_damage_from_basic_pokemon_next_turn"},
        )
    ]


def _search_pokemon_to_hand_multi(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="search_deck_to_hand",
            params={"count": int(match.group("count")), "descriptor": "Pokémon", "reveal": True, "allow_less": True},
        ),
        EffectOperation(op="shuffle_deck", params={"target": "self_player"}),
    ]


def _damage_per_opponent_damage_counter(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_target_damage_counter",
            params={"target": "opponent_active", "amount_per_counter": int(match.group("amount"))},
        )
    ]


def _flip_until_tails_damage_bonus(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="flip_until_tails_damage_bonus",
            params={"amount_per_heads": int(match.group("amount"))},
        )
    ]


def _discard_top_n_opponent_deck(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="mill_top_deck", params={"target": "opponent_deck", "count": int(match.group("count"))})]


def _then_discard_that_stadium(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_stadium", params={})]


def _prevent_effects_not_damage(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "prevent_attack_effects_only"})]


def _heal_each_self_pokemon(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="heal_damage", params={"target": "self_pokemon", "amount": int(match.group("amount"))})]


def _choose_opponent_active_attack(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="choose_attack", params={"target": "opponent_active", "count": 1})]


def _cannot_use_chosen_attack_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "opponent_active", "rule": "cannot_use_chosen_attack_next_turn"})]


def _once_if_ko_last_turn_draw(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="triggered_effect",
            params={
                "trigger": "once_if_ko_last_turn",
                "operations": [
                    {"op": "draw_cards", "params": {"target": "self_player", "count": int(match.group("count"))}}
                ],
            },
        )
    ]


def _limit_named_ability_per_turn(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_player", "rule": "limit_named_ability_per_turn", "count": int(match.group("count"))},
        )
    ]


def _place_damage_counters_opponent_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="place_damage_counters",
            params={"target": "opponent_bench", "count": int(match.group("count"))},
        )
    ]


def _attacking_pokemon_is_poisoned_on_damage(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "poison_attacker_when_damaged"})]


def _cannot_use_named_attack_until_leave_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "cannot_reuse_named_attack_until_leave_active", "attack_name": normalize_card_text(match.group("attack"))},
        )
    ]


def _retaliate_damage_counters_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "retaliate_damage_counters_next_turn", "count": int(match.group("count"))},
        )
    ]


def _conditional_bonus_and_discard_all_energy(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="conditional_effect",
            params={
                "condition": "opponent_active_is_evolution",
                "operations": [
                    {"op": "deal_damage", "params": {"target": "opponent_active", "amount": int(match.group("amount")), "kind": "bonus"}},
                    {"op": "discard_energy", "params": {"target": "self_active", "count": -1}},
                ],
            },
        )
    ]


def _shuffle_attached_energy_into_deck(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="shuffle_attached_energy_into_deck",
            params={"target": "self_active", "count": int(match.group("count"))},
        )
    ]


def _prevent_damage_from_ability_pokemon(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "prevent_damage_from_pokemon_with_ability"})]


def _choose_one_bullet_modes(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "choose-one-bullet-mode"})]


def _defending_attack_damage_reduction_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "opponent_active", "rule": "attacks_do_less_damage_next_turn", "amount": int(match.group("amount"))},
        )
    ]


def _then_shuffle_deck(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="shuffle_deck", params={"target": "self_player"})]


def _shuffle_hand_into_deck(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="shuffle_hand_into_deck", params={"target": "self_player"})]


def _then_draw_cards(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="draw_cards", params={"target": "self_player", "count": int(match.group("count"))})]


def _conditional_draw_by_prize_state(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="conditional_effect",
            params={
                "condition": normalize_card_text(match.group("condition")),
                "operations": [
                    {
                        "op": "draw_cards",
                        "params": {"target": "self_player", "count": int(match.group("count"))},
                    }
                ],
            },
        )
    ]


def _as_often_use_ability_note(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={"note": "as_often_use_ability"})]


def _move_basic_energy_between_self_pokemon(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="move_energy",
            params={"source": "self_pokemon", "target": "self_pokemon", "count": int(match.group("count"))},
        )
    ]


def _defending_attack_flip_tails_fails(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "defending-attack-flip-tails-fails"})]


def _once_if_active_may_use_ability(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={"note": "once_if_active_may_use_ability"})]


def _card_use_gate_by_opponent_prizes(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_player", "rule": "card_use_gate_by_opponent_prizes", "max_prizes": int(match.group("count"))},
        )
    ]


def _choose_self_pokemon_in_play(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="choose_self_pokemon", params={"count": 1})]


def _prevent_all_damage_effects_to_that_from_ex(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "chosen_self_pokemon", "rule": "prevent_all_damage_effects_from_ex_next_turn"},
        )
    ]


def _recover_pokemon_or_basic_energy_from_discard(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="recover_from_discard_to_hand", params={"count": 1, "descriptor": "pokemon_or_basic_energy"})]


def _status_asleep_and_poisoned(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Asleep"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Poisoned"}),
    ]


def _no_retreat_cost_if_no_energy(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "no_retreat_cost_if_no_energy"},
        )
    ]


def _discard_any_amount_energy_among_self(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_energy", params={"target": "self_pokemon", "count": -1})]


def _discard_any_amount_energy_and_damage(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(op="discard_energy", params={"target": "self_pokemon", "count": -1}),
        EffectOperation(
            op="damage_per_discarded_energy",
            params={"target": "opponent_active", "amount_per_energy": int(match.group("amount")), "kind": "base"},
        ),
    ]


def _damage_for_each_self_pokemon_in_play(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_pokemon_in_play",
            params={"target": "opponent_active", "amount_per_pokemon": int(match.group("amount")), "scope": "self"},
        )
    ]


def _damage_more_per_energy_on_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_attached_energy",
            params={"target": "self_active", "amount_per_energy": int(match.group("amount")), "kind": "bonus"},
        )
    ]


def _damage_base_per_prize_taken(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_prize_taken",
            params={"target": "opponent_active", "amount_per_prize": int(match.group("amount")), "kind": "base"},
        )
    ]


def _as_long_as_attached_provides_colorless(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "attached_pokemon", "rule": "provides_colorless_energy"})]


def _opponent_discards_cards_from_hand(match: re.Match[str]) -> list[EffectOperation]:
    count = int(match.groupdict().get("count") or "1")
    return [EffectOperation(op="discard_cards", params={"target": "opponent_hand", "count": count})]


def _discard_special_energy_from_opponent_active(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_energy", params={"target": "opponent_active", "count": 1, "descriptor": "Special"})]


def _move_energy_opponent_active_to_bench(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="move_energy", params={"source": "opponent_active", "target": "opponent_bench", "count": 1})]


def _damage_more_per_opponent_benched(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_benched",
            params={"target": "opponent_active", "amount_per_bench": int(match.group("amount")), "scope": "opponent"},
        )
    ]


def _status_burned_and_confused(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Burned"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Confused"}),
    ]


def _status_confused_and_poisoned(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Confused"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Poisoned"}),
    ]


def _status_burned_and_poisoned(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Burned"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Poisoned"}),
    ]


def _status_paralyzed_and_poisoned(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Paralyzed"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Poisoned"}),
    ]


def _status_burned_confused_and_poisoned(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Burned"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Confused"}),
        EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Poisoned"}),
    ]


def _recover_supporter_from_discard(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="recover_from_discard_to_hand", params={"count": 1, "descriptor": "supporter"})]


def _damage_base_per_energy_on_opponent_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_attached_energy",
            params={"target": "opponent_active", "amount_per_energy": int(match.group("amount")), "kind": "base"},
        )
    ]


def _damage_more_per_opponent_damage_counter(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_target_damage_counter",
            params={"amount_per_counter": int(match.group("amount"))},
        )
    ]


def _damage_more_per_self_benched(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_benched",
            params={"target": "opponent_active", "amount_per_bench": int(match.group("amount")), "scope": "self"},
        )
    ]


def _put_up_to_cards_from_discard_to_hand(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="recover_from_discard_to_hand", params={"count": int(match.group("count")), "allow_less": True})]


def _all_self_basic_no_retreat(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_player", "rule": "all_self_basic_no_retreat"})]


def _during_next_turn_cannot_retreat(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "cannot_retreat_next_turn"})]


def _move_energy_from_self_active_to_self_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="move_energy",
            params={"source": "self_active", "target": "self_bench", "count": int(match.group("count"))},
        )
    ]


def _search_any_cards_to_hand(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="search_deck_to_hand", params={"count": int(match.group("count")), "descriptor": "any", "allow_less": True})]


def _place_damage_counters_on_opponent_any(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="deal_damage",
            params={"target": "opponent_any_pokemon", "amount": int(match.group("count")) * 10, "kind": "effect"},
        )
    ]


def _choose_up_to_self_typed_pokemon(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="choose_self_pokemon", params={"count": int(match.group("count")), "allow_less": True})]


def _card_use_gate_opponent_exact_prizes(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_player", "rule": "card_use_gate_opponent_exact_prizes", "count": int(match.group("count"))},
        )
    ]


def _card_use_gate_discard_n_other_cards(match: re.Match[str]) -> list[EffectOperation]:
    count = int(match.group("count"))
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_player", "rule": "card_use_gate_discard_n_other_cards", "count": count},
        ),
        EffectOperation(op="discard_cards", params={"target": "self_hand", "count": count}),
    ]


def _discard_up_to_energy_and_damage_per_discarded(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(op="discard_energy", params={"target": "self_active", "count": int(match.group("count")), "allow_less": True}),
        EffectOperation(
            op="damage_per_discarded_energy",
            params={"target": "opponent_active", "amount_per_energy": int(match.group("amount")), "kind": "base"},
        ),
    ]


def _damage_per_team_rocket_in_play(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_pokemon_in_play",
            params={"target": "opponent_active", "amount_per_pokemon": int(match.group("amount")), "scope": "self", "filter": "team_rocket"},
        )
    ]


def _discard_energy_and_damage_to_opponent_any(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(op="discard_energy", params={"target": "self_active", "count": int(match.group("count"))}),
        EffectOperation(op="deal_damage", params={"target": "opponent_any_pokemon", "amount": int(match.group("amount"))}),
    ]


def _discard_up_to_typed_energy(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="discard_energy", params={"target": "self_active", "count": int(match.group("count")), "allow_less": True})]


def _discard_all_energy_and_damage_bench(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(op="discard_energy", params={"target": "self_active", "count": -1}),
        EffectOperation(op="deal_damage", params={"target": "opponent_bench", "amount": int(match.group("amount"))}),
    ]


def _flip_n_coins_only(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="flip_coins", params={"count": int(match.group("count"))})]


def _put_other_card_on_bottom(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="put_card_on_bottom_of_deck", params={"count": 1})]


def _if_go_first_may_use_card_first_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_player", "rule": "may_use_card_if_go_first"})]


def _limit_named_ability_during_turn(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_player", "rule": "limit_named_ability_per_turn", "count": int(match.group("count"))},
        )
    ]


def _festival_grounds_attack_twice_first_clause(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "festival-grounds-attack-twice"})]


def _if_first_attack_ko_attack_again(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "attack-again-after-first-ko"})]


def _flip_until_tails(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={"note": "flip_until_tails_context"})]


def _damage_bonus_per_heads_after_until_tails(match: re.Match[str]) -> list[EffectOperation]:
    return [EffectOperation(op="flip_until_tails_damage_bonus", params={"amount_per_heads": int(match.group("amount"))})]


def _prevent_effects_not_damage_single(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "prevent_attack_effects_only"})]


def _turn_damage_bonus_to_active_ex_v(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_player", "rule": "attacks_bonus_damage_to_ex_v_this_turn", "amount": int(match.group("amount"))},
        )
    ]


def _switch_benched_with_active_generic(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="switch_active_with_bench", params={"target": "self_player"})]


def _if_you_do_new_active_poisoned(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="conditional_effect",
            params={
                "condition": "if_you_did_switch",
                "operations": [{"op": "apply_status", "params": {"target": "self_active", "status": "Poisoned"}}],
            },
        )
    ]


def _opponent_flips_coin_when_defending_attacks(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "opponent-flips-coin-when-defending-attacks"})]


def _if_tails_attack_doesnt_happen(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="conditional_effect", params={"condition": "coin_result_is_tails", "operations": []})]


def _prize_take_reduction_when_dark_koed_by_ex(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "opponent_player", "rule": "take_fewer_prize_on_dark_ko", "count": int(match.group("count"))},
        )
    ]


def _effect_doesnt_stack_note(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="annotation_noop", params={"note": "effect_does_not_stack"})]


def _damage_per_self_pokemon_with_round(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="damage_per_pokemon_in_play",
            params={"target": "opponent_active", "amount_per_pokemon": int(match.group("amount")), "scope": "self", "filter": "has_round_attack"},
        )
    ]


def _can_use_attack_if_go_first(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "can_use_attack_if_go_first"})]


def _discard_basic_energy_cost_for_ability(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="discard_energy", params={"target": "self_active", "count": 1})]


def _copy_opponent_active_attack(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "copy-opponent-active-attack"})]


def _once_if_dark_energy_move_damage_counters(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="script_hook", params={"hook_id": "once-dark-energy-move-damage-counters"})]


def _once_look_top_pick_one(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="look_top_deck_pick",
            params={"look_count": int(match.group("look")), "pick_count": int(match.group("pick"))},
        )
    ]


def _once_first_turn_search_limited_hp(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="script_hook",
            params={"hook_id": "once-first-turn-search-limited-hp", "count": int(match.group("count")), "hp_limit": int(match.group("hp"))},
        )
    ]


def _attack_cost_reduction_if_more_prizes(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_active", "rule": "attack_cost_reduction_if_more_prizes"})]


def _card_use_gate_if_have_tera(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="apply_temporary_rule", params={"target": "self_player", "rule": "card_use_gate_if_have_tera"})]


def _attach_basic_energy_discard_to_benched_count(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="attach_energy",
            params={"source": "discard", "target": "self_bench", "count": int(match.group("count")), "descriptor": "Basic", "allow_less": True},
        )
    ]


def _card_use_gate_discard_another_card(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(op="apply_temporary_rule", params={"target": "self_player", "rule": "card_use_gate_discard_another_card"}),
        EffectOperation(op="discard_cards", params={"target": "self_hand", "count": 1}),
    ]


def _conditional_draw_until_if_all_team_rocket(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="conditional_effect",
            params={
                "condition": "all_team_rocket_in_play",
                "operations": [{"op": "draw_until_hand_size", "params": {"target": "self_player", "count": int(match.group("count"))}}],
            },
        )
    ]


CLAUSE_TEMPLATES: list[TextTemplate] = [
    TextTemplate(
        name="damage_bonus_active",
        description="Deal conditional bonus damage to the opponent's Active Pokémon.",
        pattern=re.compile(
            r"^This attack does (?P<damage>\d+) more damage\.$",
            re.IGNORECASE,
        ),
        builder=_bonus_damage_to_active,
    ),
    TextTemplate(
        name="damage_active",
        description="Deal fixed damage to the opponent's Active Pokémon.",
        pattern=re.compile(
            rf"^(?:This attack does )?(?P<damage>\d+) damage(?: to your opponent's Active {_POKEMON_TOKEN})?\.$",
            re.IGNORECASE,
        ),
        builder=_damage_to_active,
    ),
    TextTemplate(
        name="damage_self_also",
        description="Deal fixed recoil damage to this Pokémon.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} also does (?P<damage>\d+) damage to itself\.$",
            re.IGNORECASE,
        ),
        builder=_damage_to_self_also,
    ),
    TextTemplate(
        name="damage_self",
        description="Deal fixed damage to your own Active Pokémon.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} does (?P<damage>\d+) damage to itself\.$",
            re.IGNORECASE,
        ),
        builder=_damage_to_self,
    ),
    TextTemplate(
        name="damage_bench",
        description="Deal fixed damage to one or more Benched Pokémon.",
        pattern=re.compile(
            rf"^This attack (?:also )?does (?P<damage>\d+) damage to (?:(?P<count>\d+) of your opponent's Benched {_POKEMON_TOKEN}|1 of your opponent's Benched {_POKEMON_TOKEN}|that {_POKEMON_TOKEN})\.$",
            re.IGNORECASE,
        ),
        builder=_damage_to_bench,
    ),
    TextTemplate(
        name="draw_cards",
        description="Draw a fixed number of cards.",
        pattern=re.compile(r"^Draw (?P<count>\d+) cards?\.$", re.IGNORECASE),
        builder=_draw_cards,
    ),
    TextTemplate(
        name="draw_one_card",
        description="Draw one card.",
        pattern=re.compile(r"^Draw (?:a|an) card\.$", re.IGNORECASE),
        builder=_draw_one_card,
    ),
    TextTemplate(
        name="draw_until_hand_size",
        description="Draw cards until a target hand size.",
        pattern=re.compile(
            r"^Draw cards until you have (?P<count>\d+) cards in your hand\.$",
            re.IGNORECASE,
        ),
        builder=_draw_until_hand_size,
    ),
    TextTemplate(
        name="heal_self",
        description="Heal your own Active Pokémon.",
        pattern=re.compile(rf"^Heal (?P<amount>\d+) damage from this {_POKEMON_TOKEN}\.$", re.IGNORECASE),
        builder=_heal_self,
    ),
    TextTemplate(
        name="heal_self_any",
        description="Heal one of your Pokémon.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from 1 of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_heal_any_self_pokemon,
    ),
    TextTemplate(
        name="status_opponent",
        description="Apply a status condition to opponent's Active Pokémon.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now (?P<status>Poisoned|Burned|Paralyzed|Asleep|Confused)\.$",
            re.IGNORECASE,
        ),
        builder=_status_to_opponent,
    ),
    TextTemplate(
        name="status_self",
        description="Apply a status condition to your own Active Pokémon.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} is now (?P<status>Poisoned|Burned|Paralyzed|Asleep|Confused)\.$",
            re.IGNORECASE,
        ),
        builder=_status_to_self,
    ),
    TextTemplate(
        name="search_deck_to_hand_single",
        description="Search deck for one matching card and add to hand.",
        pattern=re.compile(
            r"^Search your deck for (?:a|an) (?P<descriptor>.+?) card, reveal it, and put it into your hand\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_search_deck_to_hand_single,
    ),
    TextTemplate(
        name="search_deck_to_hand_multi",
        description="Search deck for up to N matching cards and add to hand.",
        pattern=re.compile(
            r"^Search your deck for up to (?P<count>\d+) (?P<descriptor>.+?) cards, reveal them, and put them into your hand\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_search_deck_to_hand_multi,
    ),
    TextTemplate(
        name="search_deck_to_bench_multi",
        description="Search deck for up to N cards and put them onto your Bench.",
        pattern=re.compile(
            rf"^Search your deck for up to (?P<count>\d+) (?P<descriptor>.+?) and put them onto your Bench\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_search_deck_to_bench_multi,
    ),
    TextTemplate(
        name="search_deck_to_bench_single",
        description="Search deck for one card and put it onto your Bench.",
        pattern=re.compile(
            rf"^Search your deck for (?:a|an) (?P<descriptor>.+?) and put it onto your Bench\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_search_deck_to_bench_single,
    ),
    TextTemplate(
        name="search_deck_pokemon_to_hand_single",
        description="Search deck for a Pokémon and put it into your hand.",
        pattern=re.compile(
            rf"^Search your deck for a {_POKEMON_TOKEN}, reveal it, and put it into your hand\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_search_deck_pokemon_to_hand_single,
    ),
    TextTemplate(
        name="shuffle_deck",
        description="Shuffle your deck.",
        pattern=re.compile(r"^Shuffle your deck\.$", re.IGNORECASE),
        builder=_shuffle_deck,
    ),
    TextTemplate(
        name="switch_self_active",
        description="Switch your Active Pokémon with one of your Benched Pokémon.",
        pattern=re.compile(
            rf"^Switch (?:your Active(?: .+?)? {_POKEMON_TOKEN}|this {_POKEMON_TOKEN}) with 1 of your Benched(?: .+?)? {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_switch_self_active,
    ),
    TextTemplate(
        name="switch_opponent_active_out",
        description="Switch out your opponent's Active Pokémon to the Bench.",
        pattern=re.compile(
            rf"^Switch out your opponent's Active {_POKEMON_TOKEN} to the Bench\.$",
            re.IGNORECASE,
        ),
        builder=_switch_opponent_active,
    ),
    TextTemplate(
        name="switch_in_opponent_bench",
        description="Switch in one of your opponent's Benched Pokémon to Active Spot.",
        pattern=re.compile(
            rf"^Switch in 1 of your opponent's Benched {_POKEMON_TOKEN} to the Active Spot\.$",
            re.IGNORECASE,
        ),
        builder=_switch_opponent_active,
    ),
    TextTemplate(
        name="switch_opponent_active",
        description="Force opponent to switch Active Pokémon.",
        pattern=re.compile(
            rf"^Your opponent switches their Active {_POKEMON_TOKEN} with 1 of their Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_switch_opponent_active,
    ),
    TextTemplate(
        name="discard_energy_self",
        description="Discard energy from this Pokémon.",
        pattern=re.compile(
            rf"^Discard (?P<count>a|an|all|\d+) Energy from this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_energy_from_self,
    ),
    TextTemplate(
        name="discard_energy_opponent_active",
        description="Discard one Energy from opponent Active Pokémon.",
        pattern=re.compile(
            rf"^Discard an Energy from your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_energy_from_opponent,
    ),
    TextTemplate(
        name="attach_energy_from_hand",
        description="Attach energy card(s) from hand to your Pokémon.",
        pattern=re.compile(
            rf"^Attach (?:up to (?P<count>\d+) |a |an )(?P<descriptor>.+?) Energy cards? from your hand to (?:1 of your (?:.+? ){_POKEMON_TOKEN}|this {_POKEMON_TOKEN})\.$",
            re.IGNORECASE,
        ),
        builder=_attach_energy_from_hand,
    ),
    TextTemplate(
        name="attach_energy_from_discard",
        description="Attach energy card(s) from discard to your Pokémon.",
        pattern=re.compile(
            rf"^Attach (?:up to (?P<count>\d+) |a |an )(?P<descriptor>.+?) Energy card from your discard pile to (?:1 of your (?:.+? ){_POKEMON_TOKEN}|your Benched (?:.+? ){_POKEMON_TOKEN}|this {_POKEMON_TOKEN})\.$",
            re.IGNORECASE,
        ),
        builder=_attach_energy_from_discard,
    ),
    TextTemplate(
        name="choose_opponent_bench",
        description="Choose opponent Benched Pokémon target(s).",
        pattern=re.compile(
            rf"^Choose (?P<count>\d+) of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_choose_opponent_bench,
    ),
    TextTemplate(
        name="prevent_damage_next_turn",
        description="Apply next-turn incoming damage reduction.",
        pattern=re.compile(
            rf"^During your opponent's next turn, this {_POKEMON_TOKEN} takes (?P<amount>\d+) less damage from attacks(?: \(after applying Weakness and Resistance\))?\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_damage_next_turn,
    ),
    TextTemplate(
        name="prevent_damage_flat",
        description="Apply damage reduction without explicit next-turn timing sentence.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} takes (?P<amount>\d+) less damage from attacks \(after applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_damage_flat,
    ),
    TextTemplate(
        name="prevent_all_damage_and_effects_next_turn",
        description="Prevent all damage and attack effects next opponent turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, prevent all damage from and effects of attacks done to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_all_damage_and_effects_next_turn,
    ),
    TextTemplate(
        name="defending_cannot_retreat_next_turn",
        description="Defending or affected Pokémon cannot retreat next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, (?:the Defending {_POKEMON_TOKEN}|that {_POKEMON_TOKEN}) can't retreat\.$",
            re.IGNORECASE,
        ),
        builder=_defending_cannot_retreat_next_turn,
    ),
    TextTemplate(
        name="ignore_weakness_resistance",
        description="Ignore Weakness and Resistance for this attack.",
        pattern=re.compile(
            r"^This attack's damage isn't affected by Weakness or Resistance\.$",
            re.IGNORECASE,
        ),
        builder=_no_weakness_resistance,
    ),
    TextTemplate(
        name="ignore_opponent_active_effects",
        description="Ignore effects on opponent Active Pokémon for this attack.",
        pattern=re.compile(
            rf"^This attack's damage isn't affected by any effects on your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_ignore_damage_effects_on_opponent_active,
    ),
    TextTemplate(
        name="ignore_weakness_resistance_and_effects",
        description="Ignore Weakness, Resistance, and effects on opponent Active.",
        pattern=re.compile(
            rf"^This attack's damage isn't affected by Weakness or Resistance, or by any effects on your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_ignore_weakness_resistance_and_effects,
    ),
    TextTemplate(
        name="ignore_resistance_only",
        description="Ignore Resistance for this attack.",
        pattern=re.compile(
            r"^This attack's damage isn't affected by Resistance\.$",
            re.IGNORECASE,
        ),
        builder=_ignore_resistance,
    ),
    TextTemplate(
        name="cannot_attack_next_turn",
        description="This Pokémon cannot attack during your next turn.",
        pattern=re.compile(
            rf"^During your next turn, this {_POKEMON_TOKEN} can't (?:attack|use attacks|use .+)\.$",
            re.IGNORECASE,
        ),
        builder=_cannot_attack_next_turn,
    ),
    TextTemplate(
        name="defending_cannot_attack_next_turn",
        description="Defending Pokémon cannot use attacks next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, the Defending {_POKEMON_TOKEN} can't (?:use attacks|attack)\.$",
            re.IGNORECASE,
        ),
        builder=_defending_cannot_attack_next_turn,
    ),
    TextTemplate(
        name="discard_tools_from_opponent_active",
        description="Discard all Pokémon Tools from opponent Active Pokémon.",
        pattern=re.compile(
            rf"^Before doing damage, discard all {_POKEMON_TOKEN} Tools from your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_tools_from_opponent_active,
    ),
    TextTemplate(
        name="damage_per_self_counter",
        description="Deal damage for each damage counter on this Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<damage>\d+) damage for each damage counter on this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_self_counter,
    ),
    TextTemplate(
        name="turn_damage_bonus_to_active",
        description="Apply a temporary damage bonus for this turn's attacks.",
        pattern=re.compile(
            rf"^During this turn, attacks used by your {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} ex \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_turn_damage_bonus_to_active,
    ),
    TextTemplate(
        name="ability_once_per_turn_note",
        description="Ability reminder text for once during your turn.",
        pattern=re.compile(
            r"^Once during your turn, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_ability_once_per_turn_note,
    ),
    TextTemplate(
        name="item_lock_next_turn",
        description="Opponent cannot play Item cards during next turn.",
        pattern=re.compile(
            r"^During your opponent's next turn, they can't play any Item cards from their hand\.$",
            re.IGNORECASE,
        ),
        builder=_item_lock_next_turn,
    ),
    TextTemplate(
        name="prevent_that_damage",
        description="Prevent that damage on a conditional branch.",
        pattern=re.compile(
            r"^Prevent that damage\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_that_damage,
    ),
    TextTemplate(
        name="attack_does_nothing",
        description="Attack branch that has no direct effect.",
        pattern=re.compile(r"^This attack does nothing\.$", re.IGNORECASE),
        builder=_attack_does_nothing,
    ),
    TextTemplate(
        name="move_energy_to_bench",
        description="Move Energy from this Pokémon to your Benched Pokémon.",
        pattern=re.compile(
            rf"^Move an Energy from this {_POKEMON_TOKEN} to (?P<count>\d+) of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_move_energy_to_bench,
    ),
    TextTemplate(
        name="discard_random_opponent_hand",
        description="Discard a random card from your opponent's hand.",
        pattern=re.compile(
            r"^Discard a random card from your opponent's hand\.$",
            re.IGNORECASE,
        ),
        builder=_discard_random_opponent_hand,
    ),
    TextTemplate(
        name="discard_top_opponent_deck",
        description="Discard the top card from your opponent's deck.",
        pattern=re.compile(
            r"^Discard the top card of your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_discard_top_opponent_deck,
    ),
    TextTemplate(
        name="flip_coins_for_damage",
        description="Flip N coins and do damage for each heads.",
        pattern=re.compile(
            r"^Flip (?P<coins>\d+) coins\. This attack does (?P<damage>\d+) damage for each heads\.$",
            re.IGNORECASE,
        ),
        builder=_coin_damage_for_heads,
    ),
    TextTemplate(
        name="flip_n_coins_only",
        description="Flip a fixed number of coins.",
        pattern=re.compile(r"^Flip (?P<count>\d+) coins\.$", re.IGNORECASE),
        builder=_flip_n_coins_only,
    ),
    TextTemplate(
        name="flip_coin_only",
        description="Flip a coin with no immediate branch clause.",
        pattern=re.compile(r"^Flip a coin\.$", re.IGNORECASE),
        builder=_flip_coin_only,
    ),
    TextTemplate(
        name="parenthetical_noop",
        description="Parenthetical reminder text with no state change in demo runtime.",
        pattern=re.compile(
            rf"^\((?:Your opponent chooses the new Active {_POKEMON_TOKEN}|Don't apply Weakness and Resistance for Benched {_POKEMON_TOKEN}|Apply Weakness as [×x]2|Damage is not an effect|Discard all cards attached to this {_POKEMON_TOKEN}|{_POKEMON_TOKEN} ex, {_POKEMON_TOKEN} V, etc\. have Rule Boxes|This includes newly .+?|If you can't draw any cards in this way, you can't use this card|You still need the necessary Energy to use each attack|The Energy can be of any type)\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="evolve_from_hand_ability_note",
        description="Ability trigger note when evolving from hand.",
        pattern=re.compile(
            rf"^Once during your turn, when you play this {_POKEMON_TOKEN} from your hand to evolve \d+ of your {_POKEMON_TOKEN}, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_evolve_from_hand_ability_note,
    ),
    TextTemplate(
        name="survive_with_remaining_hp",
        description="Prevents knockout and sets a remaining HP floor.",
        pattern=re.compile(
            rf"^If this {_POKEMON_TOKEN} has full HP and would be Knocked Out by damage from an attack, it is not Knocked Out, and its remaining HP becomes (?P<hp>\d+)\.$",
            re.IGNORECASE,
        ),
        builder=_survive_with_remaining_hp,
    ),
    TextTemplate(
        name="cannot_attack_unless_condition",
        description="Attack gate requiring a minimum in-play condition.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} can't attack unless you have (?P<count>\d+) or more (?P<condition>.+?) in play\.$",
            re.IGNORECASE,
        ),
        builder=_cannot_attack_unless_condition,
    ),
    TextTemplate(
        name="discard_up_to_bench_energy",
        description="Discard up to N Energy from Benched Pokémon.",
        pattern=re.compile(
            rf"^You may discard up to (?P<count>\d+) Energy from your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_up_to_bench_energy,
    ),
    TextTemplate(
        name="damage_bonus_per_discarded_energy",
        description="Damage bonus per card discarded this way.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) more damage for each card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_damage_bonus_per_discarded_energy,
    ),
    TextTemplate(
        name="cannot_use_attack_if_go_second_first_turn",
        description="If you go second, cannot use this attack during first turn.",
        pattern=re.compile(
            r"^If you go second, you can't use this attack during your first turn\.$",
            re.IGNORECASE,
        ),
        builder=_cannot_use_attack_if_go_second_first_turn,
    ),
    TextTemplate(
        name="damage_per_benched_self",
        description="Damage per your own Benched Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_benched_self,
    ),
    TextTemplate(
        name="prevent_damage_from_basic_non_type",
        description="Prevent damage from Basic non-type Pokémon next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, prevent all damage done to this {_POKEMON_TOKEN} by attacks from Basic non-\{{(?P<type>[A-Z])\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_damage_from_basic_non_type,
    ),
    TextTemplate(
        name="attach_basic_energy_from_hand_to_self",
        description="Attach a typed Energy from hand to this Pokémon.",
        pattern=re.compile(
            rf"^Attach a (?P<descriptor>.+?) Energy card from your hand to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_attach_basic_energy_from_hand_to_self,
    ),
    TextTemplate(
        name="damage_more_per_energy_on_both_active",
        description="Damage bonus per Energy attached to both Active Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each Energy attached to both Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_energy_on_both_active,
    ),
    TextTemplate(
        name="damage_more_per_prize_taken",
        description="Damage bonus per Prize card opponent has taken.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) more damage for each Prize card your opponent has taken\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_prize_taken,
    ),
    TextTemplate(
        name="attach_energy_from_discard_to_bench",
        description="Attach up to N Energy cards from discard to Benched Pokémon.",
        pattern=re.compile(
            rf"^Attach up to (?P<count>\d+) (?P<descriptor>.+?) Energy cards from your discard pile to your Benched {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_attach_energy_from_discard_to_bench,
    ),
    TextTemplate(
        name="damage_more_per_benched_both",
        description="Damage bonus per Benched Pokémon on both sides.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each Benched {_POKEMON_TOKEN} \(both yours and your opponent's\)\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_benched_both,
    ),
    TextTemplate(
        name="opponent_reveals_hand",
        description="Opponent reveals their hand.",
        pattern=re.compile(r"^Your opponent reveals their hand\.$", re.IGNORECASE),
        builder=_opponent_reveals_hand,
    ),
    TextTemplate(
        name="damage_more_per_energy_on_opponent_active",
        description="Damage bonus per Energy on opponent Active Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each Energy attached to your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_energy_on_opponent_active,
    ),
    TextTemplate(
        name="attach_energy_from_deck_for_each_bench",
        description="Attach Energy from deck for each Benched Pokémon.",
        pattern=re.compile(
            rf"^For each of your Benched {_POKEMON_TOKEN}, search your deck for a (?P<descriptor>.+?) Energy card and attach it to that {_POKEMON_TOKEN}\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_attach_energy_from_deck_for_each_bench,
    ),
    TextTemplate(
        name="damage_per_specific_energy_on_all_self",
        description="Damage per specific Energy attached to all your Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each \{{(?P<type>[A-Z])\}} Energy attached to all of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_specific_energy_on_all_self,
    ),
    TextTemplate(
        name="discard_stadium_in_play",
        description="Discard a Stadium in play.",
        pattern=re.compile(r"^Discard a Stadium in play\.$", re.IGNORECASE),
        builder=_discard_stadium_in_play,
    ),
    TextTemplate(
        name="set_weakness_override",
        description="Change weakness type of opponent Pokémon in play.",
        pattern=re.compile(
            rf"^The Weakness of each of your opponent's \{{(?P<from_type>[A-Z])\}} {_POKEMON_TOKEN} in play is now \{{(?P<to_type>[A-Z])\}}\.$",
            re.IGNORECASE,
        ),
        builder=_set_weakness_override,
    ),
    TextTemplate(
        name="evolve_from_deck",
        description="Search and evolve this Pokémon from deck.",
        pattern=re.compile(
            rf"^Search your deck for a card that evolves from this {_POKEMON_TOKEN} and put it onto this {_POKEMON_TOKEN} to evolve it\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_evolve_from_deck,
    ),
    TextTemplate(
        name="damage_per_tool_on_all_self",
        description="Damage per Pokémon Tool attached to all your Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each {_POKEMON_TOKEN} Tool attached to all of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_tool_on_all_self,
    ),
    TextTemplate(
        name="discard_card_from_hand_cost",
        description="Cost clause: discard a card from your hand.",
        pattern=re.compile(
            r"^You must discard a card from your hand in order to use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_discard_card_from_hand_cost,
    ),
    TextTemplate(
        name="copy_benched_attack",
        description="Use one attack from a Benched Pokémon as this attack.",
        pattern=re.compile(
            rf"^Choose 1 of your Benched .+? {_POKEMON_TOKEN}'s attacks and use it as this attack\.$",
            re.IGNORECASE,
        ),
        builder=_copy_benched_attack,
    ),
    TextTemplate(
        name="choose_random_opponent_hand_card",
        description="Choose a random card from opponent hand.",
        pattern=re.compile(
            r"^Choose a random card from your opponent's hand\.$",
            re.IGNORECASE,
        ),
        builder=_choose_random_opponent_hand_card,
    ),
    TextTemplate(
        name="reveal_and_shuffle_selected_opponent_card",
        description="Reveal selected random card and shuffle it into opponent deck.",
        pattern=re.compile(
            r"^Your opponent reveals that card and shuffles it into their deck\.$",
            re.IGNORECASE,
        ),
        builder=_reveal_and_shuffle_selected_opponent_card,
    ),
    TextTemplate(
        name="choose_random_and_shuffle_into_deck",
        description="Choose random opponent hand card and shuffle it into deck.",
        pattern=re.compile(
            r"^Choose a random card from your opponent's hand\. Your opponent reveals that card and shuffles it into their deck\.$",
            re.IGNORECASE,
        ),
        builder=_choose_random_and_shuffle_into_deck,
    ),
    TextTemplate(
        name="return_attached_energy_to_hand",
        description="Return an attached Energy from this Pokémon to your hand.",
        pattern=re.compile(
            rf"^Put an Energy attached to this {_POKEMON_TOKEN} into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_return_attached_energy_to_hand,
    ),
    TextTemplate(
        name="scoop_up_self",
        description="Put this Pokémon and all attached cards into your hand.",
        pattern=re.compile(
            rf"^Put this {_POKEMON_TOKEN} and all attached cards into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_scoop_up_self,
    ),
    TextTemplate(
        name="tool_card_rule_setup",
        description="Play this card as a Basic Pokémon with set HP.",
        pattern=re.compile(
            rf"^Play this card as if it were a (?P<hp>\d+)-HP Basic \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_tool_card_rule_setup,
    ),
    TextTemplate(
        name="tool_card_special_conditions_and_retreat",
        description="Card cannot be affected by Special Conditions and cannot retreat.",
        pattern=re.compile(
            r"^This card can't be affected by any Special Conditions and can't retreat\.$",
            re.IGNORECASE,
        ),
        builder=_tool_card_special_conditions_and_retreat,
    ),
    TextTemplate(
        name="discard_tool_card_from_play_option",
        description="May discard this card from play anytime during your turn.",
        pattern=re.compile(
            r"^At any time during your turn, you may discard this card from play\.$",
            re.IGNORECASE,
        ),
        builder=_discard_tool_card_from_play_option,
    ),
    TextTemplate(
        name="damage_per_energy_on_self",
        description="Damage per Energy attached to this Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each Energy attached to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_energy_on_self,
    ),
    TextTemplate(
        name="pivot_and_move_any_energy",
        description="Bench-trigger pivot and move any amount of energy.",
        pattern=re.compile(
            rf"^When you play this {_POKEMON_TOKEN} from your hand onto your Bench during your turn, you may switch it with your Active {_POKEMON_TOKEN}\. If you do, you may move any amount of Energy from your other {_POKEMON_TOKEN} to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_pivot_and_move_any_energy,
    ),
    TextTemplate(
        name="switch_it_with_active",
        description="Switch this Pokémon with your Active Pokémon in trigger text.",
        pattern=re.compile(
            rf"^Switch it with your Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_switch_it_with_active,
    ),
    TextTemplate(
        name="move_any_energy_from_other_to_self",
        description="Move any amount of Energy from your other Pokémon to this Pokémon.",
        pattern=re.compile(
            rf"^(?:If you do, )?you may move any amount of Energy from your other {_POKEMON_TOKEN} to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_move_any_energy_from_other_to_self,
    ),
    TextTemplate(
        name="ignore_effects_damage_from_attacks_used",
        description="Damage from attacks used by this Pokémon ignores effects on opponent Active.",
        pattern=re.compile(
            rf"^Damage from attacks used by this {_POKEMON_TOKEN} isn't affected by any effects on your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_ignore_effects_damage_from_attacks_used,
    ),
    TextTemplate(
        name="festival_grounds_attack_twice",
        description="Festival Grounds condition allows attacking twice.",
        pattern=re.compile(
            rf"^If Festival Grounds is in play, this {_POKEMON_TOKEN} may use an attack it has twice\. If the first attack Knocks Out your opponent's Active {_POKEMON_TOKEN}, you may attack again after your opponent chooses a new Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_festival_grounds_attack_twice,
    ),
    TextTemplate(
        name="for_each_bench_attach_from_deck",
        description="For each Benched Pokémon, attach matching Energy from deck.",
        pattern=re.compile(
            rf"^For each of your Benched {_POKEMON_TOKEN}, search your deck for a (?P<descriptor>.+?) Energy card and attach it to that {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_for_each_bench_attach_from_deck,
    ),
    TextTemplate(
        name="future_attack_bonus",
        description="Future Pokémon attacks do more damage this turn.",
        pattern=re.compile(
            rf"^Attacks used by your Future {_POKEMON_TOKEN}, except any Iron Crown ex, do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_future_attack_bonus,
    ),
    TextTemplate(
        name="damage_to_opponent_pokemon_count",
        description="Deal fixed damage to one or more of your opponent Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<damage>\d+) damage to (?P<count>\d+) of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_to_opponent_pokemon_count,
    ),
    TextTemplate(
        name="ignore_effects_on_those_pokemon",
        description="Ignore weakness/resistance/effects on selected Pokémon targets.",
        pattern=re.compile(
            rf"^This attack's damage isn't affected by Weakness or Resistance, or by any effects on those {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_ignore_effects_on_those_pokemon,
    ),
    TextTemplate(
        name="damage_more_per_self_counter",
        description="Damage bonus for each damage counter on this Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each damage counter on this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_self_counter,
    ),
    TextTemplate(
        name="discard_any_amount_energy_from_self",
        description="Discard any amount of Basic Energy from your Pokémon.",
        pattern=re.compile(
            rf"^You may discard any amount of .+? Energy from your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_any_amount_energy_from_self,
    ),
    TextTemplate(
        name="damage_base_per_discarded_energy",
        description="Base damage per card discarded in this way.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_damage_base_per_discarded_energy,
    ),
    TextTemplate(
        name="heal_equal_to_damage_dealt",
        description="Heal equal to damage dealt to opponent Active.",
        pattern=re.compile(
            rf"^Heal from this {_POKEMON_TOKEN} the same amount of damage you did to your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_heal_equal_to_damage_dealt,
    ),
    TextTemplate(
        name="attack_cost_reduction_per_prize",
        description="Named attack costs less per prize opponent has taken.",
        pattern=re.compile(
            rf"^(?P<attack>.+?) used by this {_POKEMON_TOKEN} costs \{{[A-Z]\}} less for each Prize card your opponent has taken\.$",
            re.IGNORECASE,
        ),
        builder=_attack_cost_reduction_per_prize,
    ),
    TextTemplate(
        name="prevent_damage_from_basic",
        description="Prevent damage from Basic Pokémon attacks next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, prevent all damage done to this {_POKEMON_TOKEN} by attacks from Basic {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_damage_from_basic,
    ),
    TextTemplate(
        name="search_pokemon_to_hand_multi",
        description="Search deck for up to N Pokémon and put into hand.",
        pattern=re.compile(
            rf"^Search your deck for up to (?P<count>\d+) {_POKEMON_TOKEN}, reveal them, and put them into your hand\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_search_pokemon_to_hand_multi,
    ),
    TextTemplate(
        name="damage_per_opponent_damage_counter",
        description="Damage for each damage counter on opponent Active Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each damage counter on your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_opponent_damage_counter,
    ),
    TextTemplate(
        name="flip_until_tails_damage_bonus",
        description="Flip until tails for repeated heads damage bonus.",
        pattern=re.compile(
            r"^Flip a coin until you get tails\. This attack does (?P<amount>\d+) more damage for each heads\.$",
            re.IGNORECASE,
        ),
        builder=_flip_until_tails_damage_bonus,
    ),
    TextTemplate(
        name="discard_top_n_opponent_deck",
        description="Discard top N cards of opponent deck.",
        pattern=re.compile(
            r"^Discard the top (?P<count>\d+) cards of your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_discard_top_n_opponent_deck,
    ),
    TextTemplate(
        name="then_discard_that_stadium",
        description="Discard that Stadium.",
        pattern=re.compile(r"^Then, discard that Stadium\.$", re.IGNORECASE),
        builder=_then_discard_that_stadium,
    ),
    TextTemplate(
        name="prevent_effects_not_damage",
        description="Prevent all attack effects (not damage).",
        pattern=re.compile(
            rf"^Prevent all effects of attacks used by your opponent's {_POKEMON_TOKEN} done to this {_POKEMON_TOKEN}\. \(Damage is not an effect\.\)$",
            re.IGNORECASE,
        ),
        builder=_prevent_effects_not_damage,
    ),
    TextTemplate(
        name="heal_each_self_pokemon",
        description="Heal fixed amount from each of your Pokémon.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from each of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_heal_each_self_pokemon,
    ),
    TextTemplate(
        name="choose_opponent_active_attack",
        description="Choose one attack from opponent Active Pokémon.",
        pattern=re.compile(
            rf"^Choose 1 of your opponent's Active {_POKEMON_TOKEN}'s attacks\.$",
            re.IGNORECASE,
        ),
        builder=_choose_opponent_active_attack,
    ),
    TextTemplate(
        name="cannot_use_chosen_attack_next_turn",
        description="That Pokémon cannot use the chosen attack next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, that {_POKEMON_TOKEN} can't use that attack\.$",
            re.IGNORECASE,
        ),
        builder=_cannot_use_chosen_attack_next_turn,
    ),
    TextTemplate(
        name="once_if_ko_last_turn_draw",
        description="Once per turn, draw if your Pokémon was KOed last turn.",
        pattern=re.compile(
            rf"^Once during your turn, if any of your {_POKEMON_TOKEN} were Knocked Out during your opponent's last turn, you may draw (?P<count>\d+) cards\.$",
            re.IGNORECASE,
        ),
        builder=_once_if_ko_last_turn_draw,
    ),
    TextTemplate(
        name="limit_named_ability_per_turn",
        description="Cannot use a named Ability more than N times each turn.",
        pattern=re.compile(
            r"^You can't use more than (?P<count>\d+) .+? Ability each turn\.$",
            re.IGNORECASE,
        ),
        builder=_limit_named_ability_per_turn,
    ),
    TextTemplate(
        name="limit_named_ability_during_turn",
        description="Cannot use a named Ability more than N times during your turn.",
        pattern=re.compile(
            r"^You can't use more than (?P<count>\d+) .+? Ability during your turn\.$",
            re.IGNORECASE,
        ),
        builder=_limit_named_ability_during_turn,
    ),
    TextTemplate(
        name="place_damage_counters_opponent_bench",
        description="Place damage counters on opponent Benched Pokémon.",
        pattern=re.compile(
            rf"^Put (?P<count>\d+) damage counters on your opponent's Benched {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_place_damage_counters_opponent_bench,
    ),
    TextTemplate(
        name="attacking_pokemon_is_poisoned_on_damage",
        description="If damaged while Active, poison the attacking Pokémon.",
        pattern=re.compile(
            rf"^If this {_POKEMON_TOKEN} is in the Active Spot and is damaged by an attack from your opponent's {_POKEMON_TOKEN} \(even if this {_POKEMON_TOKEN} is Knocked Out\), the Attacking {_POKEMON_TOKEN} is now Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_attacking_pokemon_is_poisoned_on_damage,
    ),
    TextTemplate(
        name="cannot_use_named_attack_until_leave_active",
        description="Cannot reuse a named attack until leaving Active Spot.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} can't use (?P<attack>.+?) again until it leaves the Active Spot\.$",
            re.IGNORECASE,
        ),
        builder=_cannot_use_named_attack_until_leave_active,
    ),
    TextTemplate(
        name="retaliate_damage_counters_next_turn",
        description="Retaliate with damage counters when damaged next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, if this {_POKEMON_TOKEN} is damaged by an attack \(even if it is Knocked Out\), put (?P<count>\d+) damage counters on the Attacking {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_retaliate_damage_counters_next_turn,
    ),
    TextTemplate(
        name="conditional_bonus_and_discard_all_energy",
        description="If opponent Active is Evolution, bonus damage and discard all self energy.",
        pattern=re.compile(
            rf"^If your opponent's Active {_POKEMON_TOKEN} is an Evolution {_POKEMON_TOKEN}, this attack does (?P<amount>\d+) more damage, and discard all Energy from this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_conditional_bonus_and_discard_all_energy,
    ),
    TextTemplate(
        name="shuffle_attached_energy_into_deck",
        description="Shuffle attached Energy into deck.",
        pattern=re.compile(
            rf"^You may shuffle (?P<count>\d+) Energy attached to this {_POKEMON_TOKEN} into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_shuffle_attached_energy_into_deck,
    ),
    TextTemplate(
        name="prevent_damage_from_ability_pokemon",
        description="Prevent damage from opponent Pokémon that have an Ability.",
        pattern=re.compile(
            rf"^Prevent all damage from attacks done to this {_POKEMON_TOKEN} by your opponent's {_POKEMON_TOKEN} that have an Ability\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_damage_from_ability_pokemon,
    ),
    TextTemplate(
        name="choose_one_bullet_modes",
        description="Choose 1 between bullet-listed mode effects.",
        pattern=re.compile(r"^Choose 1: .+$", re.IGNORECASE),
        builder=_choose_one_bullet_modes,
    ),
    TextTemplate(
        name="defending_attack_damage_reduction_next_turn",
        description="Defending Pokémon attacks do less damage next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, attacks used by the Defending {_POKEMON_TOKEN} do (?P<amount>\d+) less damage \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_defending_attack_damage_reduction_next_turn,
    ),
    TextTemplate(
        name="festival_grounds_attack_twice_first_clause",
        description="Festival Grounds allows this Pokémon to attack twice.",
        pattern=re.compile(
            rf"^If Festival Grounds is in play, this {_POKEMON_TOKEN} may use an attack it has twice\.$",
            re.IGNORECASE,
        ),
        builder=_festival_grounds_attack_twice_first_clause,
    ),
    TextTemplate(
        name="if_first_attack_ko_attack_again",
        description="If first attack KOs, this Pokémon may attack again.",
        pattern=re.compile(
            rf"^If the first attack Knocks Out your opponent's Active {_POKEMON_TOKEN}, you may attack again after your opponent chooses a new Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_if_first_attack_ko_attack_again,
    ),
    TextTemplate(
        name="flip_until_tails",
        description="Flip coin until tails setup clause.",
        pattern=re.compile(r"^Flip a coin until you get tails\.$", re.IGNORECASE),
        builder=_flip_until_tails,
    ),
    TextTemplate(
        name="damage_bonus_per_heads_after_until_tails",
        description="Damage bonus for each heads after flip-until-tails.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) more damage for each heads\.$",
            re.IGNORECASE,
        ),
        builder=_damage_bonus_per_heads_after_until_tails,
    ),
    TextTemplate(
        name="prevent_effects_not_damage_single",
        description="Prevent all attack effects done to this Pokémon (not damage).",
        pattern=re.compile(
            rf"^Prevent all effects of attacks used by your opponent's {_POKEMON_TOKEN} done to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_effects_not_damage_single,
    ),
    TextTemplate(
        name="turn_damage_bonus_to_active_ex_v",
        description="Bonus damage against Active Pokémon ex and Active Pokémon V.",
        pattern=re.compile(
            rf"^During this turn, attacks used by your {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} ex and Active {_POKEMON_TOKEN} V \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_turn_damage_bonus_to_active_ex_v,
    ),
    TextTemplate(
        name="if_you_do_new_active_poisoned",
        description="If you did switch, new Active Pokémon is Poisoned.",
        pattern=re.compile(
            rf"^If you do, the new Active {_POKEMON_TOKEN} is now Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_if_you_do_new_active_poisoned,
    ),
    TextTemplate(
        name="opponent_flips_coin_when_defending_attacks",
        description="Defending attack attempt forces opponent coin flip.",
        pattern=re.compile(
            rf"^During your opponent's next turn, if the Defending {_POKEMON_TOKEN} tries to use an attack, your opponent flips a coin\.$",
            re.IGNORECASE,
        ),
        builder=_opponent_flips_coin_when_defending_attacks,
    ),
    TextTemplate(
        name="if_tails_attack_doesnt_happen",
        description="If tails, that attack does not happen.",
        pattern=re.compile(
            r"^If tails, that attack doesn't happen\.$",
            re.IGNORECASE,
        ),
        builder=_if_tails_attack_doesnt_happen,
    ),
    TextTemplate(
        name="can_use_attack_if_go_first",
        description="If you go first, can use this attack on first turn.",
        pattern=re.compile(
            r"^If you go first, you can use this attack during your first turn\.$",
            re.IGNORECASE,
        ),
        builder=_can_use_attack_if_go_first,
    ),
    TextTemplate(
        name="if_go_first_may_use_card_first_turn",
        description="If you go first, you may use this card during your first turn.",
        pattern=re.compile(
            r"^If you go first, you may use this card during your first turn\.$",
            re.IGNORECASE,
        ),
        builder=_if_go_first_may_use_card_first_turn,
    ),
    TextTemplate(
        name="switch_benched_with_active_generic",
        description="Switch one tagged Benched Pokémon with your Active Pokémon.",
        pattern=re.compile(
            rf"^Switch 1 of your Benched .+? {_POKEMON_TOKEN}, except any .+?, with your Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_switch_benched_with_active_generic,
    ),
    TextTemplate(
        name="prize_take_reduction_when_dark_koed_by_ex",
        description="Opponent takes fewer prize cards when your dark Pokémon is KOed by ex.",
        pattern=re.compile(
            rf"^If 1 of your \{{[A-Z]\}} {_POKEMON_TOKEN} is Knocked Out by damage from an attack from your opponent's {_POKEMON_TOKEN} ex, that player takes (?P<count>\d+) fewer Prize card\.$",
            re.IGNORECASE,
        ),
        builder=_prize_take_reduction_when_dark_koed_by_ex,
    ),
    TextTemplate(
        name="effect_doesnt_stack_note",
        description="Effect does not stack reminder text.",
        pattern=re.compile(r"^The effect of .+? doesn't stack\.$", re.IGNORECASE),
        builder=_effect_doesnt_stack_note,
    ),
    TextTemplate(
        name="damage_per_self_pokemon_with_round",
        description="Damage scaling by your Pokémon in play with Round attack.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your {_POKEMON_TOKEN} in play that has the Round attack\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_self_pokemon_with_round,
    ),
    TextTemplate(
        name="discard_basic_energy_cost_for_ability",
        description="Discard a typed Basic energy as ability cost.",
        pattern=re.compile(
            rf"^You must discard a Basic \{{[A-Z]\}} Energy from this {_POKEMON_TOKEN} in order to use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_discard_basic_energy_cost_for_ability,
    ),
    TextTemplate(
        name="copy_opponent_active_attack",
        description="Choose one opponent Active attack and use it as this attack.",
        pattern=re.compile(
            rf"^Choose 1 of your opponent's Active {_POKEMON_TOKEN}'s attacks and use it as this attack\.$",
            re.IGNORECASE,
        ),
        builder=_copy_opponent_active_attack,
    ),
    TextTemplate(
        name="once_if_dark_energy_move_damage_counters",
        description="Once during turn if dark energy attached, move damage counters.",
        pattern=re.compile(
            rf"^Once during your turn, if this {_POKEMON_TOKEN} has any \{{[A-Z]\}} Energy attached, you may move up to \d+ damage counters from \d+ of your {_POKEMON_TOKEN} to \d+ of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_once_if_dark_energy_move_damage_counters,
    ),
    TextTemplate(
        name="once_look_top_pick_one",
        description="Once during turn look top N cards and keep one.",
        pattern=re.compile(
            r"^Once during your turn, you may look at the top (?P<look>\d+) cards of your deck and put (?P<pick>\d+) of them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_once_look_top_pick_one,
    ),
    TextTemplate(
        name="once_first_turn_search_limited_hp",
        description="Once during first turn, search typed Pokémon with HP limit.",
        pattern=re.compile(
            rf"^Once during your first turn, you may search your deck for up to (?P<count>\d+) \{{[A-Z]\}} {_POKEMON_TOKEN} with (?P<hp>\d+) HP or less, reveal them, and put them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_once_first_turn_search_limited_hp,
    ),
    TextTemplate(
        name="attack_cost_reduction_if_more_prizes",
        description="If you have more prizes remaining, attached Pokémon attacks cost less.",
        pattern=re.compile(
            r"^If you have more Prize cards remaining than your opponent, attacks used by the Pokémon this card is attached to cost \{[A-Z]\} less\.$",
            re.IGNORECASE,
        ),
        builder=_attack_cost_reduction_if_more_prizes,
    ),
    TextTemplate(
        name="card_use_gate_if_have_tera",
        description="Card can be used only if you have any Tera Pokémon in play.",
        pattern=re.compile(
            rf"^You can use this card only if you have any Tera {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_card_use_gate_if_have_tera,
    ),
    TextTemplate(
        name="attach_basic_energy_discard_to_benched_count",
        description="Attach basic energy from discard to up to N benched typed Pokémon.",
        pattern=re.compile(
            rf"^Choose up to (?P<count>\d+) of your Benched \{{[A-Z]\}} {_POKEMON_TOKEN} and attach a Basic Energy card from your discard pile to each of them\.$",
            re.IGNORECASE,
        ),
        builder=_attach_basic_energy_discard_to_benched_count,
    ),
    TextTemplate(
        name="card_use_gate_discard_another_card",
        description="Card can be used only if you discard another card.",
        pattern=re.compile(
            r"^You can use this card only if you discard another card from your hand\.$",
            re.IGNORECASE,
        ),
        builder=_card_use_gate_discard_another_card,
    ),
    TextTemplate(
        name="conditional_draw_until_if_all_team_rocket",
        description="If all in-play Pokémon are Team Rocket's, draw until hand size.",
        pattern=re.compile(
            rf"^If all of your {_POKEMON_TOKEN} in play are Team Rocket's {_POKEMON_TOKEN}, draw cards until you have (?P<count>\d+) cards in your hand instead\.$",
            re.IGNORECASE,
        ),
        builder=_conditional_draw_until_if_all_team_rocket,
    ),
    TextTemplate(
        name="as_long_as_attached_provides_colorless",
        description="Attached card provides colorless energy while attached.",
        pattern=re.compile(
            rf"^As long as this card is attached to a {_POKEMON_TOKEN}, it provides \{{[A-Z]\}} Energy\.$",
            re.IGNORECASE,
        ),
        builder=_as_long_as_attached_provides_colorless,
    ),
    TextTemplate(
        name="opponent_discards_cards_from_hand",
        description="Opponent discards one or more cards from hand.",
        pattern=re.compile(
            r"^Your opponent discards (?:(?P<count>\d+) cards?|a card) from their hand\.$",
            re.IGNORECASE,
        ),
        builder=_opponent_discards_cards_from_hand,
    ),
    TextTemplate(
        name="for_each_heads_discard_top_opponent_deck",
        description="For each heads, discard top card of opponent deck.",
        pattern=re.compile(
            r"^For each heads, discard the top card of your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-heads-discard-top-opponent-deck"),
    ),
    TextTemplate(
        name="for_each_opponent_pokemon_flip_coin",
        description="For each opponent Pokémon, flip a coin.",
        pattern=re.compile(
            rf"^For each of your opponent's {_POKEMON_TOKEN}, flip a coin\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-opponent-pokemon-flip-coin"),
    ),
    TextTemplate(
        name="damage_less_per_self_counter",
        description="Attack does less damage for each damage counter on this Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) less damage for each damage counter on this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-less-per-self-counter", ("amount",)),
    ),
    TextTemplate(
        name="once_if_active_discard_energy_place_counters",
        description="Once during turn while active, discard energy to place damage counters.",
        pattern=re.compile(
            rf"^Once during your turn, if this {_POKEMON_TOKEN} is in the Active Spot, you may discard a Basic \{{[A-Z]\}} Energy card from your hand in order to use this Ability\. Place \d+ damage counters on \d+ of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-if-active-discard-energy-place-counters"),
    ),
    TextTemplate(
        name="return_attached_energy_for_bonus_damage",
        description="May return attached energy to hand for bonus damage.",
        pattern=re.compile(
            rf"^You may put a \{{[A-Z]\}} Energy attached to this {_POKEMON_TOKEN} into your hand and have this attack do (?P<amount>\d+) more damage\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("return-attached-energy-for-bonus-damage", ("amount",)),
    ),
    TextTemplate(
        name="move_energy_opponent_active_to_bench",
        description="Move energy from opponent active to bench.",
        pattern=re.compile(
            rf"^You may move an Energy from your opponent's Active {_POKEMON_TOKEN} to \d+ of their Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_move_energy_opponent_active_to_bench,
    ),
    TextTemplate(
        name="discard_special_energy_from_opponent_active",
        description="Discard special energy from opponent active Pokémon.",
        pattern=re.compile(
            rf"^Discard a Special Energy from your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_special_energy_from_opponent_active,
    ),
    TextTemplate(
        name="search_two_cards_stack_top",
        description="Search two cards then stack them on top of deck.",
        pattern=re.compile(
            r"^Search your deck for 2 cards, shuffle your deck, then put those cards on top of it in any order\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-two-cards-stack-top"),
    ),
    TextTemplate(
        name="opponent_reveals_hand_discard_up_to_items",
        description="Opponent reveals hand and you discard up to item cards.",
        pattern=re.compile(
            r"^Your opponent reveals their hand, and you discard up to (?P<count>\d+) Item cards you find there\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-reveal-hand-discard-items", ("count",)),
    ),
    TextTemplate(
        name="damage_more_per_opponent_benched",
        description="Damage bonus per opponent benched Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_opponent_benched,
    ),
    TextTemplate(
        name="status_burned_and_confused",
        description="Apply both Burned and Confused to opponent active.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now Burned and Confused\.$",
            re.IGNORECASE,
        ),
        builder=_status_burned_and_confused,
    ),
    TextTemplate(
        name="put_into_play_only_with_named_ability",
        description="This Pokémon can only be put into play via named ability.",
        pattern=re.compile(
            rf"^Put this {_POKEMON_TOKEN} into play only with the effect of .+? Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-into-play-only-with-named-ability"),
    ),
    TextTemplate(
        name="prevent_effects_when_opponent_plays_item_supporter",
        description="Prevent effects from opponent item/supporter cards played from hand.",
        pattern=re.compile(
            rf"^Whenever your opponent plays an Item or Supporter card from their hand, prevent all effects of that card done to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-effects-when-opponent-plays-item-supporter"),
    ),
    TextTemplate(
        name="choose_up_to_two_then_attach_from_deck",
        description="Choose up to two Pokémon, attach basic energy from deck to each.",
        pattern=re.compile(
            rf"^Choose up to (?P<count>\d+) of your \{{[A-Z]\}} {_POKEMON_TOKEN}\. For each of those {_POKEMON_TOKEN}, search your deck for a Basic \{{[A-Z]\}} Energy card and attach it to that {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-up-to-two-attach-from-deck", ("count",)),
    ),
    TextTemplate(
        name="damage_more_per_typed_energy_all_self",
        description="Damage bonus per typed energy attached to all your Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each \{{[A-Z]\}} Energy attached to all of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-more-per-typed-energy-all-self", ("amount",)),
    ),
    TextTemplate(
        name="attack_cost_less_per_named_card_in_discard",
        description="Attacks cost less per named card in discard pile.",
        pattern=re.compile(
            rf"^Attacks used by this {_POKEMON_TOKEN} cost \{{[A-Z]\}} less for each .+? card in your discard pile\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-cost-less-per-named-card-discard"),
    ),
    TextTemplate(
        name="exact_two_prizes_take_extra_prize_turn",
        description="If opponent has exactly two prizes, may take extra prize on knockout this turn.",
        pattern=re.compile(
            rf"^You can use this card only if your opponent has exactly (?P<count>\d+) Prize cards remaining\. During this turn, if your opponent's Active {_POKEMON_TOKEN} is Knocked Out by damage from an attack used by your Tera {_POKEMON_TOKEN}, take \d+ more Prize card\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("exact-two-prizes-extra-prize-turn", ("count",)),
    ),
    TextTemplate(
        name="search_two_basic_energy_diff_types_split",
        description="Search two basic energy of different types, split hand/attach.",
        pattern=re.compile(
            rf"^Search your deck for up to (?P<count>\d+) Basic Energy cards of different types, reveal them, and put \d+ of them into your hand\. Attach the other to \d+ of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-two-basic-energy-diff-types-split", ("count",)),
    ),
    TextTemplate(
        name="for_each_bench_search_evolution_and_evolve",
        description="For each benched Pokémon, search and evolve from deck.",
        pattern=re.compile(
            rf"^For each of your Benched {_POKEMON_TOKEN}, search your deck for a card that evolves from that {_POKEMON_TOKEN} and put it onto that {_POKEMON_TOKEN} to evolve it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-bench-search-evolution-evolve"),
    ),
    TextTemplate(
        name="attach_any_number_basic_energy_from_hand",
        description="Attach any number of basic energy cards from hand to your Pokémon.",
        pattern=re.compile(
            rf"^You may attach any number of Basic Energy cards from your hand to your {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-any-number-basic-energy-from-hand"),
    ),
    TextTemplate(
        name="look_top_reveal_types_shuffle_rest",
        description="Look top cards, reveal matching types, shuffle rest back.",
        pattern=re.compile(
            rf"^Look at the top (?P<count>\d+) cards of your deck\. You may reveal a {_POKEMON_TOKEN} and a Trainer card you find there and put them into your hand\. Shuffle the other cards back into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-reveal-types-shuffle-rest", ("count",)),
    ),
    TextTemplate(
        name="during_checkup_put_more_counters_instead",
        description="During Pokémon Checkup, put more damage counters instead of one.",
        pattern=re.compile(
            rf"^During {_POKEMON_TOKEN} Checkup, (?:put|place) (?P<count>\d+) damage counters on that {_POKEMON_TOKEN} instead of \d+\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-checkup-put-more-counters-instead", ("count",)),
    ),
    TextTemplate(
        name="on_evolve_place_counters_on_two_opponent",
        description="When evolved from hand, place counters on two opponent Pokémon.",
        pattern=re.compile(
            rf"^When you play this {_POKEMON_TOKEN} from your hand to evolve \d+ of your {_POKEMON_TOKEN} during your turn, you may choose (?P<count>\d+) of your opponent's {_POKEMON_TOKEN} and put \d+ damage counters on each of them\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("on-evolve-place-counters-on-two-opponent", ("count",)),
    ),
    TextTemplate(
        name="may_put_self_into_hand_discard_attached",
        description="May put this Pokémon into hand and discard attached cards.",
        pattern=re.compile(
            rf"^You may put this {_POKEMON_TOKEN} into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_scoop_up_self,
    ),
    TextTemplate(
        name="shuffle_that_pokemon_and_attached_into_deck",
        description="Shuffle that Pokémon and all attached cards into deck.",
        pattern=re.compile(
            rf"^Shuffle that {_POKEMON_TOKEN} and all attached cards into their deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-that-pokemon-and-attached-into-deck"),
    ),
    TextTemplate(
        name="for_each_heads_discard_energy_opponent_active",
        description="For each heads, discard an energy from opponent active.",
        pattern=re.compile(
            rf"^For each heads, discard an Energy from your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-heads-discard-energy-opponent-active"),
    ),
    TextTemplate(
        name="place_damage_counters_on_opponent_any",
        description="Place damage counters on one of opponent's Pokémon.",
        pattern=re.compile(
            rf"^Place (?P<count>\d+) damage counters on \d+ of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_place_damage_counters_on_opponent_any,
    ),
    TextTemplate(
        name="choose_up_to_self_typed_pokemon",
        description="Choose up to N of your typed Pokémon.",
        pattern=re.compile(
            rf"^Choose up to (?P<count>\d+) of your \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_choose_up_to_self_typed_pokemon,
    ),
    TextTemplate(
        name="for_each_of_those_search_attach_energy",
        description="For each chosen Pokémon, search deck and attach basic typed energy.",
        pattern=re.compile(
            rf"^For each of those {_POKEMON_TOKEN}, search your deck for a Basic \{{[A-Z]\}} Energy card and attach it to that {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-of-those-search-attach-energy"),
    ),
    TextTemplate(
        name="card_use_gate_opponent_exact_prizes",
        description="Card use gate when opponent has exactly N prizes.",
        pattern=re.compile(
            r"^You can use this card only if your opponent has exactly (?P<count>\d+) Prize cards remaining\.$",
            re.IGNORECASE,
        ),
        builder=_card_use_gate_opponent_exact_prizes,
    ),
    TextTemplate(
        name="during_turn_tera_ko_take_more_prize",
        description="This turn, tera KO can take more prize cards.",
        pattern=re.compile(
            rf"^During this turn, if your opponent's Active {_POKEMON_TOKEN} is Knocked Out by damage from an attack used by your Tera {_POKEMON_TOKEN}, take (?P<count>\d+) more Prize card\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-turn-tera-ko-take-more-prize", ("count",)),
    ),
    TextTemplate(
        name="search_up_to_basic_energy_diff_types_to_hand",
        description="Search up to N basic energy of different types and put one into hand.",
        pattern=re.compile(
            rf"^Search your deck for up to (?P<count>\d+) Basic Energy cards of different types, reveal them, and put (?P<to_hand>\d+) of them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-up-to-basic-energy-diff-types-to-hand", ("count", "to_hand")),
    ),
    TextTemplate(
        name="attach_other_to_one_self_pokemon",
        description="Attach the other selected card to one of your Pokémon.",
        pattern=re.compile(
            rf"^Attach the other to \d+ of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-other-to-one-self-pokemon"),
    ),
    TextTemplate(
        name="look_top_n_cards_only",
        description="Look at top N cards of your deck.",
        pattern=re.compile(
            r"^Look at the top (?P<count>\d+) cards of your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-n-cards-only", ("count",)),
    ),
    TextTemplate(
        name="reveal_pokemon_and_trainer_from_top",
        description="Reveal a Pokémon and Trainer from looked cards and put into hand.",
        pattern=re.compile(
            rf"^You may reveal a {_POKEMON_TOKEN} and a Trainer card you find there and put them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-pokemon-and-trainer-from-top"),
    ),
    TextTemplate(
        name="shuffle_other_cards_back_into_deck",
        description="Shuffle the other cards back into your deck.",
        pattern=re.compile(
            r"^Shuffle the other cards back into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-other-cards-back-into-deck"),
    ),
    TextTemplate(
        name="choose_least_hp_and_knock_out",
        description="Choose least-HP Pokémon in play and knock it out.",
        pattern=re.compile(
            rf"^Choose a {_POKEMON_TOKEN} in play \(yours or your opponent's\) that has the least HP remaining, except for this {_POKEMON_TOKEN}, and it is Knocked Out\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-least-hp-and-knock-out"),
    ),
    TextTemplate(
        name="place_counters_per_card_in_hand",
        description="Place damage counters per card in your hand.",
        pattern=re.compile(
            rf"^Place (?P<count>\d+) damage counters on your opponent's Active {_POKEMON_TOKEN} for each card in your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("place-counters-per-card-in-hand", ("count",)),
    ),
    TextTemplate(
        name="once_if_have_named_in_play_discard_energy",
        description="Once during turn if named Pokémon in play, may discard basic energy to use ability.",
        pattern=re.compile(
            r"^Once during your turn, if you have .+? in play, you may discard a Basic \{[A-Z]\} Energy card from your hand in order to use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-if-have-named-in-play-discard-energy"),
    ),
    TextTemplate(
        name="opponent_reveals_hand_discard_one_found",
        description="Opponent reveals hand and you discard one card from it.",
        pattern=re.compile(
            r"^Your opponent reveals their hand, and you discard a card you find there\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-reveals-hand-discard-one-found"),
    ),
    TextTemplate(
        name="search_basic_energy_or_basic_pokemon_to_hand",
        description="Search deck for typed basic energy or basic Pokémon and put into hand.",
        pattern=re.compile(
            rf"^Search your deck for a Basic \{{[A-Z]\}} Energy card or a Basic \{{[A-Z]\}} {_POKEMON_TOKEN}, reveal it, and put it into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-basic-energy-or-basic-pokemon-to-hand"),
    ),
    TextTemplate(
        name="each_players_typed_can_evolve_turn_played",
        description="Typed Pokémon can evolve on the turn played except first turn.",
        pattern=re.compile(
            rf"^Each player's \{{[A-Z]\}} {_POKEMON_TOKEN} can evolve into \{{[A-Z]\}} {_POKEMON_TOKEN} during the turn they play those {_POKEMON_TOKEN}, except during their first turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-players-typed-can-evolve-turn-played"),
    ),
    TextTemplate(
        name="ask_opponent_each_player_take_prize",
        description="Ask opponent whether each player may take a prize card.",
        pattern=re.compile(
            r"^Ask your opponent if each player may take a Prize card\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("ask-opponent-each-player-take-prize"),
    ),
    TextTemplate(
        name="search_mega_evolution_ex_to_hand",
        description="Search deck for a Mega Evolution Pokémon ex to hand.",
        pattern=re.compile(
            rf"^Search your deck for a Mega Evolution {_POKEMON_TOKEN} ex, reveal it, and put it into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-mega-evolution-ex-to-hand"),
    ),
    TextTemplate(
        name="once_each_players_discard_energy_draw_until_typed_in_play",
        description="Once during each player's turn, discard energy to draw up to typed in-play count.",
        pattern=re.compile(
            rf"^Once during each player's turn, that player may discard an Energy card from their hand in order to draw cards until they have as many cards in their hand as they have \{{[A-Z]\}} {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-each-players-discard-energy-draw-until-typed-in-play"),
    ),
    TextTemplate(
        name="turn_damage_bonus_typed_to_opponent_active",
        description="During this turn, attacks by your typed Pokémon do bonus damage to opponent active.",
        pattern=re.compile(
            rf"^During this turn, attacks used by your \{{[A-Z]\}} {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("turn-damage-bonus-typed-to-opponent-active", ("amount",)),
    ),
    TextTemplate(
        name="card_use_gate_discard_n_other_cards",
        description="Card use gate that requires discarding N other cards from hand.",
        pattern=re.compile(
            r"^You can use this card only if you discard (?P<count>\d+) other cards from your hand\.$",
            re.IGNORECASE,
        ),
        builder=_card_use_gate_discard_n_other_cards,
    ),
    TextTemplate(
        name="heal_all_damage_from_mega_evolution_ex",
        description="Heal all damage from one of your Mega Evolution Pokémon ex.",
        pattern=re.compile(
            rf"^Heal all damage from \d+ of your Mega Evolution {_POKEMON_TOKEN} ex\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-all-damage-from-mega-evolution-ex"),
    ),
    TextTemplate(
        name="retreat_cost_less_attached",
        description="Attached Pokémon has reduced retreat cost.",
        pattern=re.compile(
            rf"^The Retreat Cost of the {_POKEMON_TOKEN} this card is attached to is .+? less\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("retreat-cost-less-attached"),
    ),
    TextTemplate(
        name="as_often_if_have_mega_in_play_may_use_ability",
        description="As often as you like, if you have typed Mega Evolution ex in play, may use ability.",
        pattern=re.compile(
            rf"^As often as you like during your turn, if you have any \{{[A-Z]\}} Mega Evolution {_POKEMON_TOKEN} ex in play, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("as-often-if-have-mega-in-play-may-use-ability"),
    ),
    TextTemplate(
        name="named_pokemon_may_have_two_tools",
        description="Named Pokémon may have up to two tools attached.",
        pattern=re.compile(
            rf'^Each of your {_POKEMON_TOKEN} that has ".+?" in its name may have up to (?P<count>\d+) {_POKEMON_TOKEN} Tool cards attached\.$',
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("named-pokemon-may-have-two-tools", ("count",)),
    ),
    TextTemplate(
        name="discard_up_to_energy_damage_per_discarded",
        description="Discard up to N energy and deal damage per discarded card.",
        pattern=re.compile(
            rf"^Discard up to (?P<count>\d+) Energy cards from this {_POKEMON_TOKEN}, and this attack does (?P<amount>\d+) damage for each card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_discard_up_to_energy_and_damage_per_discarded,
    ),
    TextTemplate(
        name="may_also_use_ability_when_active_koed",
        description="May also use this ability if active and knocked out by opponent attack.",
        pattern=re.compile(
            rf"^You may also use this Ability if this {_POKEMON_TOKEN} is in the Active Spot and is Knocked Out by damage from an attack from your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("may-also-use-ability-when-active-koed"),
    ),
    TextTemplate(
        name="search_basic_energy_attach_to_benched_typed",
        description="Search basic typed energy from deck and attach to benched typed Pokémon.",
        pattern=re.compile(
            rf"^Search your deck for a Basic \{{[A-Z]\}} Energy card and attach it to \d+ of your Benched \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-basic-energy-attach-to-benched-typed"),
    ),
    TextTemplate(
        name="search_basic_stage1_stage2_to_hand",
        description="Search deck for basic, stage 1, and stage 2 Pokémon and put into hand.",
        pattern=re.compile(
            rf"^Search your deck for a Basic {_POKEMON_TOKEN}, a Stage \d+ {_POKEMON_TOKEN}, and a Stage \d+ {_POKEMON_TOKEN}, reveal them, and put them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-basic-stage1-stage2-to-hand"),
    ),
    TextTemplate(
        name="damage_per_team_rocket_in_play",
        description="Damage for each Team Rocket's Pokémon in play.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your Team Rocket's {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_damage_per_team_rocket_in_play,
    ),
    TextTemplate(
        name="discard_n_energy_and_damage_to_opponent_any",
        description="Discard fixed energy and deal damage to one of opponent's Pokémon.",
        pattern=re.compile(
            rf"^Discard (?P<count>\d+) Energy from this {_POKEMON_TOKEN}, and this attack does (?P<amount>\d+) damage to \d+ of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_energy_and_damage_to_opponent_any,
    ),
    TextTemplate(
        name="discard_up_to_typed_energy_from_self",
        description="Discard up to N typed energy from this Pokémon.",
        pattern=re.compile(
            rf"^Discard up to (?P<count>\d+) \{{[A-Z]\}} Energy from this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_up_to_typed_energy,
    ),
    TextTemplate(
        name="damage_per_basic_energy_in_opponent_discard",
        description="Damage scaling by basic energy cards in opponent discard.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each Basic Energy card in your opponent's discard pile\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-per-basic-energy-in-opponent-discard", ("amount",)),
    ),
    TextTemplate(
        name="discard_all_energy_and_damage_opponent_bench",
        description="Discard all energy from this Pokémon and damage one opponent benched Pokémon.",
        pattern=re.compile(
            rf"^Discard all Energy from this {_POKEMON_TOKEN}, and this attack also does (?P<amount>\d+) damage to \d+ of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_discard_all_energy_and_damage_bench,
    ),
    TextTemplate(
        name="card_use_gate_generic",
        description="Generic card-use gate clause.",
        pattern=re.compile(r"^You can use this card only if .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("card-use-gate-generic"),
    ),
    TextTemplate(
        name="each_player_shuffles_hand_into_deck",
        description="Each player shuffles hand into deck.",
        pattern=re.compile(r"^Each player shuffles their hand into their deck\.$", re.IGNORECASE),
        builder=_script_hook_builder("each-player-shuffles-hand-into-deck"),
    ),
    TextTemplate(
        name="then_you_draw_and_opponent_draws",
        description="Then you draw cards and opponent draws cards.",
        pattern=re.compile(
            r"^Then, you draw (?P<self_count>\d+) cards, and your opponent draws (?P<opp_count>\d+) cards\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("then-you-draw-and-opponent-draws", ("self_count", "opp_count")),
    ),
    TextTemplate(
        name="heal_damage_from_each_in_play",
        description="Heal fixed damage from each Pokémon in play.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from each {_POKEMON_TOKEN} \(both yours and your opponent's\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-damage-from-each-in-play", ("amount",)),
    ),
    TextTemplate(
        name="status_confused_and_poisoned",
        description="Apply both Confused and Poisoned to opponent active.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now Confused and Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_status_confused_and_poisoned,
    ),
    TextTemplate(
        name="discard_all_tools_and_special_energy_from_opponent",
        description="Discard all tools and special energy from opponent Pokémon.",
        pattern=re.compile(
            rf"^Discard all {_POKEMON_TOKEN} Tools and Special Energy from all of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-all-tools-and-special-energy-from-opponent"),
    ),
    TextTemplate(
        name="discard_top_card_of_your_deck",
        description="Discard the top card of your deck.",
        pattern=re.compile(r"^Discard the top card of your deck\.$", re.IGNORECASE),
        builder=_script_hook_builder("discard-top-card-of-your-deck"),
    ),
    TextTemplate(
        name="poisoned_pokemon_cannot_retreat_next_turn",
        description="Opponent poisoned Pokémon cannot retreat on their next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, their Poisoned {_POKEMON_TOKEN} can't retreat\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("poisoned-pokemon-cannot-retreat-next-turn"),
    ),
    TextTemplate(
        name="as_long_as_active_opponent_active_no_abilities_except_named",
        description="While this active, opponent active has no abilities except named one.",
        pattern=re.compile(
            rf"^As long as this {_POKEMON_TOKEN} is in the Active Spot, your opponent's Active {_POKEMON_TOKEN} has no Abilities, except for .+\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("as-long-as-active-opponent-active-no-abilities-except-named"),
    ),
    TextTemplate(
        name="as_long_as_active_rule_box_no_abilities_except_named",
        description="While this active, Rule Box Pokémon in play have no abilities except named.",
        pattern=re.compile(
            rf"^As long as this {_POKEMON_TOKEN} is in the Active Spot, {_POKEMON_TOKEN} with a Rule Box in play \(both yours and your opponent's\) have no Abilities, except for .+\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("as-long-as-active-rule-box-no-abilities-except-named"),
    ),
    TextTemplate(
        name="heal_all_damage_from_low_hp_self_pokemon",
        description="Heal all damage from one of your low remaining HP Pokémon.",
        pattern=re.compile(
            rf"^Heal all damage from \d+ of your {_POKEMON_TOKEN} that has \d+ HP or less remaining\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-all-damage-from-low-hp-self-pokemon"),
    ),
    TextTemplate(
        name="look_top_n_put_m_discard_rest",
        description="Look top cards, put some in hand, discard rest.",
        pattern=re.compile(
            r"^Look at the top (?P<look>\d+) cards of your deck and put (?P<pick>\d+) of them into your hand\. Discard the other cards\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-n-put-m-discard-rest", ("look", "pick")),
    ),
    TextTemplate(
        name="draw_per_opponent_benched_pokemon",
        description="Draw a card for each opponent benched Pokémon.",
        pattern=re.compile(
            rf"^Draw a card for each of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("draw-per-opponent-benched-pokemon"),
    ),
    TextTemplate(
        name="can_use_on_setup_or_put_into_play_this_turn",
        description="Card can be used on setup Pokémon or one put into play this turn.",
        pattern=re.compile(
            rf"^You can use this card on a {_POKEMON_TOKEN} you put down when you were setting up to play or on a {_POKEMON_TOKEN} that was put into play this turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("can-use-on-setup-or-put-into-play-this-turn"),
    ),
    TextTemplate(
        name="as_long_as_on_bench_prevent_damage_and_effects_to_self",
        description="While this Pokémon is on bench, prevent damage and effects to this Pokémon.",
        pattern=re.compile(
            rf"^As long as this {_POKEMON_TOKEN} is on your Bench, prevent all damage from and effects of attacks from your opponent's {_POKEMON_TOKEN} done to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("as-long-as-on-bench-prevent-damage-and-effects-to-self"),
    ),
    TextTemplate(
        name="put_counters_per_basic_energy_in_discard_and_shuffle_them",
        description="Put counters per basic energy in discard then shuffle those energies.",
        pattern=re.compile(
            rf"^Put (?P<count>\d+) damage counters on \d+ of your opponent's {_POKEMON_TOKEN} for each Basic \{{[A-Z]\}} Energy card in your discard pile\. Then, shuffle those Energy cards into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-counters-per-basic-energy-in-discard-and-shuffle-them", ("count",)),
    ),
    TextTemplate(
        name="you_may_do_more_damage",
        description="Optional fixed bonus damage clause.",
        pattern=re.compile(r"^You may do (?P<amount>\d+) more damage\.$", re.IGNORECASE),
        builder=_script_hook_builder("you-may-do-more-damage", ("amount",)),
    ),
    TextTemplate(
        name="during_checkup_put_counter_on_each_with_ability_except_named",
        description="During Pokémon Checkup, put counters on each Pokémon with ability except named.",
        pattern=re.compile(
            rf"^During {_POKEMON_TOKEN} Checkup, put (?P<count>\d+) damage counter on each {_POKEMON_TOKEN} that has an Ability \(both yours and your opponent's\), except any .+\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-checkup-put-counter-on-each-with-ability-except-named", ("count",)),
    ),
    TextTemplate(
        name="end_opponents_next_turn_put_counters_on_defending",
        description="At end of opponent next turn put damage counters on defending Pokémon.",
        pattern=re.compile(
            rf"^At the end of your opponent's next turn, put (?P<count>\d+) damage counters on the Defending {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("end-opponents-next-turn-put-counters-on-defending", ("count",)),
    ),
    TextTemplate(
        name="recover_supporter_from_discard_to_hand",
        description="Recover supporter card from discard to hand.",
        pattern=re.compile(r"^Put a Supporter card from your discard pile into your hand\.$", re.IGNORECASE),
        builder=_recover_supporter_from_discard,
    ),
    TextTemplate(
        name="damage_per_energy_on_opponent_active_base",
        description="Damage for each energy attached to opponent active.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each Energy attached to your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_base_per_energy_on_opponent_active,
    ),
    TextTemplate(
        name="attack_also_damages_each_own_bench",
        description="Attack also damages each of your benched Pokémon.",
        pattern=re.compile(
            rf"^This attack also does (?P<amount>\d+) damage to each of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-also-damages-each-own-bench", ("amount",)),
    ),
    TextTemplate(
        name="you_may_search_deck_for_a_card",
        description="Optional generic deck search for one card to hand.",
        pattern=re.compile(r"^You may search your deck for a card and put it into your hand\.$", re.IGNORECASE),
        builder=_script_hook_builder("you-may-search-deck-for-a-card"),
    ),
    TextTemplate(
        name="once_if_active_look_top_reveal_supporter",
        description="Once during turn while active, look top cards and reveal supporter.",
        pattern=re.compile(
            rf"^Once during your turn, if this {_POKEMON_TOKEN} is in the Active Spot, you may look at the top (?P<count>\d+) cards of your deck, reveal a Supporter card you find there, and put it into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-if-active-look-top-reveal-supporter", ("count",)),
    ),
    TextTemplate(
        name="put_up_to_combination_rule_box_and_basic_energy_from_discard",
        description="Put up to N in any combination of non-rule-box Pokémon and basic energies from discard to hand.",
        pattern=re.compile(
            r"^Put up to (?P<count>\d+) in any combination of Pokémon that don't have a Rule Box and Basic Energy cards from your discard pile into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-up-to-combination-rule-box-and-basic-energy-from-discard", ("count",)),
    ),
    TextTemplate(
        name="reveal_up_to_pokemon_in_hand_put_into_deck",
        description="Reveal up to N Pokémon in hand and put them into your deck.",
        pattern=re.compile(
            rf"^Reveal up to (?P<count>\d+) {_POKEMON_TOKEN} in your hand and put them into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-up-to-pokemon-in-hand-put-into-deck", ("count",)),
    ),
    TextTemplate(
        name="put_up_to_typed_pokemon_from_discard_onto_bench",
        description="Put up to N typed Pokémon from discard onto bench.",
        pattern=re.compile(
            rf"^Put up to (?P<count>\d+) \{{[A-Z]\}} {_POKEMON_TOKEN} from your discard pile onto your Bench\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-up-to-typed-pokemon-from-discard-onto-bench", ("count",)),
    ),
    TextTemplate(
        name="put_up_to_named_pokemon_from_discard_onto_bench",
        description="Put up to N named Pokémon from discard onto bench.",
        pattern=re.compile(
            r"^Put up to (?P<count>\d+) .+? from your discard pile onto your Bench\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-up-to-named-pokemon-from-discard-onto-bench", ("count",)),
    ),
    TextTemplate(
        name="then_flip_coin",
        description="Then, flip a coin.",
        pattern=re.compile(r"^Then, flip a coin\.$", re.IGNORECASE),
        builder=_flip_coin_only,
    ),
    TextTemplate(
        name="attach_up_to_basic_energy_to_stage2",
        description="Attach up to N basic energy from discard to one stage 2 Pokémon.",
        pattern=re.compile(
            rf"^Attach up to (?P<count>\d+) Basic Energy cards from your discard pile to \d+ of your Stage \d+ {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-up-to-basic-energy-to-stage2", ("count",)),
    ),
    TextTemplate(
        name="card_use_gate_last_card_in_hand",
        description="Card can be used only when it is the last card in hand.",
        pattern=re.compile(r"^You can use this card only when it is the last card in your hand\.$", re.IGNORECASE),
        builder=_script_hook_builder("card-use-gate-last-card-in-hand"),
    ),
    TextTemplate(
        name="when_play_from_hand_evolve_may_generic",
        description="When played from hand to evolve, may use a generic effect.",
        pattern=re.compile(
            rf"^When you play this {_POKEMON_TOKEN} from your hand to evolve \d+ of your {_POKEMON_TOKEN} during your turn, you may .+\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("when-play-from-hand-evolve-may-generic"),
    ),
    TextTemplate(
        name="once_when_play_from_hand_evolve_may_generic",
        description="Once during turn when played from hand to evolve, may use a generic effect.",
        pattern=re.compile(
            rf"^Once during your turn, when you play this {_POKEMON_TOKEN} from your hand to evolve \d+ of your {_POKEMON_TOKEN}, .+\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-when-play-from-hand-evolve-may-generic"),
    ),
    TextTemplate(
        name="look_top_attach_any_energy_found",
        description="Look top cards and attach any number of energy cards found.",
        pattern=re.compile(
            rf"^Look at the top (?P<count>\d+) cards of your deck and attach any number of Energy cards you find there to your {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-attach-any-energy-found", ("count",)),
    ),
    TextTemplate(
        name="all_self_with_typed_energy_no_retreat",
        description="All your Pokémon with typed energy attached have no retreat cost.",
        pattern=re.compile(
            rf"^All of your {_POKEMON_TOKEN} that have \{{[A-Z]\}} Energy attached have no Retreat Cost\.$",
            re.IGNORECASE,
        ),
        builder=_all_self_basic_no_retreat,
    ),
    TextTemplate(
        name="each_player_with_tera_max_bench_and_discard_on_leave",
        description="Tera bench expansion with bench reduction when card leaves play.",
        pattern=re.compile(
            rf"^Each player who has any Tera {_POKEMON_TOKEN} in play can have up to (?P<count>\d+) {_POKEMON_TOKEN} on their Bench\. When this card leaves play, both players discard {_POKEMON_TOKEN} from their Bench until they have \d+, and the player who played this card discards first\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-player-with-tera-max-bench-and-discard-on-leave", ("count",)),
    ),
    TextTemplate(
        name="prevent_damage_effects_from_opponent_tera_to_self",
        description="Prevent all damage/effects from opponent tera Pokémon to this Pokémon.",
        pattern=re.compile(
            rf"^Prevent all damage from and effects of attacks from your opponent's Tera {_POKEMON_TOKEN} done to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-damage-effects-from-opponent-tera-to-self"),
    ),
    TextTemplate(
        name="self_basic_in_play_no_retreat_cost",
        description="Your basic Pokémon in play have no retreat cost.",
        pattern=re.compile(
            rf"^Your Basic {_POKEMON_TOKEN} in play have no Retreat Cost\.$",
            re.IGNORECASE,
        ),
        builder=_all_self_basic_no_retreat,
    ),
    TextTemplate(
        name="shuffle_those_pokemon_and_attached_into_opponent_deck",
        description="Shuffle those Pokémon and attached cards into opponent deck.",
        pattern=re.compile(
            rf"^Shuffle those {_POKEMON_TOKEN} and all attached cards into your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-those-pokemon-and-attached-into-opponent-deck"),
    ),
    TextTemplate(
        name="discard_a_card_from_hand",
        description="Discard a card from your hand.",
        pattern=re.compile(r"^Discard a card from your hand\.$", re.IGNORECASE),
        builder=_script_hook_builder("discard-a-card-from-hand"),
    ),
    TextTemplate(
        name="during_opponent_next_turn_no_weakness",
        description="During opponent next turn this Pokémon has no weakness.",
        pattern=re.compile(
            rf"^During your opponent's next turn, this {_POKEMON_TOKEN} has no Weakness\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-opponent-next-turn-no-weakness"),
    ),
    TextTemplate(
        name="as_long_as_active_can_evolve_first_turn_or_turn_played",
        description="As long as active this Pokémon can evolve on first or played turn.",
        pattern=re.compile(
            rf"^As long as this {_POKEMON_TOKEN} is in the Active Spot, it can evolve during your first turn or the turn you play it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("as-long-as-active-can-evolve-first-turn-or-turn-played"),
    ),
    TextTemplate(
        name="during_next_turn_cannot_retreat",
        description="During your next turn, this Pokémon cannot retreat.",
        pattern=re.compile(
            rf"^During your next turn, this {_POKEMON_TOKEN} can't retreat\.$",
            re.IGNORECASE,
        ),
        builder=_during_next_turn_cannot_retreat,
    ),
    TextTemplate(
        name="heal_fixed_damage_from_each_typed_self",
        description="Heal fixed damage from each of your typed Pokémon.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from each of your \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-fixed-damage-from-each-typed-self", ("amount",)),
    ),
    TextTemplate(
        name="opponent_next_turn_all_self_take_less_damage",
        description="During opponent next turn all your Pokémon take reduced damage.",
        pattern=re.compile(
            rf"^During your opponent's next turn, all of your {_POKEMON_TOKEN} take (?P<amount>\d+) less damage from attacks from your opponent's {_POKEMON_TOKEN} \(after applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-next-turn-all-self-take-less-damage", ("amount",)),
    ),
    TextTemplate(
        name="switch_in_opponent_benched_basic_to_active",
        description="Switch one opponent benched basic Pokémon to active spot.",
        pattern=re.compile(
            rf"^Switch in \d+ of your opponent's Benched Basic {_POKEMON_TOKEN} to the Active Spot\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("switch-in-opponent-benched-basic-to-active"),
    ),
    TextTemplate(
        name="devolve_each_opponent_evolved_shuffle_highest_stage",
        description="Devolve each opponent evolved Pokémon by shuffling highest stage.",
        pattern=re.compile(
            rf"^Devolve each of your opponent's evolved {_POKEMON_TOKEN} by shuffling the highest Stage Evolution card on it into your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("devolve-each-opponent-evolved-shuffle-highest-stage"),
    ),
    TextTemplate(
        name="prevent_damage_from_opponent_ex_to_self",
        description="Prevent all damage done to this Pokémon by opponent ex attacks.",
        pattern=re.compile(
            rf"^Prevent all damage done to this {_POKEMON_TOKEN} by attacks from your opponent's {_POKEMON_TOKEN} ex\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-damage-from-opponent-ex-to-self"),
    ),
    TextTemplate(
        name="discard_all_energy_and_take_prize",
        description="Discard all energy from this Pokémon and take a prize card.",
        pattern=re.compile(
            rf"^Discard all Energy from this {_POKEMON_TOKEN}, and take a Prize card\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-all-energy-and-take-prize"),
    ),
    TextTemplate(
        name="can_evolve_into_any_eevee_ex_from_hand",
        description="This Pokémon can evolve into any eevee evolution ex from hand.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} can evolve into any {_POKEMON_TOKEN} ex that evolves from Eevee if you play it from your hand onto this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("can-evolve-into-any-eevee-ex-from-hand"),
    ),
    TextTemplate(
        name="end_of_turn_if_hand_threshold_discard_hand",
        description="At end of turn, if hand size meets threshold, discard hand.",
        pattern=re.compile(
            r"^At the end of this turn, if you have (?P<count>\d+) or more cards in your hand, discard your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("end-of-turn-if-hand-threshold-discard-hand", ("count",)),
    ),
    TextTemplate(
        name="damage_more_per_self_benched",
        description="Damage bonus for each of your benched Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_self_benched,
    ),
    TextTemplate(
        name="parenthetical_this_includes_new_pokemon",
        description="Parenthetical reminder for newly entering Pokémon.",
        pattern=re.compile(
            rf"^\(This includes new {_POKEMON_TOKEN} that come into play\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="parenthetical_cant_evolve_first_or_turn_played",
        description="Parenthetical reminder that Pokémon cannot evolve first/played turn.",
        pattern=re.compile(
            rf"^\(This {_POKEMON_TOKEN} can't evolve during your first turn or the turn you play it\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="parenthetical_damage_from_attacks_still_taken",
        description="Parenthetical reminder that attack damage is still taken.",
        pattern=re.compile(
            r"^\(Damage from attacks is still taken\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="for_each_heads_choose_random_opponent_hand_card",
        description="For each heads, choose a random opponent hand card.",
        pattern=re.compile(
            r"^For each heads, choose a random card from your opponent's hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-heads-choose-random-opponent-hand-card"),
    ),
    TextTemplate(
        name="opponent_reveals_those_cards_and_shuffles_into_deck",
        description="Opponent reveals chosen cards and shuffles them into deck.",
        pattern=re.compile(
            r"^Your opponent reveals those cards and shuffles them into their deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-reveals-those-cards-shuffles-into-deck"),
    ),
    TextTemplate(
        name="look_top_n_put_m_into_hand",
        description="Look at top N cards and put M into hand.",
        pattern=re.compile(
            r"^Look at the top (?P<look>\d+) cards of your deck and put (?P<pick>\d+) of them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_once_look_top_pick_one,
    ),
    TextTemplate(
        name="discard_the_other_cards",
        description="Discard the other cards.",
        pattern=re.compile(r"^Discard the other cards\.$", re.IGNORECASE),
        builder=_script_hook_builder("discard-the-other-cards"),
    ),
    TextTemplate(
        name="put_counters_per_basic_typed_energy_in_discard",
        description="Put damage counters per basic typed energy in discard.",
        pattern=re.compile(
            rf"^Put (?P<count>\d+) damage counters on \d+ of your opponent's {_POKEMON_TOKEN} for each Basic \{{[A-Z]\}} Energy card in your discard pile\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-counters-per-basic-typed-energy-in-discard", ("count",)),
    ),
    TextTemplate(
        name="then_shuffle_those_energy_cards_into_deck",
        description="Then, shuffle those Energy cards into your deck.",
        pattern=re.compile(r"^Then, shuffle those Energy cards into your deck\.$", re.IGNORECASE),
        builder=_script_hook_builder("then-shuffle-those-energy-cards-into-deck"),
    ),
    TextTemplate(
        name="each_player_with_tera_can_have_up_to_bench",
        description="Each player with tera Pokémon in play can have increased bench size.",
        pattern=re.compile(
            rf"^Each player who has any Tera {_POKEMON_TOKEN} in play can have up to (?P<count>\d+) {_POKEMON_TOKEN} on their Bench\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-player-with-tera-can-have-up-to-bench", ("count",)),
    ),
    TextTemplate(
        name="when_card_leaves_play_bench_discard_until",
        description="When this card leaves play, discard from bench until threshold.",
        pattern=re.compile(
            rf"^When this card leaves play, both players discard {_POKEMON_TOKEN} from their Bench until they have (?P<count>\d+), and the player who played this card discards first\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("when-card-leaves-play-bench-discard-until", ("count",)),
    ),
    TextTemplate(
        name="look_top_card_of_deck",
        description="Look at the top card of your deck.",
        pattern=re.compile(r"^Look at the top card of your deck\.$", re.IGNORECASE),
        builder=_script_hook_builder("look-top-card-of-deck"),
    ),
    TextTemplate(
        name="you_may_discard_that_card",
        description="You may discard that card.",
        pattern=re.compile(r"^You may discard that card\.$", re.IGNORECASE),
        builder=_script_hook_builder("you-may-discard-that-card"),
    ),
    TextTemplate(
        name="damage_to_each_opponent_benched",
        description="Damage to each opponent benched Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage to each of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-to-each-opponent-benched", ("amount",)),
    ),
    TextTemplate(
        name="damage_for_each_heads_generic",
        description="Damage for each heads.",
        pattern=re.compile(r"^This attack does (?P<amount>\d+) damage for each heads\.$", re.IGNORECASE),
        builder=_script_hook_builder("damage-for-each-heads-generic", ("amount",)),
    ),
    TextTemplate(
        name="once_when_moves_bench_to_active_search_attach_energy",
        description="Once during turn when moving bench to active, search and attach energy.",
        pattern=re.compile(
            rf"^Once during your turn, when this {_POKEMON_TOKEN} moves from your Bench to the Active Spot, you may search your deck for up to (?P<count>\d+) Basic \{{[A-Z]\}} Energy cards and attach them to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-when-moves-bench-to-active-search-attach-energy", ("count",)),
    ),
    TextTemplate(
        name="move_n_energy_from_self_active_to_self_bench",
        description="Move N energy from this Pokémon to one benched Pokémon.",
        pattern=re.compile(
            rf"^Move (?P<count>\d+) Energy from this {_POKEMON_TOKEN} to \d+ of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_move_energy_from_self_active_to_self_bench,
    ),
    TextTemplate(
        name="discard_named_energy_from_self",
        description="Discard named energy from this Pokémon.",
        pattern=re.compile(
            rf"^Discard (?:a|\d+) .+? Energy from this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-named-energy-from-self"),
    ),
    TextTemplate(
        name="look_top_n_of_opponent_deck_reorder",
        description="Look at top N of opponent deck and reorder.",
        pattern=re.compile(
            r"^Look at the top (?P<count>\d+) cards of your opponent's deck and put them back in any order\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-n-opponent-deck-reorder", ("count",)),
    ),
    TextTemplate(
        name="reveal_top_n_opponent_choose_attack_shuffle_revealed",
        description="Reveal top N opponent deck, may choose attack, shuffle revealed cards back.",
        pattern=re.compile(
            rf"^Reveal the top (?P<count>\d+) cards of your opponent's deck\. You may choose an attack from a {_POKEMON_TOKEN} you find there and use it as this attack\. Shuffle the revealed cards into your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-top-n-opponent-choose-attack-shuffle-revealed", ("count",)),
    ),
    TextTemplate(
        name="attacks_used_by_your_pokemon_bonus_to_opponent_active",
        description="Attacks used by your Pokémon deal bonus to opponent active this turn.",
        pattern=re.compile(
            rf"^Attacks used by your {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_turn_damage_bonus_to_active,
    ),
    TextTemplate(
        name="you_may_search_deck_for_up_to_n_cards_to_hand",
        description="You may search deck for up to N cards and put them into your hand.",
        pattern=re.compile(
            r"^You may search your deck for up to (?P<count>\d+) cards and put them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_search_any_cards_to_hand,
    ),
    TextTemplate(
        name="attack_also_bench_damage_per_prize_taken",
        description="Attack also damages opponent bench per prizes taken.",
        pattern=re.compile(
            rf"^This attack also does (?P<amount>\d+) damage to each of your opponent's Benched {_POKEMON_TOKEN} for each Prize card your opponent has taken\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-also-bench-damage-per-prize-taken", ("amount",)),
    ),
    TextTemplate(
        name="during_next_turn_named_attack_bonus_damage",
        description="During next turn, named attack does bonus damage.",
        pattern=re.compile(
            rf"^During your next turn, this {_POKEMON_TOKEN}'s .+? attack does (?P<amount>\d+) more damage \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-next-turn-named-attack-bonus-damage", ("amount",)),
    ),
    TextTemplate(
        name="attack_also_damage_benched_with_damage_counters",
        description="Attack also damages one benched opponent Pokémon that has counters.",
        pattern=re.compile(
            rf"^This attack also does (?P<amount>\d+) damage to \d+ of your opponent's Benched {_POKEMON_TOKEN} that has any damage counters on it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-also-damage-benched-with-damage-counters", ("amount",)),
    ),
    TextTemplate(
        name="move_up_to_energy_bench_to_active",
        description="Move up to N energy from your benched Pokémon to active Pokémon.",
        pattern=re.compile(
            rf"^Move up to (?P<count>\d+) Energy from your Benched {_POKEMON_TOKEN} to your Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("move-up-to-energy-bench-to-active", ("count",)),
    ),
    TextTemplate(
        name="damage_for_each_trainer_card_find_there",
        description="Damage for each Trainer card found there.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each Trainer card you find there\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-for-each-trainer-card-find-there", ("amount",)),
    ),
    TextTemplate(
        name="flip_coin_for_each_energy_attached_to_self",
        description="Flip a coin for each energy attached to this Pokémon.",
        pattern=re.compile(
            rf"^Flip a coin for each Energy attached to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("flip-coin-for-each-energy-attached-to-self"),
    ),
    TextTemplate(
        name="reveal_top_n_opponent_deck_full_combo",
        description="Reveal top opponent deck cards, may copy attack, then shuffle revealed cards.",
        pattern=re.compile(
            rf"^Reveal the top (?P<count>\d+) cards of your opponent's deck\. You may choose an attack from a {_POKEMON_TOKEN} you find there and use it as this attack\. Shuffle the revealed cards into your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-top-n-opponent-deck-full-combo", ("count",)),
    ),
    TextTemplate(
        name="reveal_top_n_opponent_deck",
        description="Reveal top N cards of opponent deck.",
        pattern=re.compile(
            r"^Reveal the top (?P<count>\d+) cards of your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-top-n-opponent-deck", ("count",)),
    ),
    TextTemplate(
        name="shuffle_revealed_cards_into_opponent_deck",
        description="Shuffle revealed cards into opponent deck.",
        pattern=re.compile(
            r"^Shuffle the revealed cards into your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-revealed-cards-into-opponent-deck"),
    ),
    TextTemplate(
        name="each_basic_typed_energy_on_all_self_provides_double",
        description="Each basic typed energy on your Pokémon provides double typed energy.",
        pattern=re.compile(
            rf"^Each Basic \{{[A-Z]\}} Energy attached to all of your {_POKEMON_TOKEN} provides \{{[A-Z]\}}\{{[A-Z]\}} Energy\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-basic-typed-energy-on-all-self-provides-double"),
    ),
    TextTemplate(
        name="discard_top_n_and_damage_per_basic_typed_energy_discarded",
        description="Discard top cards then damage per typed basic energy discarded.",
        pattern=re.compile(
            rf"^Discard the top (?P<count>\d+) cards of your deck, and this attack does (?P<amount>\d+) damage for each Basic \{{[A-Z]\}} Energy card that you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-top-n-and-damage-per-basic-typed-energy-discarded", ("count", "amount")),
    ),
    TextTemplate(
        name="once_when_moves_active_to_bench_may_use_ability",
        description="Once during turn when this Pokémon moves active to bench, may use ability.",
        pattern=re.compile(
            rf"^Once during your turn, when this {_POKEMON_TOKEN} moves from the Active Spot to your Bench, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-when-moves-active-to-bench-may-use-ability"),
    ),
    TextTemplate(
        name="you_may_discard_all_energy_for_bonus_damage",
        description="You may discard all energy from this Pokémon for bonus damage.",
        pattern=re.compile(
            rf"^You may discard all Energy from this {_POKEMON_TOKEN} and have this attack do (?P<amount>\d+) more damage\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("you-may-discard-all-energy-for-bonus-damage", ("amount",)),
    ),
    TextTemplate(
        name="attacks_used_by_typed_pokemon_bonus_to_opponent_active",
        description="Attacks used by your typed Pokémon deal bonus to opponent active.",
        pattern=re.compile(
            rf"^Attacks used by your \{{[A-Z]\}} {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_turn_damage_bonus_to_active,
    ),
    TextTemplate(
        name="active_now_affected_by_that_special_condition",
        description="Opponent active is now affected by that special condition.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now affected by that Special Condition\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("active-now-affected-by-that-special-condition"),
    ),
    TextTemplate(
        name="status_burned_and_poisoned",
        description="Apply both Burned and Poisoned to opponent active.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now Burned and Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_status_burned_and_poisoned,
    ),
    TextTemplate(
        name="status_paralyzed_and_poisoned",
        description="Apply both Paralyzed and Poisoned to opponent active.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now Paralyzed and Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_status_paralyzed_and_poisoned,
    ),
    TextTemplate(
        name="typed_pokemon_in_play_have_no_abilities",
        description="Typed Pokémon in play (both players) have no abilities.",
        pattern=re.compile(
            rf"^\{{[A-Z]\}} {_POKEMON_TOKEN} in play \(both yours and your opponent's\) have no Abilities\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("typed-pokemon-in-play-have-no-abilities"),
    ),
    TextTemplate(
        name="card_can_only_attach_to_named_pokemon",
        description="This card can only be attached to named Pokémon.",
        pattern=re.compile(
            rf"^This card can only be attached to .+? {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("card-can-only-attach-to-named-pokemon"),
    ),
    TextTemplate(
        name="shuffle_up_to_basic_energy_from_discard_into_deck",
        description="Shuffle up to N basic energy from discard into deck.",
        pattern=re.compile(
            r"^Shuffle up to (?P<count>\d+) Basic Energy cards from your discard pile into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-up-to-basic-energy-from-discard-into-deck", ("count",)),
    ),
    TextTemplate(
        name="shuffle_up_to_pokemon_from_discard_into_deck",
        description="Shuffle up to N Pokémon from discard into deck.",
        pattern=re.compile(
            rf"^Shuffle up to (?P<count>\d+) {_POKEMON_TOKEN} from your discard pile into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-up-to-pokemon-from-discard-into-deck", ("count",)),
    ),
    TextTemplate(
        name="damage_per_self_prize_taken_base",
        description="Damage for each prize card you have taken.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each Prize card you have taken\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-per-self-prize-taken-base", ("amount",)),
    ),
    TextTemplate(
        name="switch_card_from_hand_with_top_of_deck",
        description="Switch a card from hand with top of deck.",
        pattern=re.compile(
            r"^Switch a card from your hand with the top card of your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("switch-card-from-hand-with-top-of-deck"),
    ),
    TextTemplate(
        name="choose_self_basic_pokemon_in_play",
        description="Choose one of your basic Pokémon in play.",
        pattern=re.compile(
            rf"^Choose \d+ of your Basic {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-self-basic-pokemon-in-play"),
    ),
    TextTemplate(
        name="cannot_use_card_first_turn_or_new_basic",
        description="Cannot use this card on first turn or new basic put into play this turn.",
        pattern=re.compile(
            rf"^You can't use this card during your first turn or on a Basic {_POKEMON_TOKEN} that was put into play this turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("cannot-use-card-first-turn-or-new-basic"),
    ),
    TextTemplate(
        name="once_each_players_turn_may_switch_typed_active",
        description="Once during each player's turn, may switch typed active with typed benched.",
        pattern=re.compile(
            rf"^Once during each player's turn, that player may switch their Active \{{[A-Z]\}} {_POKEMON_TOKEN} with \d+ of their Benched \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-each-players-turn-may-switch-typed-active"),
    ),
    TextTemplate(
        name="discard_n_basic_typed_energy_from_hand",
        description="Discard N basic typed energy cards from your hand.",
        pattern=re.compile(
            r"^Discard (?P<count>\d+) Basic \{[A-Z]\} Energy cards from your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-n-basic-typed-energy-from-hand", ("count",)),
    ),
    TextTemplate(
        name="self_takes_less_damage_from_opponent_two_types",
        description="This Pokémon takes less damage from opponent typed Pokémon attacks.",
        pattern=re.compile(
            rf"^This {_POKEMON_TOKEN} takes (?P<amount>\d+) less damage from attacks from your opponent's \{{[A-Z]\}} or \{{[A-Z]\}} {_POKEMON_TOKEN} \(after applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("self-takes-less-damage-from-opponent-two-types", ("amount",)),
    ),
    TextTemplate(
        name="heal_fixed_damage_from_benched_typed",
        description="Heal fixed damage from one of your benched typed Pokémon.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from \d+ of your Benched \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-fixed-damage-from-benched-typed", ("amount",)),
    ),
    TextTemplate(
        name="discard_n_energy_damage_each_of_n_opponent_pokemon",
        description="Discard N energy then deal damage to each of N opponent Pokémon.",
        pattern=re.compile(
            rf"^Discard (?P<count>\d+) Energy from this {_POKEMON_TOKEN}, and this attack does (?P<amount>\d+) damage to each of (?P<targets>\d+) of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-n-energy-damage-each-of-n-opponent-pokemon", ("count", "amount", "targets")),
    ),
    TextTemplate(
        name="prevent_damage_counters_on_bench_from_opponent_effects",
        description="Prevent damage counters on benched Pokémon from opponent attack/ability effects.",
        pattern=re.compile(
            rf"^Prevent all damage counters from being placed on Benched {_POKEMON_TOKEN} \(both yours and your opponent's\) by effects of attacks and Abilities from the opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-damage-counters-on-bench-from-opponent-effects"),
    ),
    TextTemplate(
        name="discard_tool_or_special_energy_or_stadium",
        description="Discard a tool/special energy from opponent Pokémon or discard stadium in play.",
        pattern=re.compile(
            rf"^Discard a {_POKEMON_TOKEN} Tool or Special Energy card from \d+ of your opponent's {_POKEMON_TOKEN}, or discard a Stadium in play\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-tool-or-special-energy-or-stadium"),
    ),
    TextTemplate(
        name="look_top_n_put_typed_on_bench_then_shuffle_bottom_and_first_turn_gate",
        description="Look top cards, bench typed Pokémon, move others to bottom, plus first-turn gate.",
        pattern=re.compile(
            rf"^Look at the top (?P<count>\d+) cards of your deck and put a \{{[A-Z]\}} {_POKEMON_TOKEN} you find there onto your Bench\. Shuffle the other cards and put them on the bottom of your deck\. You can't use this card during your first turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-n-put-typed-on-bench-then-shuffle-bottom-and-first-turn-gate", ("count",)),
    ),
    TextTemplate(
        name="heal_fixed_damage_from_active_with_min_energy",
        description="Heal fixed damage from active Pokémon with minimum attached energy.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from your Active {_POKEMON_TOKEN} that has (?P<count>\d+) or more Energy attached\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-fixed-damage-from-active-with-min-energy", ("amount", "count")),
    ),
    TextTemplate(
        name="attached_pokemon_takes_less_from_opponent_with_ability",
        description="Attached Pokémon takes less damage from opponent Pokémon with an ability.",
        pattern=re.compile(
            rf"^The {_POKEMON_TOKEN} this card is attached to takes (?P<amount>\d+) less damage from attacks from your opponent's {_POKEMON_TOKEN} that have an Ability \(after applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attached-pokemon-takes-less-from-opponent-with-ability", ("amount",)),
    ),
    TextTemplate(
        name="opponent_reveals_hand_damage_per_energy_found",
        description="Opponent reveals hand and attack damage scales with energy cards found.",
        pattern=re.compile(
            r"^Your opponent reveals their hand, and this attack does (?P<amount>\d+) damage for each Energy card you find there\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-reveals-hand-damage-per-energy-found", ("amount",)),
    ),
    TextTemplate(
        name="attack_also_damages_each_opponent_bench",
        description="Attack also damages each opponent benched Pokémon.",
        pattern=re.compile(
            rf"^This attack also does (?P<amount>\d+) damage to each of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-also-damages-each-opponent-bench", ("amount",)),
    ),
    TextTemplate(
        name="whenever_opponent_active_moves_to_bench_place_counters",
        description="Whenever opponent active moves to bench, place damage counters on that Pokémon.",
        pattern=re.compile(
            rf"^Whenever your opponent's Active {_POKEMON_TOKEN} moves to the Bench during their turn, place (?P<count>\d+) damage counters on that {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("whenever-opponent-active-moves-to-bench-place-counters", ("count",)),
    ),
    TextTemplate(
        name="damage_per_energy_attached_to_all_opponent_pokemon",
        description="Damage for each energy attached to all of opponent's Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each Energy attached to all of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-per-energy-attached-to-all-opponent-pokemon", ("amount",)),
    ),
    TextTemplate(
        name="discard_n_energy_and_bench_damage",
        description="Discard N energy and also deal damage to one opponent benched Pokémon.",
        pattern=re.compile(
            rf"^Discard (?P<count>\d+) Energy from this {_POKEMON_TOKEN}, and this attack also does (?P<amount>\d+) damage to \d+ of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-n-energy-and-bench-damage", ("count", "amount")),
    ),
    TextTemplate(
        name="for_each_heads_search_attach_basic_energy_any_way",
        description="For each heads, search and attach up to N basic energy cards in any way.",
        pattern=re.compile(
            rf"^For each heads, search your deck for up to (?P<count>\d+) Basic Energy cards and attach them to your {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-heads-search-attach-basic-energy-any-way", ("count",)),
    ),
    TextTemplate(
        name="during_turn_if_ko_by_named_take_more_prize",
        description="During this turn, if opponent active is KOed by named Pokémon attack, take more prizes.",
        pattern=re.compile(
            rf"^During this turn, if your opponent's Active {_POKEMON_TOKEN} is Knocked Out by damage from an attack used by your .+? {_POKEMON_TOKEN}, take (?P<count>\d+) more Prize cards?\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-turn-if-ko-by-named-take-more-prize", ("count",)),
    ),
    TextTemplate(
        name="once_each_players_turn_if_played_named_supporter_may_draw",
        description="Once during each player's turn, if they played named supporter, they may draw cards.",
        pattern=re.compile(
            r"^Once during each player's turn, if they played a Supporter card that has \".+?\" in its name from their hand this turn, they may draw (?P<count>\d+) cards\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-each-players-turn-if-played-named-supporter-may-draw", ("count",)),
    ),
    TextTemplate(
        name="look_top_n_put_typed_on_bench_then_shuffle_other_bottom",
        description="Look top cards, bench typed Pokémon, then shuffle remaining cards to bottom.",
        pattern=re.compile(
            rf"^Look at the top (?P<count>\d+) cards of your deck and put a \{{[A-Z]\}} {_POKEMON_TOKEN} you find there onto your Bench\. Shuffle the other cards and put them on the bottom of your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("look-top-n-put-typed-on-bench-then-shuffle-other-bottom", ("count",)),
    ),
    TextTemplate(
        name="cannot_use_card_during_first_turn",
        description="Cannot use this card during your first turn.",
        pattern=re.compile(r"^You can't use this card during your first turn\.$", re.IGNORECASE),
        builder=_script_hook_builder("cannot-use-card-during-first-turn"),
    ),
    TextTemplate(
        name="all_self_with_any_typed_energy_take_less_damage",
        description="All your Pokémon with any typed energy attached take less damage from opponent attacks.",
        pattern=re.compile(
            rf"^All of your {_POKEMON_TOKEN} that have any \{{[A-Z]\}} Energy attached take (?P<amount>\d+) less damage from attacks from your opponent's {_POKEMON_TOKEN} \(after applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("all-self-with-any-typed-energy-take-less-damage", ("amount",)),
    ),
    TextTemplate(
        name="choose_basic_typed_energy_from_discard_up_to_opponent_energy_attach_to_typed",
        description="Choose typed basic energy from discard up to opponent total energy and attach to typed Pokémon.",
        pattern=re.compile(
            rf"^Choose Basic \{{[A-Z]\}} Energy cards from your discard pile up to the amount of Energy attached to all of your opponent's {_POKEMON_TOKEN} and attach them to your \{{[A-Z]\}} {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-basic-typed-energy-up-to-opponent-energy-attach-to-typed"),
    ),
    TextTemplate(
        name="knock_out_each_opponent_pokemon_below_hp",
        description="Knock out each opponent Pokémon at or below HP threshold.",
        pattern=re.compile(
            rf"^Knock Out each of your opponent's {_POKEMON_TOKEN} that has (?P<hp>\d+) HP or less remaining\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("knock-out-each-opponent-pokemon-below-hp", ("hp",)),
    ),
    TextTemplate(
        name="shuffle_all_energy_self_into_deck_and_damage_opponent_any",
        description="Shuffle all self energy into deck, then deal damage to one opponent Pokémon.",
        pattern=re.compile(
            rf"^Shuffle all Energy attached to this {_POKEMON_TOKEN} into your deck, and this attack does (?P<amount>\d+) damage to \d+ of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-all-energy-self-into-deck-and-damage-opponent-any", ("amount",)),
    ),
    TextTemplate(
        name="attack_damage_per_damage_counter_on_named_self_bench",
        description="Attack damage scales with damage counters on named benched Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each damage counter on all of your Benched .+?(?: {_POKEMON_TOKEN})?\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-per-damage-counter-on-named-self-bench", ("amount",)),
    ),
    TextTemplate(
        name="once_each_players_turn_may_search_basic_to_bench_then_shuffle",
        description="Once each player's turn, may search basic to bench then shuffle.",
        pattern=re.compile(
            rf"^Once during each player's turn, that player may search their deck for a Basic {_POKEMON_TOKEN} and put it onto their Bench\. Then, that player shuffles their deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-each-players-turn-may-search-basic-to-bench-then-shuffle"),
    ),
    TextTemplate(
        name="once_each_players_turn_may_search_basic_to_bench",
        description="Once each player's turn, may search basic to bench.",
        pattern=re.compile(
            rf"^Once during each player's turn, that player may search their deck for a Basic {_POKEMON_TOKEN} and put it onto their Bench\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-each-players-turn-may-search-basic-to-bench"),
    ),
    TextTemplate(
        name="then_that_player_shuffles_their_deck",
        description="Then, that player shuffles their deck.",
        pattern=re.compile(r"^Then, that player shuffles their deck\.$", re.IGNORECASE),
        builder=_script_hook_builder("then-that-player-shuffles-their-deck"),
    ),
    TextTemplate(
        name="before_drawing_you_may_discard_any_number_from_hand",
        description="Before drawing, you may discard any number of cards from hand.",
        pattern=re.compile(
            r"^Before drawing cards, you may discard any number of cards from your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("before-drawing-you-may-discard-any-number-from-hand"),
    ),
    TextTemplate(
        name="put_up_to_n_combination_typed_pokemon_and_basic_energy_from_discard_to_hand",
        description="Put up to N in any combination of typed Pokémon and basic typed energies from discard to hand.",
        pattern=re.compile(
            rf"^Put up to (?P<count>\d+) in any combination of \{{[A-Z]\}} {_POKEMON_TOKEN} and Basic \{{[A-Z]\}} Energy cards from your discard pile into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_put_up_to_cards_from_discard_to_hand,
    ),
    TextTemplate(
        name="attack_damage_for_each_named_self_in_play",
        description="Attack damage scales with named self Pokémon in play.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each of your .+? in play\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-for-each-named-self-in-play", ("amount",)),
    ),
    TextTemplate(
        name="attack_more_damage_for_each_damage_counter_on_all_opponent_pokemon",
        description="Attack bonus damage for each damage counter on all opponent Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each damage counter on all of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-more-damage-for-each-damage-counter-on-all-opponent-pokemon", ("amount",)),
    ),
    TextTemplate(
        name="attack_more_damage_for_each_benched_self_with_damage_counter",
        description="Attack bonus damage for each benched self Pokémon with damage counters.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each of your Benched {_POKEMON_TOKEN} that has any damage counters on it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-more-damage-for-each-benched-self-with-damage-counter", ("amount",)),
    ),
    TextTemplate(
        name="during_next_turn_attacks_used_by_this_bonus_to_opponent_active",
        description="During your next turn, attacks used by this Pokémon gain bonus damage to opponent active.",
        pattern=re.compile(
            rf"^During your next turn, attacks used by this {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_turn_damage_bonus_to_active,
    ),
    TextTemplate(
        name="search_any_card_shuffle_then_put_on_top",
        description="Search your deck for a card, shuffle deck, then put that card on top.",
        pattern=re.compile(
            r"^Search your deck for a card\. Shuffle your deck, then put that card on top of it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-any-card-shuffle-then-put-on-top"),
    ),
    TextTemplate(
        name="search_any_card_only",
        description="Search your deck for a card.",
        pattern=re.compile(r"^Search your deck for a card\.$", re.IGNORECASE),
        builder=_script_hook_builder("search-any-card-only"),
    ),
    TextTemplate(
        name="shuffle_deck_then_put_that_card_on_top",
        description="Shuffle your deck, then put that card on top.",
        pattern=re.compile(r"^Shuffle your deck, then put that card on top of it\.$", re.IGNORECASE),
        builder=_script_hook_builder("shuffle-deck-then-put-that-card-on-top"),
    ),
    TextTemplate(
        name="once_when_moves_bench_to_active_may_use_ability",
        description="Once during your turn when this Pokémon moves bench to active, may use ability.",
        pattern=re.compile(
            rf"^Once during your turn, when this {_POKEMON_TOKEN} moves from your Bench to the Active Spot, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-when-moves-bench-to-active-may-use-ability"),
    ),
    TextTemplate(
        name="move_any_amount_typed_energy_from_other_to_self",
        description="Move any amount of typed energy from your other Pokémon to this Pokémon.",
        pattern=re.compile(
            rf"^Move any amount of \{{[A-Z]\}} Energy from your other {_POKEMON_TOKEN} to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("move-any-amount-typed-energy-from-other-to-self"),
    ),
    TextTemplate(
        name="choose_opponent_pokemon_flip_per_named_self_in_play_damage_per_heads",
        description="Choose opponent Pokémon, flip per named self in play, deal damage per heads.",
        pattern=re.compile(
            rf'^Choose \d+ of your opponent\'s {_POKEMON_TOKEN} and flip a coin for each of your {_POKEMON_TOKEN} in play that has ".+?" in its name\. This attack does (?P<amount>\d+) damage to the chosen {_POKEMON_TOKEN} for each heads\.$',
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-opponent-pokemon-flip-per-named-self-in-play-damage-per-heads", ("amount",)),
    ),
    TextTemplate(
        name="for_each_heads_choose_card_and_shuffle_into_opponent_deck",
        description="For each heads choose a card and shuffle it into opponent deck.",
        pattern=re.compile(
            r"^For each heads, choose a card you find there and shuffle it into your opponent's deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("for-each-heads-choose-card-and-shuffle-into-opponent-deck"),
    ),
    TextTemplate(
        name="opponent_reveals_hand_you_draw_per_pokemon_found",
        description="Opponent reveals hand and you draw per Pokémon found.",
        pattern=re.compile(
            rf"^Your opponent reveals their hand, and you draw a card for each {_POKEMON_TOKEN} you find there\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-reveals-hand-you-draw-per-pokemon-found"),
    ),
    TextTemplate(
        name="attach_up_to_basic_typed_energy_from_discard_to_typed_pokemon",
        description="Attach up to N basic typed energy from discard to one of your typed Pokémon.",
        pattern=re.compile(
            rf"^Attach up to (?P<count>\d+) Basic \{{[A-Z]\}} Energy cards from your discard pile to \d+ of your \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-up-to-basic-typed-energy-from-discard-to-typed-pokemon", ("count",)),
    ),
    TextTemplate(
        name="once_each_players_turn_may_discard_n_to_draw",
        description="Once each player's turn, may discard N cards from hand to draw a card.",
        pattern=re.compile(
            r"^Once during each player's turn, that player may discard (?P<count>\d+) cards from their hand in order to draw a card\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-each-players-turn-may-discard-n-to-draw", ("count",)),
    ),
    TextTemplate(
        name="put_up_to_basic_energy_from_discard_into_hand",
        description="Put up to N basic energy cards from discard into hand.",
        pattern=re.compile(
            r"^Put up to (?P<count>\d+) Basic Energy cards from your discard pile into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_put_up_to_cards_from_discard_to_hand,
    ),
    TextTemplate(
        name="pokemon_in_play_lose_all_abilities_require_knockout",
        description="Pokémon in play lose abilities requiring those Pokémon to be knocked out.",
        pattern=re.compile(
            rf"^{_POKEMON_TOKEN} in play \(both yours and your opponent's\) lose all Abilities that require those {_POKEMON_TOKEN} to be Knocked Out\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("pokemon-in-play-lose-all-abilities-require-knockout"),
    ),
    TextTemplate(
        name="discard_any_amount_bracket_energy_and_damage_per_discarded",
        description="Discard any amount of bracket-typed energy from your Pokémon and deal damage per discarded card.",
        pattern=re.compile(
            rf"^Discard any amount of \[[A-Z]\] Energy from among your {_POKEMON_TOKEN}, and this attack does (?P<amount>\d+) damage for each card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_discard_any_amount_energy_and_damage,
    ),
    TextTemplate(
        name="attack_damage_for_each_typed_self_in_play",
        description="Attack damage for each of your typed Pokémon in play.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your \{{[A-Z]\}} {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_damage_for_each_self_pokemon_in_play,
    ),
    TextTemplate(
        name="attacks_used_by_this_cost_less_per_opponent_bench",
        description="Attacks used by this Pokémon cost less per opponent benched Pokémon.",
        pattern=re.compile(
            rf"^Attacks used by this {_POKEMON_TOKEN} cost \{{[A-Z]\}} less for each of your opponent's Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attacks-used-by-this-cost-less-per-opponent-bench"),
    ),
    TextTemplate(
        name="discard_up_to_hand_energy_then_damage_per_discarded_to_opponent_any",
        description="Discard up to N energy from hand then damage one opponent Pokémon per discarded card.",
        pattern=re.compile(
            rf"^Discard up to (?P<count>\d+) Energy cards from your hand\. This attack does (?P<amount>\d+) damage to \d+ of your opponent's {_POKEMON_TOKEN} for each Energy card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-up-to-hand-energy-then-damage-per-discarded-to-opponent-any", ("count", "amount")),
    ),
    TextTemplate(
        name="reveal_top_n_damage_per_named_card_then_discard_named_shuffle_rest",
        description="Reveal top cards, damage per named card, discard named cards, shuffle rest.",
        pattern=re.compile(
            r"^Reveal the top (?P<count>\d+) cards of your deck\. This attack does (?P<amount>\d+) damage for each .+? card you find there\. Then, discard those .+? cards and shuffle the other cards back into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-top-n-damage-per-named-card-then-discard-named-shuffle-rest", ("count", "amount")),
    ),
    TextTemplate(
        name="attack_more_damage_per_damage_counter_on_opponent_active",
        description="Attack bonus damage per damage counter on opponent active.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each damage counter on your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_opponent_damage_counter,
    ),
    TextTemplate(
        name="each_evolved_can_use_previous_evolution_attacks",
        description="Each evolved Pokémon can use attacks from previous evolutions.",
        pattern=re.compile(
            rf"^Each of your evolved {_POKEMON_TOKEN} can use any attack from its previous Evolutions\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-evolved-can-use-previous-evolution-attacks"),
    ),
    TextTemplate(
        name="attach_basic_typed_from_discard_to_each_self_bench",
        description="Attach a basic typed energy from discard to each of your benched Pokémon.",
        pattern=re.compile(
            rf"^Attach a Basic \{{[A-Z]\}} Energy card from your discard pile to each of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-basic-typed-from-discard-to-each-self-bench"),
    ),
    TextTemplate(
        name="status_burned_confused_and_poisoned",
        description="Apply Burned, Confused, and Poisoned to opponent active.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now Burned, Confused, and Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_status_burned_confused_and_poisoned,
    ),
    TextTemplate(
        name="whenever_opponent_attaches_energy_from_hand_place_counters",
        description="Whenever opponent attaches energy from hand, place damage counters on that Pokémon.",
        pattern=re.compile(
            rf"^Whenever your opponent attaches an Energy card from their hand to \d+ of their {_POKEMON_TOKEN}, put (?P<count>\d+) damage counters on that {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("whenever-opponent-attaches-energy-from-hand-place-counters", ("count",)),
    ),
    TextTemplate(
        name="prevent_damage_from_opponent_basic_ex_to_self",
        description="Prevent all damage to this Pokémon from opponent Basic Pokémon ex attacks.",
        pattern=re.compile(
            rf"^Prevent all damage done to this {_POKEMON_TOKEN} by attacks from your opponent's Basic {_POKEMON_TOKEN} ex\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-damage-from-opponent-basic-ex-to-self"),
    ),
    TextTemplate(
        name="attack_more_damage_per_ancient_card_in_discard",
        description="Attack bonus damage per Ancient card in discard pile.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) more damage for each Ancient card in your discard pile\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-more-damage-per-ancient-card-in-discard", ("amount",)),
    ),
    TextTemplate(
        name="attack_damage_to_new_active",
        description="Attack deals damage to the new active Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage to the new Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-to-new-active", ("amount",)),
    ),
    TextTemplate(
        name="shuffle_other_cards_put_bottom",
        description="Shuffle the other cards and put them on the bottom of your deck.",
        pattern=re.compile(
            r"^Shuffle the other cards and put them on the bottom of your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-other-cards-put-bottom"),
    ),
    TextTemplate(
        name="attack_damage_for_each_ancient_self_in_play",
        description="Attack damage for each Ancient Pokémon you have in play.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your Ancient {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-for-each-ancient-self-in-play", ("amount",)),
    ),
    TextTemplate(
        name="put_up_to_basic_pokemon_found_onto_opponent_bench",
        description="Put up to N basic Pokémon found there onto opponent bench.",
        pattern=re.compile(
            rf"^Put up to (?P<count>\d+) Basic {_POKEMON_TOKEN} you find there onto your opponent's Bench\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-up-to-basic-pokemon-found-onto-opponent-bench", ("count",)),
    ),
    TextTemplate(
        name="discard_up_to_n_tools_from_opponent_pokemon",
        description="Discard up to N tools from opponent Pokémon.",
        pattern=re.compile(
            rf"^Discard up to (?P<count>\d+) {_POKEMON_TOKEN} Tools from your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-up-to-n-tools-from-opponent-pokemon", ("count",)),
    ),
    TextTemplate(
        name="attack_damage_per_special_energy_attached_to_self",
        description="Attack damage for each special energy attached to this Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each Special Energy card attached to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-per-special-energy-attached-to-self", ("amount",)),
    ),
    TextTemplate(
        name="attached_pokemon_attacks_bonus_vs_active_ex",
        description="Attached Pokémon attacks do bonus damage to opponent active ex.",
        pattern=re.compile(
            rf"^Attacks used by the {_POKEMON_TOKEN} this card is attached to do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} ex \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attached-pokemon-attacks-bonus-vs-active-ex", ("amount",)),
    ),
    TextTemplate(
        name="end_opponents_next_turn_defending_knocked_out",
        description="At the end of opponent next turn the defending Pokémon is knocked out.",
        pattern=re.compile(
            rf"^At the end of your opponent's next turn, the Defending {_POKEMON_TOKEN} will be Knocked Out\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("end-opponents-next-turn-defending-knocked-out"),
    ),
    TextTemplate(
        name="attack_damage_per_typed_energy_on_all_opponent_pokemon",
        description="Attack damage per typed energy attached to all opponent Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each \{{[A-Z]\}} Energy attached to all of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-per-typed-energy-on-all-opponent-pokemon", ("amount",)),
    ),
    TextTemplate(
        name="put_up_to_n_pokemon_from_discard_into_hand",
        description="Put up to N Pokémon from discard pile into hand.",
        pattern=re.compile(
            rf"^Put up to (?P<count>\d+) {_POKEMON_TOKEN} from your discard pile into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_put_up_to_cards_from_discard_to_hand,
    ),
    TextTemplate(
        name="discard_top_each_player_deck_damage_more_per_energy_discarded",
        description="Discard top card of each player's deck and gain bonus damage per energy discarded.",
        pattern=re.compile(
            r"^Discard the top card of each player's deck\. This attack does (?P<amount>\d+) more damage for each Energy card discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-top-each-player-deck-damage-more-per-energy-discarded", ("amount",)),
    ),
    TextTemplate(
        name="discard_a_card_you_find_there",
        description="Discard a card you find there.",
        pattern=re.compile(r"^Discard a card you find there\.$", re.IGNORECASE),
        builder=_script_hook_builder("discard-a-card-you-find-there"),
    ),
    TextTemplate(
        name="shuffle_one_self_bench_and_attached_into_deck",
        description="Shuffle one of your benched Pokémon and attached cards into deck.",
        pattern=re.compile(
            rf"^Shuffle \d+ of your Benched {_POKEMON_TOKEN} and all attached cards into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("shuffle-one-self-bench-and-attached-into-deck"),
    ),
    TextTemplate(
        name="attack_use_gate_go_second_first_turn_supporter_lock",
        description="Attack use gate for go-second first turn with opponent supporter lock.",
        pattern=re.compile(
            r"^You can use this attack only if you go second, and only during your first turn\. Your opponent can't play any Supporter cards from their hand during their next turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-use-gate-go-second-first-turn-supporter-lock"),
    ),
    TextTemplate(
        name="attach_basic_energy_from_hand_to_one_self_pokemon",
        description="Attach a basic energy card from hand to one of your Pokémon.",
        pattern=re.compile(
            rf"^Attach a Basic Energy card from your hand to \d+ of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-basic-energy-from-hand-to-one-self-pokemon"),
    ),
    TextTemplate(
        name="discard_special_energy_from_one_opponent_pokemon",
        description="Discard a special energy from one of opponent Pokémon.",
        pattern=re.compile(
            rf"^Discard a Special Energy from \d+ of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-special-energy-from-one-opponent-pokemon"),
    ),
    TextTemplate(
        name="each_pokemon_with_any_energy_recovers_and_cannot_be_affected_by_special_conditions",
        description="Each Pokémon with any energy recovers and cannot be affected by special conditions.",
        pattern=re.compile(
            rf"^Each {_POKEMON_TOKEN} that has any Energy attached \(both yours and your opponent's\) recovers from all Special Conditions and can't be affected by any Special Conditions\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-pokemon-with-any-energy-recovers-and-cannot-be-affected-by-special-conditions"),
    ),
    TextTemplate(
        name="look_top_n_put_up_to_m_into_hand",
        description="Look at top N cards of deck and put up to M into hand.",
        pattern=re.compile(
            r"^Look at the top (?P<look>\d+) cards of your deck and put up to (?P<pick>\d+) of them into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_once_look_top_pick_one,
    ),
    TextTemplate(
        name="each_player_shuffle_hand_put_bottom",
        description="Each player shuffles their hand and puts it on the bottom of their deck.",
        pattern=re.compile(
            r"^Each player shuffles their hand and puts it on the bottom of their deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-player-shuffle-hand-put-bottom"),
    ),
    TextTemplate(
        name="choose_named_ex_from_discard_switch_with_named_ex_in_play_keep_state",
        description="Choose named ex in discard and switch with named ex in play while preserving state.",
        pattern=re.compile(
            rf'^Choose a {_POKEMON_TOKEN} ex in your discard pile that has ".+?" in its name, and switch it with \d+ of your {_POKEMON_TOKEN} ex in play that has ".+?" in its name\. Any attached cards, damage counters, Special Conditions, turns in play, and any other effects remain on the new {_POKEMON_TOKEN}\.$',
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-named-ex-from-discard-switch-with-named-ex-in-play-keep-state"),
    ),
    TextTemplate(
        name="put_one_self_pokemon_and_attached_into_hand",
        description="Put one of your Pokémon and all attached cards into your hand.",
        pattern=re.compile(
            rf"^Put \d+ of your {_POKEMON_TOKEN} and all attached cards into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_scoop_up_self,
    ),
    TextTemplate(
        name="discard_self_pokemon_and_all_attached",
        description="Discard this Pokémon and all attached cards.",
        pattern=re.compile(
            rf"^Discard this {_POKEMON_TOKEN} and all attached cards\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-self-pokemon-and-all-attached"),
    ),
    TextTemplate(
        name="parenthetical_prize_card_remains_face_up",
        description="Parenthetical reminder that prize card remains face up.",
        pattern=re.compile(
            r"^\(That Prize card remains face up for the rest of the game\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="parenthetical_if_cant_put_two_cards_bottom_cant_use",
        description="Parenthetical reminder about not being able to put two cards on bottom.",
        pattern=re.compile(
            r"^\(If you can't put \d+ cards from your hand on the bottom of your deck, you can't use this card\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="parenthetical_existing_effects_not_removed_damage_not_effect",
        description="Parenthetical reminder that existing effects are not removed and damage is not an effect.",
        pattern=re.compile(
            r"^\(Existing effects are not removed\. Damage is not an effect\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="parenthetical_weakness_amount_doesnt_change",
        description="Parenthetical reminder that weakness amount doesn't change.",
        pattern=re.compile(
            r"^\(The amount of Weakness doesn't change\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
    ),
    TextTemplate(
        name="discard_top_n_cards_of_self_deck",
        description="Discard top N cards of your deck.",
        pattern=re.compile(
            r"^Discard the top (?P<count>\d+) cards of your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-top-n-cards-of-self-deck", ("count",)),
    ),
    TextTemplate(
        name="attacks_used_by_poisoned_attached_bonus_to_opponent_active",
        description="Attacks used by poisoned attached Pokémon gain bonus damage to opponent active.",
        pattern=re.compile(
            rf"^Attacks used by the Poisoned {_POKEMON_TOKEN} this card is attached to do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attacks-used-by-poisoned-attached-bonus-to-opponent-active", ("amount",)),
    ),
    TextTemplate(
        name="end_of_turn_if_attached_in_active_may_attach_basic_from_discard",
        description="At end of turn, if attached Pokémon in active spot, may attach basic energy from discard.",
        pattern=re.compile(
            rf"^At the end of your turn \(after your attack\), if the {_POKEMON_TOKEN} this card is attached to is in the Active Spot, you may attach a Basic Energy card from your discard pile to it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("end-of-turn-if-attached-in-active-may-attach-basic-from-discard"),
    ),
    TextTemplate(
        name="opponent_discards_until_hand_size",
        description="Opponent discards cards from hand until target hand size.",
        pattern=re.compile(
            r"^Your opponent discards cards from their hand until they have (?P<count>\d+) cards in their hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-discards-until-hand-size", ("count",)),
    ),
    TextTemplate(
        name="attack_damage_per_special_condition_on_opponent_active",
        description="Attack damage per special condition affecting opponent active.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each Special Condition affecting your opponent's Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-per-special-condition-on-opponent-active", ("amount",)),
    ),
    TextTemplate(
        name="attack_damage_per_named_pair_and_also_damage_named_pair",
        description="Attack damage per named pair in play and also damages each of those named Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your .+? in play\. This attack also does (?P<splash>\d+) damage to each of your .+?\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-per-named-pair-and-also-damage-named-pair", ("amount", "splash")),
    ),
    TextTemplate(
        name="put_damage_counters_until_remaining_hp_value_on_opponent_active",
        description="Put damage counters on opponent active until remaining HP threshold.",
        pattern=re.compile(
            rf"^Put damage counters on your opponent's Active {_POKEMON_TOKEN} until its remaining HP is (?P<hp>\d+)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-damage-counters-until-remaining-hp-value-on-opponent-active", ("hp",)),
    ),
    TextTemplate(
        name="put_n_cards_from_hand_bottom_any_order",
        description="Put N cards from hand on bottom of deck in any order.",
        pattern=re.compile(
            r"^Put (?P<count>\d+) cards from your hand on the bottom of your deck in any order\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-n-cards-from-hand-bottom-any-order", ("count",)),
    ),
    TextTemplate(
        name="when_tera_attached_uses_attack_costs_less_any_type",
        description="When attached tera Pokémon uses attack, attack costs less energy of any type.",
        pattern=re.compile(
            rf"^When the Tera {_POKEMON_TOKEN} this card is attached to uses an attack, that attack costs \d+ Energy less\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("when-tera-attached-uses-attack-costs-less-any-type"),
    ),
    TextTemplate(
        name="move_all_energy_self_to_one_benched",
        description="Move all energy from this Pokémon to one of your benched Pokémon.",
        pattern=re.compile(
            rf"^Move all Energy from this {_POKEMON_TOKEN} to \d+ of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("move-all-energy-self-to-one-benched"),
    ),
    TextTemplate(
        name="attach_up_to_basic_energy_from_discard_to_one_benched",
        description="Attach up to N basic energy from discard to one of your benched Pokémon.",
        pattern=re.compile(
            rf"^Attach up to (?P<count>\d+) Basic Energy cards from your discard pile to \d+ of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-up-to-basic-energy-from-discard-to-one-benched", ("count",)),
    ),
    TextTemplate(
        name="discard_all_special_energy_from_all_opponent_pokemon",
        description="Discard all special energy from all of opponent's Pokémon.",
        pattern=re.compile(
            rf"^Discard all Special Energy from all of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-all-special-energy-from-all-opponent-pokemon"),
    ),
    TextTemplate(
        name="attack_more_damage_per_energy_in_self_discard",
        description="Attack bonus damage per energy card in your discard pile.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) more damage for each Energy card in your discard pile\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-more-damage-per-energy-in-self-discard", ("amount",)),
    ),
    TextTemplate(
        name="attach_up_to_basic_typed_energy_from_hand_any_way",
        description="Attach up to N basic typed energy cards from hand in any way.",
        pattern=re.compile(
            rf"^Attach up to (?P<count>\d+) Basic \{{[A-Z]\}} Energy cards from your hand to your {_POKEMON_TOKEN} in any way you like\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-up-to-basic-typed-energy-from-hand-any-way", ("count",)),
    ),
    TextTemplate(
        name="put_counters_on_each_opponent_bench_until_remaining_hp",
        description="Put damage counters on each opponent benched Pokémon until remaining HP threshold.",
        pattern=re.compile(
            rf"^Put damage counters on each of your opponent's Benched {_POKEMON_TOKEN} until its remaining HP is (?P<hp>\d+)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("put-counters-on-each-opponent-bench-until-remaining-hp", ("hp",)),
    ),
    TextTemplate(
        name="during_next_turn_defending_takes_more_damage",
        description="During your next turn, defending Pokémon takes more damage from attacks.",
        pattern=re.compile(
            rf"^During your next turn, the Defending {_POKEMON_TOKEN} takes (?P<amount>\d+) more damage from attacks \(after applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("during-next-turn-defending-takes-more-damage", ("amount",)),
    ),
    TextTemplate(
        name="attack_damage_to_each_opponent_ex_or_v",
        description="Attack damage to each opponent Pokémon ex and Pokémon V.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage to each of your opponent's {_POKEMON_TOKEN} ex and {_POKEMON_TOKEN} V\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-to-each-opponent-ex-or-v", ("amount",)),
    ),
    TextTemplate(
        name="attack_damage_to_new_active_generic",
        description="Attack damage to the new active Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage to the new Active {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-damage-to-new-active-generic", ("amount",)),
    ),
    TextTemplate(
        name="each_stage2_in_play_minus_hp",
        description="Each Stage 2 Pokémon in play gets reduced HP.",
        pattern=re.compile(
            rf"^Each Stage \d+ {_POKEMON_TOKEN} in play \(both yours and your opponent's\) gets -(?P<amount>\d+) HP\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-stage2-in-play-minus-hp", ("amount",)),
    ),
    TextTemplate(
        name="tell_opponent_named_pokemon_guess_hp_reveal_return",
        description="Tell opponent named Pokémon in hand, opponent guesses HP, reveal and return.",
        pattern=re.compile(
            rf"^Tell your opponent the name of a {_POKEMON_TOKEN} in your hand and put that {_POKEMON_TOKEN} face down in front of you\. Your opponent guesses that {_POKEMON_TOKEN}'s HP, and then you reveal it\. Then, return the {_POKEMON_TOKEN} to your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("tell-opponent-named-pokemon-guess-hp-reveal-return"),
    ),
    TextTemplate(
        name="heal_fixed_from_each_self_bench",
        description="Heal fixed damage from each of your benched Pokémon.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from each of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-fixed-from-each-self-bench", ("amount",)),
    ),
    TextTemplate(
        name="damage_not_affected_by_weakness_or_resistance",
        description="Damage is not affected by weakness or resistance.",
        pattern=re.compile(
            r"^This damage isn't affected by Weakness or Resistance\.$",
            re.IGNORECASE,
        ),
        builder=_ignore_weakness_resistance_and_effects,
    ),
    TextTemplate(
        name="each_named_ex_in_play_gets_bonus_hp",
        description="Each named ex in play gets bonus HP.",
        pattern=re.compile(
            rf"^Each .+? ex in play \(both yours and your opponent's\) gets \+(?P<hp>\d+) HP\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("each-named-ex-in-play-gets-bonus-hp", ("hp",)),
    ),
    TextTemplate(
        name="must_play_n_named_cards_at_once",
        description="Must play N named cards at once.",
        pattern=re.compile(
            r"^You must play (?P<count>\d+) .+? cards at once\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("must-play-n-named-cards-at-once", ("count",)),
    ),
    TextTemplate(
        name="your_turn_ends",
        description="Your turn ends.",
        pattern=re.compile(r"^Your turn ends\.$", re.IGNORECASE),
        builder=_script_hook_builder("your-turn-ends"),
    ),
    TextTemplate(
        name="then_draw_per_opponent_hand_cards",
        description="Then draw a card for each card in your opponent's hand.",
        pattern=re.compile(
            r"^Then, draw a card for each card in your opponent's hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("then-draw-per-opponent-hand-cards"),
    ),
    TextTemplate(
        name="then_if_have_n_or_more_cards_draw_m_more",
        description="Then, if you have N or more cards in hand, draw M more cards.",
        pattern=re.compile(
            r"^Then, if you have (?P<threshold>\d+) or more cards in your hand, draw (?P<count>\d+) more cards\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("then-if-have-n-or-more-cards-draw-m-more", ("threshold", "count")),
    ),
    TextTemplate(
        name="then_discard_named_cards_shuffle_others_back",
        description="Then discard named cards and shuffle the other cards back into deck.",
        pattern=re.compile(
            r"^Then, discard those .+? cards and shuffle the other cards back into your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("then-discard-named-cards-shuffle-others-back"),
    ),
    TextTemplate(
        name="any_attached_cards_damage_counters_conditions_remain",
        description="Attached cards, counters, conditions, turns in play, and effects remain on new Pokémon.",
        pattern=re.compile(
            rf"^Any attached cards, damage counters, Special Conditions, turns in play, and any other effects remain on the new {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("any-attached-cards-counters-conditions-remain"),
    ),
    TextTemplate(
        name="attack_use_gate_go_second_first_turn_only",
        description="You can use this attack only if you go second and during your first turn.",
        pattern=re.compile(
            r"^You can use this attack only if you go second, and only during your first turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attack-use-gate-go-second-first-turn-only"),
    ),
    TextTemplate(
        name="opponent_cant_play_supporter_next_turn",
        description="Opponent cannot play supporter cards from hand during next turn.",
        pattern=re.compile(
            r"^Your opponent can't play any Supporter cards from their hand during their next turn\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-cant-play-supporter-next-turn"),
    ),
    TextTemplate(
        name="knock_out_opponent_with_exact_damage_counters",
        description="Knock out one opponent Pokémon with exactly N damage counters.",
        pattern=re.compile(
            rf"^Knock Out \d+ of your opponent's {_POKEMON_TOKEN} that has exactly (?P<count>\d+) damage counters on it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("knock-out-opponent-with-exact-damage-counters", ("count",)),
    ),
    TextTemplate(
        name="attacks_used_by_named_pokemon_bonus_to_opponent_active",
        description="Attacks used by named Pokémon do bonus damage to opponent active.",
        pattern=re.compile(
            rf"^Attacks used by your .+? {_POKEMON_TOKEN} do (?P<amount>\d+) more damage to your opponent's Active {_POKEMON_TOKEN} \(before applying Weakness and Resistance\)\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attacks-used-by-named-pokemon-bonus-to-opponent-active", ("amount",)),
    ),
    TextTemplate(
        name="prevent_damage_to_bench_without_rule_box_from_opponent_attacks",
        description="Prevent damage to your benched Pokémon without Rule Box from opponent attacks.",
        pattern=re.compile(
            rf"^Prevent all damage done to your Benched {_POKEMON_TOKEN} that don't have a Rule Box by attacks from your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-damage-to-bench-without-rule-box-from-opponent-attacks"),
    ),
    TextTemplate(
        name="tell_opponent_named_pokemon_face_down_in_front",
        description="Tell opponent a Pokémon name in hand and place that Pokémon face down in front.",
        pattern=re.compile(
            rf"^Tell your opponent the name of a {_POKEMON_TOKEN} in your hand and put that {_POKEMON_TOKEN} face down in front of you\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("tell-opponent-named-pokemon-face-down-in-front"),
    ),
    TextTemplate(
        name="opponent_guesses_hp_then_reveal",
        description="Opponent guesses that Pokémon HP and then you reveal it.",
        pattern=re.compile(
            rf"^Your opponent guesses that {_POKEMON_TOKEN}'s HP, and then you reveal it\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-guesses-hp-then-reveal"),
    ),
    TextTemplate(
        name="then_return_that_pokemon_to_hand",
        description="Then return that Pokémon to your hand.",
        pattern=re.compile(
            rf"^Then, return the {_POKEMON_TOKEN} to your hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("then-return-that-pokemon-to-hand"),
    ),
    TextTemplate(
        name="generic_this_attack_clause",
        description="Fallback for unresolved 'This attack ...' clauses.",
        pattern=re.compile(r"^This attack .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-this-attack-clause"),
    ),
    TextTemplate(
        name="generic_discard_clause",
        description="Fallback for unresolved 'Discard ...' clauses.",
        pattern=re.compile(r"^Discard .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-discard-clause"),
    ),
    TextTemplate(
        name="generic_attach_clause",
        description="Fallback for unresolved 'Attach ...' clauses.",
        pattern=re.compile(r"^Attach .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-attach-clause"),
    ),
    TextTemplate(
        name="generic_move_clause",
        description="Fallback for unresolved 'Move ...' clauses.",
        pattern=re.compile(r"^Move .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-move-clause"),
    ),
    TextTemplate(
        name="generic_heal_clause",
        description="Fallback for unresolved 'Heal ...' clauses.",
        pattern=re.compile(r"^Heal .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-heal-clause"),
    ),
    TextTemplate(
        name="generic_look_clause",
        description="Fallback for unresolved 'Look at ...' clauses.",
        pattern=re.compile(r"^Look at .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-look-clause"),
    ),
    TextTemplate(
        name="generic_reveal_clause",
        description="Fallback for unresolved 'Reveal ...' clauses.",
        pattern=re.compile(r"^Reveal .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-reveal-clause"),
    ),
    TextTemplate(
        name="generic_put_clause",
        description="Fallback for unresolved 'Put ...' clauses.",
        pattern=re.compile(r"^Put .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-put-clause"),
    ),
    TextTemplate(
        name="generic_choose_clause",
        description="Fallback for unresolved 'Choose ...' clauses.",
        pattern=re.compile(r"^Choose .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-choose-clause"),
    ),
    TextTemplate(
        name="generic_once_each_players_turn_clause",
        description="Fallback for unresolved 'Once during each player's turn ...' clauses.",
        pattern=re.compile(r"^Once during each player's turn, .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-once-each-players-turn-clause"),
    ),
    TextTemplate(
        name="generic_each_player_clause",
        description="Fallback for unresolved 'Each player ...' clauses.",
        pattern=re.compile(r"^Each player .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-each-player-clause"),
    ),
    TextTemplate(
        name="generic_your_opponent_clause",
        description="Fallback for unresolved 'Your opponent ...' clauses.",
        pattern=re.compile(r"^Your opponent .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-your-opponent-clause"),
    ),
    TextTemplate(
        name="generic_when_clause",
        description="Fallback for unresolved 'When ...' clauses.",
        pattern=re.compile(r"^When .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-when-clause"),
    ),
    TextTemplate(
        name="generic_whenever_clause",
        description="Fallback for unresolved 'Whenever ...' clauses.",
        pattern=re.compile(r"^Whenever .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-whenever-clause"),
    ),
    TextTemplate(
        name="generic_during_next_turn_clause",
        description="Fallback for unresolved 'During your next turn ...' clauses.",
        pattern=re.compile(r"^During your next turn, .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("generic-during-next-turn-clause"),
    ),
    TextTemplate(
        name="during_opponent_next_turn_generic",
        description="Generic during opponent next turn clause fallback.",
        pattern=re.compile(r"^During your opponent's next turn, .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("during-opponent-next-turn-generic"),
    ),
    TextTemplate(
        name="as_long_as_generic",
        description="Generic as-long-as clause fallback.",
        pattern=re.compile(r"^As long as .+\.$", re.IGNORECASE),
        builder=_script_hook_builder("as-long-as-generic"),
    ),
    TextTemplate(
        name="once_if_active_spot_discard_energy_for_ability",
        description="Once during turn while active, discard basic energy from hand to use ability.",
        pattern=re.compile(
            rf"^Once during your turn, if this {_POKEMON_TOKEN} is in the Active Spot, you may discard a Basic \{{[A-Z]\}} Energy card from your hand in order to use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-if-active-spot-discard-energy-for-ability"),
    ),
    TextTemplate(
        name="may_put_any_number_found_onto_bench",
        description="May put any number of found Pokémon onto your bench.",
        pattern=re.compile(
            rf"^You may put any number of {_POKEMON_TOKEN} you find there onto your Bench\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("may-put-any-number-found-onto-bench"),
    ),
    TextTemplate(
        name="search_then_shuffle_generic",
        description="Generic search deck clause followed by then shuffle your deck.",
        pattern=re.compile(
            r"^Search your deck for .+\. Then, shuffle your deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("search-then-shuffle-generic"),
    ),
    TextTemplate(
        name="pokemon_in_play_lose_self_ko_abilities",
        description="Pokémon in play lose abilities that require self-KO.",
        pattern=re.compile(
            rf"^{_POKEMON_TOKEN} in play \(both yours and your opponent's\) lose any Ability that requires the {_POKEMON_TOKEN} using it to Knock Out itself\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("pokemon-in-play-lose-self-ko-abilities"),
    ),
    TextTemplate(
        name="damage_per_opponent_hand_card",
        description="Damage for each card in opponent hand.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each card in your opponent's hand\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-per-opponent-hand-card", ("amount",)),
    ),
    TextTemplate(
        name="damage_to_each_of_n_opponent_pokemon",
        description="Damage to each of N of opponent's Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage to each of (?P<count>\d+) of your opponent's {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-to-each-of-n-opponent-pokemon", ("amount", "count")),
    ),
    TextTemplate(
        name="may_discard_typed_energy_and_paralyze",
        description="May discard typed energy from this Pokémon and paralyze opponent active.",
        pattern=re.compile(
            rf"^You may discard (?P<count>\d+) \{{[A-Z]\}} Energy from this {_POKEMON_TOKEN} and make your opponent's Active {_POKEMON_TOKEN} Paralyzed\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("may-discard-typed-energy-and-paralyze", ("count",)),
    ),
    TextTemplate(
        name="when_opponent_active_knocked_out_flip_coin",
        description="When opponent active is knocked out, flip a coin.",
        pattern=re.compile(
            rf"^When your opponent's Active {_POKEMON_TOKEN} is Knocked Out, flip a coin\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("when-opponent-active-knocked-out-flip-coin"),
    ),
    TextTemplate(
        name="opponent_chooses_cards_shuffle_into_deck",
        description="Opponent chooses cards from hand and shuffles them into deck.",
        pattern=re.compile(
            r"^Your opponent chooses (?P<count>\d+) cards from their hand and shuffles those cards into their deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-chooses-cards-shuffle-into-deck", ("count",)),
    ),
    TextTemplate(
        name="copy_opponent_active_tera_attack",
        description="Copy one of opponent active Tera Pokémon attacks.",
        pattern=re.compile(
            rf"^Choose \d+ of your opponent's Active Tera {_POKEMON_TOKEN}'s attacks and use it as this attack\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("copy-opponent-active-tera-attack"),
    ),
    TextTemplate(
        name="attach_up_to_basic_typed_from_discard_to_self",
        description="Attach up to N basic typed energy from discard to this Pokémon.",
        pattern=re.compile(
            rf"^Attach up to (?P<count>\d+) Basic \{{[A-Z]\}} Energy cards from your discard pile to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("attach-up-to-basic-typed-from-discard-to-self", ("count",)),
    ),
    TextTemplate(
        name="damage_per_benched_named_with_weakness_ignored",
        description="Damage per counters on benched named Pokémon with weakness ignore note.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each damage counter on all of your Benched .+? {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-per-benched-named-with-weakness-ignored", ("amount",)),
    ),
    TextTemplate(
        name="damage_not_affected_by_weakness_only",
        description="Attack damage is not affected by weakness.",
        pattern=re.compile(
            r"^This attack's damage isn't affected by Weakness\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("damage-not-affected-by-weakness-only"),
    ),
    TextTemplate(
        name="team_rocket_knockout_gate_shuffle_draw_split",
        description="Team Rocket knockout gate then both players shuffle and draw different counts.",
        pattern=re.compile(
            rf"^You can use this card only if any of your Team Rocket's {_POKEMON_TOKEN} were Knocked Out during your opponent's last turn\. Each player shuffles their hand into their deck\. Then, you draw (?P<self_count>\d+) cards, and your opponent draws (?P<opp_count>\d+) cards\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("team-rocket-knockout-gate-shuffle-draw-split", ("self_count", "opp_count")),
    ),
    TextTemplate(
        name="choose_up_to_two_tools_attached_discard",
        description="Choose up to N tools attached to Pokémon and discard them.",
        pattern=re.compile(
            rf"^Choose up to (?P<count>\d+) {_POKEMON_TOKEN} Tools attached to {_POKEMON_TOKEN} \(yours or your opponent's\) and discard them\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("choose-up-to-two-tools-attached-discard", ("count",)),
    ),
    TextTemplate(
        name="all_pokemon_tools_have_no_effect",
        description="All attached Pokémon tools have no effect.",
        pattern=re.compile(
            rf"^{_POKEMON_TOKEN} Tools attached to each {_POKEMON_TOKEN} \(both yours and your opponent's\) have no effect\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("all-pokemon-tools-have-no-effect"),
    ),
    TextTemplate(
        name="opponent_shuffle_hand_to_bottom",
        description="Opponent shuffles hand and puts it on bottom of deck.",
        pattern=re.compile(
            r"^Your opponent shuffles their hand and puts it on the bottom of their deck\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("opponent-shuffle-hand-to-bottom"),
    ),
    TextTemplate(
        name="prevent_effects_of_opponent_abilities_to_self",
        description="Prevent all effects of opponent Pokémon abilities done to this Pokémon.",
        pattern=re.compile(
            rf"^Prevent all effects of your opponent's {_POKEMON_TOKEN}'s Abilities done to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("prevent-effects-of-opponent-abilities-to-self"),
    ),
    TextTemplate(
        name="discard_up_to_hand_energy_damage_bonus_per_discarded",
        description="Discard up to N energy from hand for bonus damage per discarded card.",
        pattern=re.compile(
            r"^You may discard up to (?P<count>\d+) Energy cards from your hand, and this attack does (?P<amount>\d+) more damage for each card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("discard-up-to-hand-energy-damage-bonus-per-discarded", ("count", "amount")),
    ),
    TextTemplate(
        name="reveal_any_number_named_damage_per_revealed",
        description="Reveal any number of named cards from hand for damage scaling.",
        pattern=re.compile(
            r"^Reveal any number of .+? from your hand, and this attack does (?P<amount>\d+) damage for each card you revealed in this way\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("reveal-any-number-named-damage-per-revealed", ("amount",)),
    ),
    TextTemplate(
        name="once_when_played_to_bench_may_use_ability",
        description="Once during turn when played to bench, may use ability.",
        pattern=re.compile(
            rf"^Once during your turn, when you play this {_POKEMON_TOKEN} from your hand onto your Bench, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("once-when-played-to-bench-may-use-ability"),
    ),
    TextTemplate(
        name="limit_named_ability_with_phrase_each_turn",
        description="You can't use more than N abilities matching quoted phrase each turn.",
        pattern=re.compile(
            r'^You can\'t use more than (?P<count>\d+) Ability that has ".+?" in its name each turn\.$',
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("limit-named-ability-with-phrase-each-turn", ("count",)),
    ),
    TextTemplate(
        name="heal_fixed_damage_from_typed_pokemon",
        description="Heal fixed damage from one of your typed Pokémon.",
        pattern=re.compile(
            rf"^Heal (?P<amount>\d+) damage from \d+ of your \{{[A-Z]\}} {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("heal-fixed-damage-from-typed-pokemon", ("amount",)),
    ),
    TextTemplate(
        name="more_prizes_gate_attach_to_stage2",
        description="If you have more prizes, attach basic energy from discard to stage 2.",
        pattern=re.compile(
            rf"^You can use this card only if you have more Prize cards remaining than your opponent\. Attach up to (?P<count>\d+) Basic Energy cards from your discard pile to \d+ of your Stage \d+ {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_script_hook_builder("more-prizes-gate-attach-to-stage2", ("count",)),
    ),
    TextTemplate(
        name="then_shuffle_deck",
        description="Then, shuffle your deck.",
        pattern=re.compile(r"^Then, shuffle your deck\.$", re.IGNORECASE),
        builder=_then_shuffle_deck,
    ),
    TextTemplate(
        name="shuffle_hand_into_deck",
        description="Shuffle your hand into your deck.",
        pattern=re.compile(r"^Shuffle your hand into your deck\.$", re.IGNORECASE),
        builder=_shuffle_hand_into_deck,
    ),
    TextTemplate(
        name="then_draw_cards",
        description="Then, draw a fixed number of cards.",
        pattern=re.compile(r"^Then, draw (?P<count>\d+) cards\.$", re.IGNORECASE),
        builder=_then_draw_cards,
    ),
    TextTemplate(
        name="put_other_card_on_bottom",
        description="Put the other card on the bottom of your deck.",
        pattern=re.compile(r"^Put the other card on the bottom of your deck\.$", re.IGNORECASE),
        builder=_put_other_card_on_bottom,
    ),
    TextTemplate(
        name="conditional_draw_by_prize_state",
        description="Conditional draw based on prize-card state.",
        pattern=re.compile(
            r"^If (?P<condition>.+? Prize cards? remaining), draw (?P<count>\d+) cards instead\.$",
            re.IGNORECASE,
        ),
        builder=_conditional_draw_by_prize_state,
    ),
    TextTemplate(
        name="as_often_use_ability_note",
        description="As often as you like, you may use this Ability.",
        pattern=re.compile(
            r"^As often as you like during your turn, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_as_often_use_ability_note,
    ),
    TextTemplate(
        name="move_basic_energy_between_self_pokemon",
        description="Move a Basic Energy between your Pokémon.",
        pattern=re.compile(
            rf"^Move .+? Energy from (?P<count>\d+) of your {_POKEMON_TOKEN} to another of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_move_basic_energy_between_self_pokemon,
    ),
    TextTemplate(
        name="defending_attack_flip_tails_fails",
        description="If defending tries to attack, flip tails causes attack failure.",
        pattern=re.compile(
            rf"^During your opponent's next turn, if the Defending {_POKEMON_TOKEN} tries to use an attack, your opponent flips a coin\. If tails, that attack doesn't happen\.$",
            re.IGNORECASE,
        ),
        builder=_defending_attack_flip_tails_fails,
    ),
    TextTemplate(
        name="once_if_active_may_use_ability",
        description="Once during your turn, if this Pokémon is Active, you may use this Ability.",
        pattern=re.compile(
            rf"^Once during your turn, if this {_POKEMON_TOKEN} is in the Active Spot, you may use this Ability\.$",
            re.IGNORECASE,
        ),
        builder=_once_if_active_may_use_ability,
    ),
    TextTemplate(
        name="card_use_gate_by_opponent_prizes",
        description="Card use gate by opponent prize count.",
        pattern=re.compile(
            r"^You can use this card only if your opponent has (?P<count>\d+) or fewer Prize cards remaining\.$",
            re.IGNORECASE,
        ),
        builder=_card_use_gate_by_opponent_prizes,
    ),
    TextTemplate(
        name="choose_self_pokemon_in_play",
        description="Choose one of your Pokémon in play.",
        pattern=re.compile(
            rf"^Choose 1 of your {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_choose_self_pokemon_in_play,
    ),
    TextTemplate(
        name="prevent_all_damage_effects_to_that_from_ex",
        description="Prevent all damage/effects to that Pokémon from ex next turn.",
        pattern=re.compile(
            rf"^During your opponent's next turn, prevent all damage from and effects of attacks done to that {_POKEMON_TOKEN} by your opponent's {_POKEMON_TOKEN} ex\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_all_damage_effects_to_that_from_ex,
    ),
    TextTemplate(
        name="recover_pokemon_or_basic_energy_from_discard",
        description="Put a Pokémon or Basic Energy from discard into hand.",
        pattern=re.compile(
            rf"^Put a {_POKEMON_TOKEN} or a Basic Energy card from your discard pile into your hand\.$",
            re.IGNORECASE,
        ),
        builder=_recover_pokemon_or_basic_energy_from_discard,
    ),
    TextTemplate(
        name="status_asleep_and_poisoned",
        description="Apply both Asleep and Poisoned to opponent Active.",
        pattern=re.compile(
            rf"^Your opponent's Active {_POKEMON_TOKEN} is now Asleep and Poisoned\.$",
            re.IGNORECASE,
        ),
        builder=_status_asleep_and_poisoned,
    ),
    TextTemplate(
        name="no_retreat_cost_if_no_energy",
        description="No retreat cost when this Pokémon has no Energy attached.",
        pattern=re.compile(
            rf"^If this {_POKEMON_TOKEN} has no Energy attached, it has no Retreat Cost\.$",
            re.IGNORECASE,
        ),
        builder=_no_retreat_cost_if_no_energy,
    ),
    TextTemplate(
        name="discard_any_amount_energy_among_self",
        description="Discard any amount of typed Energy from among your Pokémon.",
        pattern=re.compile(
            rf"^Discard any amount of \{{[A-Z]\}} Energy from among your {_POKEMON_TOKEN}, and this attack does (?P<amount>\d+) damage for each card you discarded in this way\.$",
            re.IGNORECASE,
        ),
        builder=_discard_any_amount_energy_and_damage,
    ),
    TextTemplate(
        name="damage_for_each_self_pokemon_in_play",
        description="Damage for each of your Pokémon in play.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) damage for each of your {_POKEMON_TOKEN} in play\.$",
            re.IGNORECASE,
        ),
        builder=_damage_for_each_self_pokemon_in_play,
    ),
    TextTemplate(
        name="damage_more_per_energy_on_self",
        description="Damage bonus for each Energy attached to this Pokémon.",
        pattern=re.compile(
            rf"^This attack does (?P<amount>\d+) more damage for each \{{[A-Z]\}} Energy attached to this {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_damage_more_per_energy_on_self,
    ),
    TextTemplate(
        name="damage_base_per_prize_taken",
        description="Base damage for each Prize card opponent has taken.",
        pattern=re.compile(
            r"^This attack does (?P<amount>\d+) damage for each Prize card your opponent has taken\.$",
            re.IGNORECASE,
        ),
        builder=_damage_base_per_prize_taken,
    ),
]

COIN_FLIP_TEMPLATE = re.compile(
    r"^Flip a coin\. If heads, (?P<heads>.+?)\. If tails, (?P<tails>.+?)\.$",
    re.IGNORECASE,
)
COIN_FLIP_SINGLE_BRANCH_TEMPLATE = re.compile(
    r"^Flip a coin\. If (?P<result>heads|tails), (?P<effect>.+?)\.$",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list[str]:
    text = text.replace("; ", ". ")
    # Keep abbreviations like "etc." from being split into separate clauses.
    text = re.sub(r"\betc\.", "etc<dot>", text, flags=re.IGNORECASE)
    text = text.replace(
        "(Existing effects are not removed. Damage is not an effect.)",
        "(Existing effects are not removed<dot> Damage is not an effect.)",
    )
    sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned_segments = [
        segment.strip().replace("etc<dot>", "etc.").replace("removed<dot>", "removed.")
        for segment in sentences
        if segment.strip()
    ]
    return [segment for segment in cleaned_segments if segment.strip(". ")]


def _merge_coin_flip_sequences(sentences: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(sentences):
        current = sentences[index]
        if (
            current.lower() == "flip a coin."
            and index + 2 < len(sentences)
            and sentences[index + 1].lower().startswith("if heads,")
            and sentences[index + 2].lower().startswith("if tails,")
        ):
            merged.append(f"{current} {sentences[index + 1]} {sentences[index + 2]}")
            index += 3
            continue

        if (
            current.lower() == "flip a coin."
            and index + 1 < len(sentences)
            and (
                sentences[index + 1].lower().startswith("if heads,")
                or sentences[index + 1].lower().startswith("if tails,")
            )
        ):
            merged.append(f"{current} {sentences[index + 1]}")
            index += 2
            continue

        if (
            re.fullmatch(r"flip \d+ coins\.", current.strip(), flags=re.IGNORECASE)
            and index + 1 < len(sentences)
            and re.fullmatch(
                r"this attack does \d+ damage for each (heads|tails)\.",
                sentences[index + 1].strip(),
                flags=re.IGNORECASE,
            )
        ):
            merged.append(f"{current} {sentences[index + 1]}")
            index += 2
            continue

        if (
            current.lower().startswith("search your deck for")
            and index + 1 < len(sentences)
            and sentences[index + 1].lower() == "then, shuffle your deck."
        ):
            merged.append(f"{current} {sentences[index + 1]}")
            index += 2
            continue

        merged.append(current)
        index += 1

    return merged


def _compile_clause(clause: str) -> tuple[list[EffectOperation], str | None]:
    clause = clause.strip()
    deferred_script_fallback: tuple[list[EffectOperation], str] | None = None

    once_match = _ONCE_DURING_TURN_TEMPLATE.fullmatch(clause)
    if once_match:
        operations, _ = _build_triggered_effect(
            "once_during_turn",
            once_match.group("effect"),
            once_match.groupdict().get("condition"),
        )
        if operations:
            return operations, "triggered_once_clause"
        deferred_script_fallback = _script_hook_from_clause(
            "triggered_once_clause",
            clause,
            {
                "trigger": "once_during_turn",
                "effect": once_match.group("effect").strip(),
                "condition": (once_match.groupdict().get("condition") or "").strip(),
            },
        )

    as_often_match = _AS_OFTEN_DURING_TURN_TEMPLATE.fullmatch(clause)
    if as_often_match:
        operations, _ = _build_triggered_effect(
            "as_often_as_you_like",
            as_often_match.group("effect"),
            as_often_match.groupdict().get("condition"),
        )
        if operations:
            return operations, "triggered_repeatable_clause"
        if deferred_script_fallback is None:
            deferred_script_fallback = _script_hook_from_clause(
                "triggered_repeatable_clause",
                clause,
                {
                    "trigger": "as_often_as_you_like",
                    "effect": as_often_match.group("effect").strip(),
                    "condition": (as_often_match.groupdict().get("condition") or "").strip(),
                },
            )

    when_play_match = _WHEN_PLAY_FROM_HAND_TO_BENCH_TEMPLATE.fullmatch(clause)
    if when_play_match:
        operations, _ = _build_triggered_effect("on_play_from_hand_to_bench", when_play_match.group("effect"))
        if operations:
            return operations, "triggered_play_clause"
        if deferred_script_fallback is None:
            deferred_script_fallback = _script_hook_from_clause(
                "triggered_play_clause",
                clause,
                {"trigger": "on_play_from_hand_to_bench", "effect": when_play_match.group("effect").strip()},
            )

    optional_match = _OPTIONAL_TEMPLATE.fullmatch(clause)
    if optional_match:
        optional_effect = optional_match.group("effect").strip()
        if not optional_effect.endswith("."):
            optional_effect = f"{optional_effect}."
        optional_program = compile_effect_text(optional_effect)
        if optional_program.is_fully_resolved and optional_program.operations:
            return (
                [
                    EffectOperation(
                        op="optional_effect",
                        params={
                            "condition": "player_choice",
                            "operations": [operation.to_dict() for operation in optional_program.operations],
                            "unresolved": optional_program.unresolved_details,
                        },
                    )
                ],
                "optional_clause",
            )
        if deferred_script_fallback is None:
            deferred_script_fallback = _script_hook_from_clause(
                "optional_clause",
                clause,
                {"effect": optional_effect},
            )

    conditional_match = _CONDITIONAL_TEMPLATE.fullmatch(clause)
    if conditional_match:
        conditional_effect = conditional_match.group("effect").strip()
        if not conditional_effect.endswith("."):
            conditional_effect = f"{conditional_effect}."
        conditional_program = compile_effect_text(conditional_effect)
        if conditional_program.is_fully_resolved and conditional_program.operations:
            return (
                [
                    EffectOperation(
                        op="conditional_effect",
                        params={
                            "condition": conditional_match.group("condition").strip(),
                            "operations": [operation.to_dict() for operation in conditional_program.operations],
                            "unresolved": conditional_program.unresolved_details,
                        },
                    )
                ],
                "conditional_clause",
            )
        if deferred_script_fallback is None:
            deferred_script_fallback = _script_hook_from_clause(
                "conditional_clause",
                clause,
                {
                    "condition": conditional_match.group("condition").strip(),
                    "effect": conditional_effect,
                },
            )

    coin_match = COIN_FLIP_TEMPLATE.fullmatch(clause)
    if coin_match:
        heads_text = coin_match.group("heads").strip()
        tails_text = coin_match.group("tails").strip()
        if not heads_text.endswith("."):
            heads_text = f"{heads_text}."
        if not tails_text.endswith("."):
            tails_text = f"{tails_text}."

        heads_program = compile_effect_text(heads_text)
        tails_program = compile_effect_text(tails_text)
        return (
            [
                EffectOperation(
                    op="flip_coin",
                    params={
                        "heads": [operation.to_dict() for operation in heads_program.operations],
                        "tails": [operation.to_dict() for operation in tails_program.operations],
                        "heads_unresolved": heads_program.unresolved_text,
                        "tails_unresolved": tails_program.unresolved_text,
                    },
                )
            ],
            "coin_flip_branch",
        )

    single_coin_match = COIN_FLIP_SINGLE_BRANCH_TEMPLATE.fullmatch(clause)
    if single_coin_match:
        effect_text = single_coin_match.group("effect").strip()
        if not effect_text.endswith("."):
            effect_text = f"{effect_text}."

        effect_program = compile_effect_text(effect_text)
        result = single_coin_match.group("result").lower()
        heads_ops = [operation.to_dict() for operation in effect_program.operations] if result == "heads" else []
        tails_ops = [operation.to_dict() for operation in effect_program.operations] if result == "tails" else []
        return (
            [
                EffectOperation(
                    op="flip_coin",
                    params={
                        "heads": heads_ops,
                        "tails": tails_ops,
                        "heads_unresolved": effect_program.unresolved_text if result == "heads" else None,
                        "tails_unresolved": effect_program.unresolved_text if result == "tails" else None,
                    },
                )
            ],
            "coin_flip_single_branch",
        )

    for template in CLAUSE_TEMPLATES:
        match = template.pattern.fullmatch(clause)
        if match:
            return template.builder(match), template.name

    if " and " in clause.lower() and not clause.lower().startswith("if "):
        parts = [part.strip() for part in re.split(r"\band\b", clause, flags=re.IGNORECASE) if part.strip()]
        if len(parts) > 1:
            composite_operations: list[EffectOperation] = []
            resolved_parts = 0
            for part in parts:
                candidate = part if part.endswith(".") else f"{part}."
                part_operations, template_name = _compile_clause(candidate)
                if template_name is None:
                    composite_operations = []
                    break
                resolved_parts += 1
                composite_operations.extend(part_operations)
            if resolved_parts == len(parts):
                return composite_operations, "composite_and_clause"

    fallback = resolve_script_fallback(clause)
    if fallback is not None:
        return fallback

    if deferred_script_fallback is not None:
        return deferred_script_fallback

    if _looks_like_tcg_clause(clause):
        return _script_hook_from_clause("generic_tcg_clause", clause)

    return [], None


def compile_effect_text(text: str) -> EffectProgram:
    normalized = normalize_card_text(text)
    if not normalized:
        return EffectProgram(source_text=text, unresolved_text="")

    clauses = _merge_coin_flip_sequences(_split_sentences(normalized))

    operations: list[EffectOperation] = []
    template_names: list[str] = []
    unresolved_clauses: list[str] = []
    unresolved_details: list[dict[str, str]] = []

    for clause in clauses:
        clause_operations, template_name = _compile_clause(clause)
        if template_name is None:
            unresolved_clauses.append(clause)
            unresolved_details.append({"clause": clause, "reason": "no_template_or_fallback_match"})
            register_unresolved_clause(clause, source_text=normalized)
            continue
        operations.extend(clause_operations)
        template_names.append(template_name)

    return EffectProgram(
        source_text=normalized,
        operations=operations,
        template_name=" + ".join(template_names) if template_names else None,
        unresolved_text=" ".join(unresolved_clauses) if unresolved_clauses else None,
        unresolved_details=unresolved_details,
    )


def supported_templates() -> list[dict[str, str]]:
    templates = [
        {"name": template.name, "description": template.description}
        for template in CLAUSE_TEMPLATES
    ]
    templates.append(
        {
            "name": "coin_flip_branch",
            "description": "Flip a coin with independent heads/tails effect clauses.",
        }
    )
    templates.append(
        {
            "name": "coin_flip_single_branch",
            "description": "Flip a coin where only one branch has an effect clause.",
        }
    )
    return templates

