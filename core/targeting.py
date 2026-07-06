from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TargetValidationResult:
    valid: bool
    reason: str = ""


def validate_target_selector(state: dict[str, Any], actor: str, selector: str) -> TargetValidationResult:
    def bench_count(player: dict[str, Any]) -> int:
        bench = player.get("bench")
        if isinstance(bench, list):
            return len(bench)
        return int(player.get("bench_size", 0))

    if selector in {"self_active", "opponent_active", "self_player", "opponent_player"}:
        return TargetValidationResult(True, "core selector")
    if selector == "self_bench":
        return TargetValidationResult(bench_count(state["players"][actor]) > 0, "requires at least one benched Pokémon")
    if selector == "opponent_bench":
        opponent = "p2" if actor == "p1" else "p1"
        return TargetValidationResult(
            bench_count(state["players"][opponent]) > 0,
            "opponent must have benched Pokémon",
        )
    if selector in {"any_pokemon", "self_pokemon", "opponent_pokemon"}:
        return TargetValidationResult(True, "broad selector")
    return TargetValidationResult(False, f"unsupported selector '{selector}'")


def validate_target_count(requested: int, available: int, allow_less: bool) -> TargetValidationResult:
    if requested <= 0:
        return TargetValidationResult(False, "requested target count must be positive")
    if requested <= available:
        return TargetValidationResult(True, "enough legal targets")
    if allow_less and available > 0:
        return TargetValidationResult(True, "allowed to choose fewer targets")
    return TargetValidationResult(False, "not enough legal targets")
