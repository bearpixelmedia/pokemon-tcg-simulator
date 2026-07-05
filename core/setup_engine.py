from __future__ import annotations

import random
from typing import Any


def run_setup_phase(state: dict[str, Any], seed: int | None = None) -> list[str]:
    rng = random.Random(seed)
    events: list[str] = []
    for actor, player in state.get("players", {}).items():
        hand_size = int(player.get("hand_size", 0))
        if hand_size == 0:
            player["hand_size"] = 7
            events.append(f"{actor} drew opening hand to 7.")
        if int(player.get("prizes_remaining", 0)) <= 0:
            player["prizes_remaining"] = 6
            events.append(f"{actor} set 6 prize cards.")

        mulligan_flip = rng.choice([True, False])
        if mulligan_flip and int(player.get("bench_size", 0)) == 0:
            player["hand_size"] = 7
            events.append(f"{actor} mulliganed and redrew 7 cards.")
    events.append("Setup phase complete.")
    return events
