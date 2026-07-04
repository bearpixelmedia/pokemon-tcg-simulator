from __future__ import annotations

from typing import Any

from core.card_blueprints import build_card_from_blueprint
from core.legality_snapshot import build_standard_legality_snapshot
from core.quality_gates import run_quality_gates
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


def run_batch_simulations(
    games: int = 20,
    turn_limit: int = 10,
    base_seed: int | None = None,
) -> dict[str, Any]:
    if games <= 0:
        return {"error": "games must be positive"}

    summaries: list[dict[str, Any]] = []
    win_counter = {"You": 0, "AI": 0, "Draw": 0}
    total_turns = 0
    total_you_hp = 0
    total_ai_hp = 0

    for offset in range(games):
        seed = (base_seed + offset) if base_seed is not None else None
        result = run_turn_based_simulation(turn_limit=turn_limit, seed=seed)
        winner = result["winner"]
        win_counter[winner] = win_counter.get(winner, 0) + 1
        total_turns += int(result["turns"])
        total_you_hp += int(result["final_hp"]["you"])
        total_ai_hp += int(result["final_hp"]["ai"])
        summaries.append(
            {
                "index": offset + 1,
                "seed": result["replay"]["seed"],
                "winner": winner,
                "turns": result["turns"],
                "final_hp": result["final_hp"],
                "state_checksum": result["replay"]["state_checksum"],
            }
        )

    return {
        "games": games,
        "turn_limit": turn_limit,
        "base_seed": base_seed,
        "wins": win_counter,
        "win_rates": {
            key: round((value / games) * 100, 2) for key, value in win_counter.items()
        },
        "averages": {
            "turns": round(total_turns / games, 2),
            "final_you_hp": round(total_you_hp / games, 2),
            "final_ai_hp": round(total_ai_hp / games, 2),
        },
        "samples": summaries[: min(25, len(summaries))],
    }


def build_legality_snapshot(
    as_of_date: str | None = None,
    marks: tuple[str, ...] = ("H", "I", "J"),
    waiting_days: int = 14,
    limit_cards: int | None = 500,
) -> dict[str, Any]:
    return build_standard_legality_snapshot(
        as_of_date=as_of_date,
        marks=marks,
        waiting_days=waiting_days,
        limit_cards=limit_cards,
    )


def run_quality_gate_checks(
    coverage_limit_cards: int | None = 250,
    legality_limit_cards: int | None = 300,
    marks: tuple[str, ...] = ("H", "I", "J"),
    update_baseline: bool = False,
    force_refresh: bool = False,
) -> dict[str, Any]:
    return run_quality_gates(
        coverage_limit_cards=coverage_limit_cards,
        legality_limit_cards=legality_limit_cards,
        marks=marks,
        update_baseline=update_baseline,
        force_refresh=force_refresh,
    )

