from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.effect_types import EffectOperation, EffectProgram
from core.effects import apply_effect_program, create_demo_state


def run_golden_case(case: dict[str, Any]) -> dict[str, Any]:
    state = create_demo_state()
    actor = case.get("actor", "p1")
    operations = [EffectOperation(op=item["op"], params=item.get("params", {})) for item in case.get("operations", [])]
    program = EffectProgram(source_text=case.get("name", "golden-case"), operations=operations)
    events = apply_effect_program(program, state, actor=actor)
    return {"name": case.get("name", "unnamed"), "events": events, "state": state}


def run_golden_suite(path: str) -> dict[str, Any]:
    suite_path = Path(path)
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    results = [run_golden_case(case) for case in payload.get("cases", [])]
    return {
        "path": str(suite_path),
        "count": len(results),
        "results": results,
    }
