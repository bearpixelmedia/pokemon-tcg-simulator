"""Backward-compatible exports for legacy imports."""

from sim.game import (
    analyze_card_text,
    analyze_standard_coverage,
    analyze_template_recommendations,
    build_blueprint_card,
    build_legality_snapshot,
    run_data_pipeline_health,
    run_batch_simulations,
    run_full_yolo_pass,
    run_quality_gate_checks,
    run_simulation,
    verify_simulation_replay,
)

__all__ = [
    "analyze_card_text",
    "analyze_standard_coverage",
    "analyze_template_recommendations",
    "build_blueprint_card",
    "build_legality_snapshot",
    "run_data_pipeline_health",
    "run_batch_simulations",
    "run_full_yolo_pass",
    "run_quality_gate_checks",
    "run_simulation",
    "verify_simulation_replay",
]