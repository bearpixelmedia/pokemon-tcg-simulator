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
