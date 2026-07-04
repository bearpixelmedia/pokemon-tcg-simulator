"""Backward-compatible exports for legacy imports."""

from sim.game import (
    analyze_card_text,
    analyze_standard_coverage,
    analyze_template_recommendations,
    build_blueprint_card,
    run_full_yolo_pass,
    run_simulation,
    verify_simulation_replay,
)

__all__ = [
    "analyze_card_text",
    "analyze_standard_coverage",
    "analyze_template_recommendations",
    "build_blueprint_card",
    "run_full_yolo_pass",
    "run_simulation",
    "verify_simulation_replay",
]