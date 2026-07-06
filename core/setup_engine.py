from __future__ import annotations

from typing import Any

from core.battle_state import ensure_battle_state
from core.official_rules import run_official_setup

def run_setup_phase(state: dict[str, Any], seed: int | None = None) -> list[str]:
    ensure_battle_state(state)
    events = run_official_setup(state, seed=seed, opening_player="p1")
    events.append("Setup phase complete.")
    return events
