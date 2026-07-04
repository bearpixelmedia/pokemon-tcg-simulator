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


def _discard_energy_from_self(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="discard_energy",
            params={"target": "self_active", "count": _coerce_count(match.group("count"))},
        )
    ]


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


def _no_weakness_resistance(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [EffectOperation(op="ignore_weakness_resistance", params={"target": "attack"})]


def _cannot_attack_next_turn(match: re.Match[str]) -> list[EffectOperation]:
    _ = match
    return [
        EffectOperation(
            op="apply_temporary_rule",
            params={"target": "self_active", "rule": "cannot_attack_next_turn"},
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
            rf"^This attack does (?P<damage>\d+) damage to (?:(?P<count>\d+) of your opponent's Benched {_POKEMON_TOKEN}|1 of your opponent's Benched {_POKEMON_TOKEN}|that {_POKEMON_TOKEN})\.$",
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
        name="shuffle_deck",
        description="Shuffle your deck.",
        pattern=re.compile(r"^Shuffle your deck\.$", re.IGNORECASE),
        builder=_shuffle_deck,
    ),
    TextTemplate(
        name="switch_self_active",
        description="Switch your Active Pokémon with one of your Benched Pokémon.",
        pattern=re.compile(
            rf"^Switch your Active {_POKEMON_TOKEN} with 1 of your Benched {_POKEMON_TOKEN}\.$",
            re.IGNORECASE,
        ),
        builder=_switch_self_active,
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
            rf"^During your opponent's next turn, this {_POKEMON_TOKEN} takes (?P<amount>\d+) less damage from attacks\.$",
            re.IGNORECASE,
        ),
        builder=_prevent_damage_next_turn,
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
        name="cannot_attack_next_turn",
        description="This Pokémon cannot attack during your next turn.",
        pattern=re.compile(
            rf"^During your next turn, this {_POKEMON_TOKEN} can't attack\.$",
            re.IGNORECASE,
        ),
        builder=_cannot_attack_next_turn,
    ),
]

COIN_FLIP_TEMPLATE = re.compile(
    r"^Flip a coin\. If heads, (?P<heads>.+?)\. If tails, (?P<tails>.+?)\.$",
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
    return templates

