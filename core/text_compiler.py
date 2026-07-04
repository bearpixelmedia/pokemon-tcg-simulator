from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from core.effect_types import EffectOperation, EffectProgram

_STATUS_MAP = {
    "poisoned": "Poisoned",
    "burned": "Burned",
    "paralyzed": "Paralyzed",
    "asleep": "Asleep",
    "confused": "Confused",
}


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


def _damage_to_active(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="deal_damage",
            params={"target": "opponent_active", "amount": int(match.group("damage"))},
        )
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
    return [
        EffectOperation(
            op="deal_damage",
            params={"target": "opponent_bench", "amount": int(match.group("damage"))},
        )
    ]


def _draw_cards(match: re.Match[str]) -> list[EffectOperation]:
    return [
        EffectOperation(
            op="draw_cards",
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
    return [
        EffectOperation(op="apply_status", params={"target": "self_active", "status": status})
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
            r"^(?:This attack does )?(?P<damage>\d+) damage(?: to your opponent's Active Pokémon)?\.$",
            re.IGNORECASE,
        ),
        builder=_damage_to_active,
    ),
    TextTemplate(
        name="damage_bench",
        description="Deal fixed damage to one Benched Pokémon.",
        pattern=re.compile(
            r"^This attack does (?P<damage>\d+) damage to 1 of your opponent's Benched Pokémon\.$",
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
        name="heal_self",
        description="Heal your own Active Pokémon.",
        pattern=re.compile(r"^Heal (?P<amount>\d+) damage from this Pokémon\.$", re.IGNORECASE),
        builder=_heal_self,
    ),
    TextTemplate(
        name="status_opponent",
        description="Apply a status condition to opponent's Active Pokémon.",
        pattern=re.compile(
            r"^Your opponent's Active Pokémon is now (?P<status>Poisoned|Burned|Paralyzed|Asleep|Confused)\.$",
            re.IGNORECASE,
        ),
        builder=_status_to_opponent,
    ),
    TextTemplate(
        name="status_self",
        description="Apply a status condition to your own Active Pokémon.",
        pattern=re.compile(
            r"^This Pokémon is now (?P<status>Poisoned|Burned|Paralyzed|Asleep|Confused)\.$",
            re.IGNORECASE,
        ),
        builder=_status_to_self,
    ),
]

COIN_FLIP_TEMPLATE = re.compile(
    r"^Flip a coin\. If heads, (?P<heads>.+?)\. If tails, (?P<tails>.+?)\.$",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list[str]:
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

        merged.append(current)
        index += 1

    return merged


def _compile_clause(clause: str) -> tuple[list[EffectOperation], str | None]:
    clause = clause.strip()

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

    return [], None


def compile_effect_text(text: str) -> EffectProgram:
    normalized = normalize_card_text(text)
    if not normalized:
        return EffectProgram(source_text=text, unresolved_text="")

    clauses = _merge_coin_flip_sequences(_split_sentences(normalized))

    operations: list[EffectOperation] = []
    template_names: list[str] = []
    unresolved_clauses: list[str] = []

    for clause in clauses:
        clause_operations, template_name = _compile_clause(clause)
        if template_name is None:
            unresolved_clauses.append(clause)
            continue
        operations.extend(clause_operations)
        template_names.append(template_name)

    return EffectProgram(
        source_text=normalized,
        operations=operations,
        template_name=" + ".join(template_names) if template_names else None,
        unresolved_text=" ".join(unresolved_clauses) if unresolved_clauses else None,
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

