from __future__ import annotations

import re

from core.effect_types import EffectOperation


def resolve_script_fallback(clause: str) -> tuple[list[EffectOperation], str] | None:
    text = clause.strip()

    match = re.fullmatch(
        r"Search your deck for up to (?P<count>\d+) (?P<descriptor>.+?) Energy cards and attach them to 1 of your Pokémon\.",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return (
            [
                EffectOperation(
                    op="script_hook",
                    params={
                        "hook_id": "attach-energy-from-deck",
                        "count": int(match.group("count")),
                        "descriptor": match.group("descriptor"),
                    },
                )
            ],
            "script_fallback_attach_energy_from_deck",
        )

    match = re.fullmatch(
        r"During your opponent's next turn, prevent all damage done to this Pokémon by attacks\.",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return (
            [
                EffectOperation(
                    op="script_hook",
                    params={"hook_id": "prevent-all-damage-next-turn", "target": "self_active"},
                )
            ],
            "script_fallback_prevent_all_damage",
        )

    match = re.fullmatch(
        r"Discard your hand and draw (?P<count>\d+) cards\.",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return (
            [
                EffectOperation(
                    op="script_hook",
                    params={
                        "hook_id": "discard-hand-and-draw",
                        "draw_count": int(match.group("count")),
                    },
                )
            ],
            "script_fallback_discard_draw",
        )

    return None

