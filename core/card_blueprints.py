from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any

from core.text_compiler import compile_effect_text


@dataclass(frozen=True)
class CardBlueprint:
    """Reusable wording pattern that can spawn many cards via variables."""

    key: str
    name: str
    description: str
    text_template: str
    defaults: dict[str, Any] = field(default_factory=dict)

    def required_variables(self) -> list[str]:
        fields = {
            field_name
            for _, field_name, _, _ in Formatter().parse(self.text_template)
            if field_name
        }
        return sorted(fields)

    def render_text(self, variables: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        merged = dict(self.defaults)
        if variables:
            merged.update(variables)

        missing = [name for name in self.required_variables() if name not in merged]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"Missing variables for blueprint '{self.key}': {missing_list}")

        return self.text_template.format(**merged), merged


BLUEPRINTS: dict[str, CardBlueprint] = {
    "toxic_strike": CardBlueprint(
        key="toxic_strike",
        name="Toxic Strike",
        description="Fixed damage plus a status application.",
        text_template="{damage} damage. Your opponent's Active Pokémon is now {status}.",
        defaults={"damage": 30, "status": "Poisoned"},
    ),
    "volatile_strike": CardBlueprint(
        key="volatile_strike",
        name="Volatile Strike",
        description="Coin-flip branch with different outcomes.",
        text_template=(
            "{damage} damage. Flip a coin. "
            "If heads, this attack does {bonus} more damage. "
            "If tails, this Pokémon is now {self_status}."
        ),
        defaults={"damage": 20, "bonus": 40, "self_status": "Confused"},
    ),
    "tactical_draw": CardBlueprint(
        key="tactical_draw",
        name="Tactical Draw",
        description="Card draw + healing support pattern.",
        text_template="Draw {draw_count} cards. Heal {heal_amount} damage from this Pokémon.",
        defaults={"draw_count": 2, "heal_amount": 30},
    ),
}


def list_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "key": blueprint.key,
            "name": blueprint.name,
            "description": blueprint.description,
            "text_template": blueprint.text_template,
            "defaults": blueprint.defaults,
            "required_variables": blueprint.required_variables(),
        }
        for blueprint in BLUEPRINTS.values()
    ]


def build_card_from_blueprint(key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    blueprint = BLUEPRINTS.get(key)
    if blueprint is None:
        supported = ", ".join(sorted(BLUEPRINTS.keys()))
        raise ValueError(f"Unknown blueprint '{key}'. Supported blueprints: {supported}")

    rendered_text, merged_variables = blueprint.render_text(variables)
    compiled_program = compile_effect_text(rendered_text)

    return {
        "blueprint": {
            "key": blueprint.key,
            "name": blueprint.name,
            "description": blueprint.description,
        },
        "variables": merged_variables,
        "rendered_text": rendered_text,
        "compiled_program": compiled_program.to_dict(),
    }

