"""Backward-compatible exports for legacy imports."""

from sim.game import analyze_card_text, analyze_standard_coverage, build_blueprint_card, run_simulation

__all__ = ["analyze_card_text", "analyze_standard_coverage", "build_blueprint_card", "run_simulation"]