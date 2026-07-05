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


def normalize_card_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("’", "'")
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
            rf"^Switch (?:your Active {_POKEMON_TOKEN}|this {_POKEMON_TOKEN}) with 1 of your Benched {_POKEMON_TOKEN}\.$",
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
            rf"^Attach (?:up to (?P<count>\d+) |a |an )(?P<descriptor>.+?) Energy card from your hand to 1 of your {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_attach_energy_from_hand,
    ),
    TextTemplate(
        name="attach_energy_from_discard",
        description="Attach energy card(s) from discard to your Pokémon.",
        pattern=re.compile(
            rf"^Attach (?:up to (?P<count>\d+) |a |an )(?P<descriptor>.+?) Energy card from your discard pile to 1 of your {_POKEMON_TOKEN}\.$",
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
            rf"^During your opponent's next turn, the Defending {_POKEMON_TOKEN} can't use attacks\.$",
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
        name="flip_coin_only",
        description="Flip a coin with no immediate branch clause.",
        pattern=re.compile(r"^Flip a coin\.$", re.IGNORECASE),
        builder=_flip_coin_only,
    ),
    TextTemplate(
        name="parenthetical_noop",
        description="Parenthetical reminder text with no state change in demo runtime.",
        pattern=re.compile(
            rf"^\((?:Your opponent chooses the new Active {_POKEMON_TOKEN}|Don't apply Weakness and Resistance for Benched {_POKEMON_TOKEN})\.\)$",
            re.IGNORECASE,
        ),
        builder=_parenthetical_noop,
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
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [segment.strip() for segment in sentences if segment.strip()]


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

    optional_match = _OPTIONAL_TEMPLATE.fullmatch(clause)
    if optional_match:
        optional_effect = optional_match.group("effect").strip()
        if not optional_effect.endswith("."):
            optional_effect = f"{optional_effect}."
        optional_program = compile_effect_text(optional_effect)
        if not optional_program.is_fully_resolved or not optional_program.operations:
            return [], None
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

    conditional_match = _CONDITIONAL_TEMPLATE.fullmatch(clause)
    if conditional_match:
        conditional_effect = conditional_match.group("effect").strip()
        if not conditional_effect.endswith("."):
            conditional_effect = f"{conditional_effect}."
        conditional_program = compile_effect_text(conditional_effect)
        if not conditional_program.is_fully_resolved or not conditional_program.operations:
            return [], None
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

    fallback = resolve_script_fallback(clause)
    if fallback is not None:
        return fallback

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

