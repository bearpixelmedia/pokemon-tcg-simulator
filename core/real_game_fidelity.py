from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.effect_types import EffectOperation, EffectProgram
from core.effects import apply_effect_program, create_demo_state
from core.rules_mechanics import resolve_knockouts_and_prizes


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _player_snapshot(player: dict[str, Any]) -> dict[str, Any]:
    active = player.get("active", {})
    bench = player.get("bench", [])
    bench_size = len(bench) if isinstance(bench, list) else int(player.get("bench_size", 0))
    active_status = list(active.get("status", [])) if isinstance(active, dict) else []
    return {
        "active_card_id": active.get("card_id") if isinstance(active, dict) else None,
        "active_hp": int(active.get("hp", 0)) if isinstance(active, dict) else 0,
        "active_status": active_status,
        "prizes_remaining": int(player.get("prizes_remaining", 0)),
        "hand_size": int(player.get("hand_size", 0)),
        "bench_size": bench_size,
        "out_of_pokemon": bool(player.get("out_of_pokemon", False)),
    }


def state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "players": {
            "p1": _player_snapshot(state["players"]["p1"]),
            "p2": _player_snapshot(state["players"]["p2"]),
        }
    }


def run_real_game_trace(trace: dict[str, Any]) -> dict[str, Any]:
    state = create_demo_state()
    initial_state = trace.get("initial_state")
    if isinstance(initial_state, dict):
        _deep_merge(state, initial_state)

    turn_results: list[dict[str, Any]] = []
    for index, turn in enumerate(trace.get("turns", []), start=1):
        actor = str(turn.get("actor", "p1"))
        operations: list[EffectOperation] = []
        for op in turn.get("operations", []):
            operations.append(EffectOperation(op=str(op.get("op", "unknown")), params=op.get("params", {})))

        events: list[str] = []
        if operations:
            program = EffectProgram(source_text=f"{trace.get('name', 'real-game-trace')}:turn:{index}", operations=operations)
            events.extend(apply_effect_program(program, state, actor=actor))

        if bool(turn.get("resolve_knockouts", True)):
            events.extend(resolve_knockouts_and_prizes(state))

        turn_results.append(
            {
                "turn": index,
                "actor": actor,
                "events": events,
                "snapshot": state_snapshot(state),
            }
        )

    return {
        "name": trace.get("name", "unnamed-trace"),
        "turns": turn_results,
        "final_snapshot": state_snapshot(state),
    }


def run_real_game_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    result = run_real_game_trace(payload)
    result["fixture_path"] = str(fixture_path)
    return result


def _collect_subset_mismatches(expected: Any, actual: Any, path: str = "root") -> list[str]:
    mismatches: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected dict"]
        for key, value in expected.items():
            if key not in actual:
                mismatches.append(f"{path}: missing key '{key}'")
                continue
            mismatches.extend(_collect_subset_mismatches(value, actual[key], f"{path}.{key}"))
        return mismatches
    if isinstance(expected, list):
        if expected != actual:
            mismatches.append(f"{path}: expected {expected!r}, got {actual!r}")
        return mismatches
    if expected != actual:
        mismatches.append(f"{path}: expected {expected!r}, got {actual!r}")
    return mismatches


def run_real_game_fixture_suite(path: str | Path = "tests/fixtures/real_games") -> dict[str, Any]:
    suite_path = Path(path)
    if not suite_path.exists():
        return {"path": str(suite_path), "count": 0, "passed": False, "cases": []}

    case_results: list[dict[str, Any]] = []
    for fixture_path in sorted(suite_path.glob("*.json")):
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        result = run_real_game_trace(payload)
        mismatches: list[str] = []
        for turn_index, fixture_turn in enumerate(payload.get("turns", []), start=1):
            expected_snapshot = fixture_turn.get("expected_snapshot")
            if expected_snapshot is None:
                continue
            actual_snapshot = result["turns"][turn_index - 1]["snapshot"]
            mismatches.extend(
                _collect_subset_mismatches(
                    expected_snapshot,
                    actual_snapshot,
                    path=f"{fixture_path.name}.turn{turn_index}",
                )
            )
        case_results.append(
            {
                "name": payload.get("name", fixture_path.stem),
                "fixture_path": str(fixture_path),
                "turn_count": len(result["turns"]),
                "passed": len(mismatches) == 0,
                "mismatches": mismatches,
            }
        )

    passed = bool(case_results) and all(case["passed"] for case in case_results)
    return {
        "path": str(suite_path),
        "count": len(case_results),
        "passed": passed,
        "cases": case_results,
    }
