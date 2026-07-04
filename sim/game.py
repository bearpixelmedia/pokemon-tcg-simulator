from __future__ import annotations

from typing import Any

from core.card_blueprints import build_card_from_blueprint
from core.standard_coverage import run_standard_coverage_analysis
from core.text_compiler import compile_effect_text, supported_templates
from core.template_mining import mine_unresolved_templates
from core.turn_engine import run_turn_based_simulation, verify_seed_replay
from core.yolo_pipeline import run_yolo_pipeline


def analyze_card_text(text: str) -> dict[str, Any]:
    program = compile_effect_text(text)
    return {
        "compiler": {
            "supported_templates": supported_templates(),
        },
        "program": program.to_dict(),
    }


def build_blueprint_card(blueprint_key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_card_from_blueprint(blueprint_key, variables)


def analyze_standard_coverage(
    limit_cards: int | None = 250,
    marks: tuple[str, ...] = ("H", "I", "J"),
    include_examples: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    return run_standard_coverage_analysis(
        marks=marks,
        limit_cards=limit_cards,
        include_examples=include_examples,
        force_refresh=force_refresh,
    )


def analyze_template_recommendations(
    limit_cards: int | None = 250,
    marks: tuple[str, ...] = ("H", "I", "J"),
    include_examples: bool = False,
    force_refresh: bool = False,
) -> dict[str, Any]:
    coverage = run_standard_coverage_analysis(
        marks=marks,
        limit_cards=limit_cards,
        include_examples=include_examples,
        force_refresh=force_refresh,
    )
    recommendations = mine_unresolved_templates(coverage, top_n=30, sample_size=4)
    return {
        "coverage_summary": coverage.get("summary", {}),
        "card_summary": coverage.get("card_summary", {}),
        "recommendations": recommendations,
    }


def run_full_yolo_pass(
    limit_cards: int | None = 350,
    marks: tuple[str, ...] = ("H", "I", "J"),
    include_examples: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    return run_yolo_pipeline(
        limit_cards=limit_cards,
        marks=marks,
        include_examples=include_examples,
        force_refresh=force_refresh,
    )


def run_simulation(turn_limit: int = 10, seed: int | None = None) -> dict[str, Any]:
    return run_turn_based_simulation(turn_limit=turn_limit, seed=seed)


def verify_simulation_replay(turn_limit: int = 10, seed: int | None = None) -> dict[str, Any]:
    return verify_seed_replay(turn_limit=turn_limit, seed=seed)

