from __future__ import annotations

import random
from typing import Any

MAX_BENCH_SIZE = 5
OPENING_HAND_SIZE = 7
PRIZE_CARD_COUNT = 6


def _opponent(actor: str) -> str:
    return "p2" if actor == "p1" else "p1"


def _build_zone_cards(actor: str, zone: str, count: int) -> list[dict[str, str]]:
    return [{"id": f"{actor}-{zone}-{index + 1}", "name": zone.title()} for index in range(max(0, count))]


def initialize_official_rules_context(
    state: dict[str, Any],
    opening_player: str = "p1",
) -> None:
    context = state.setdefault("official_rules", {})
    context.setdefault("opening_player", opening_player)
    context.setdefault("turn", 1)
    context.setdefault("active_player", opening_player)
    context.setdefault("first_turn_no_attack", True)
    context.setdefault("first_turn_no_supporter", True)
    context.setdefault("mulligans", {"p1": 0, "p2": 0})


def set_turn_context(state: dict[str, Any], actor: str, turn: int) -> None:
    initialize_official_rules_context(state)
    context = state["official_rules"]
    context["turn"] = turn
    context["active_player"] = actor


def validate_action_against_rules(
    state: dict[str, Any],
    actor: str,
    action_type: str,
) -> tuple[bool, str]:
    if "official_rules" not in state:
        return True, "official context not initialized"
    context = state.get("official_rules", {})
    opening_player = str(context.get("opening_player", "p1"))
    turn = int(context.get("turn", 1))
    first_turn = turn == 1 and actor == opening_player

    if action_type == "attack" and first_turn and bool(context.get("first_turn_no_attack", True)):
        return False, "opening player cannot attack on first turn"
    if action_type == "play_supporter" and first_turn and bool(context.get("first_turn_no_supporter", True)):
        return False, "opening player cannot play Supporter on first turn"

    player = state["players"][actor]
    if action_type == "retreat" and int(player.get("bench_size", 0)) <= 0:
        return False, "cannot retreat without a benched Pokémon"

    return True, "legal by official baseline rules"


def enforce_state_invariants(state: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for actor, player in state.get("players", {}).items():
        bench = player.get("bench")
        if isinstance(bench, list):
            requested_size = max(int(player.get("bench_size", len(bench))), len(bench))
            while len(bench) < requested_size:
                bench.append(
                    {
                        "card_id": f"{actor}-bench-invariant-{len(bench)+1}",
                        "card_name": "Bench Placeholder",
                        "hp": 120,
                        "max_hp": 120,
                        "status": [],
                        "energy_attached": 0,
                        "stage": "Basic",
                        "retreat_cost": 1,
                    }
                )
            if len(bench) > MAX_BENCH_SIZE:
                del bench[MAX_BENCH_SIZE:]
                events.append(f"{actor} bench list was capped at {MAX_BENCH_SIZE}.")
            player["bench_size"] = len(bench)

        bench_size = int(player.get("bench_size", 0))
        if bench_size > MAX_BENCH_SIZE:
            player["bench_size"] = MAX_BENCH_SIZE
            events.append(f"{actor} bench size was capped at {MAX_BENCH_SIZE}.")
        if bench_size < 0:
            player["bench_size"] = 0
            events.append(f"{actor} bench size was normalized to 0.")

        if isinstance(player.get("hand_cards"), list):
            player["hand_size"] = len(player["hand_cards"])

        prizes = int(player.get("prizes_remaining", PRIZE_CARD_COUNT))
        if isinstance(player.get("prize_cards"), list):
            prizes = len(player["prize_cards"])
        if prizes < 0:
            player["prizes_remaining"] = 0
            events.append(f"{actor} prizes were normalized to 0.")
        if prizes > PRIZE_CARD_COUNT:
            player["prizes_remaining"] = PRIZE_CARD_COUNT
            events.append(f"{actor} prizes were capped at {PRIZE_CARD_COUNT}.")
        else:
            player["prizes_remaining"] = prizes
    return events


def run_official_setup(
    state: dict[str, Any],
    seed: int | None = None,
    opening_player: str = "p1",
) -> list[str]:
    rng = random.Random(seed)
    initialize_official_rules_context(state, opening_player=opening_player)
    events: list[str] = []

    mulligans: dict[str, int] = {"p1": 0, "p2": 0}

    for actor, player in state.get("players", {}).items():
        player["hand_size"] = OPENING_HAND_SIZE
        player["hand_cards"] = _build_zone_cards(actor, "hand", OPENING_HAND_SIZE)
        events.append(f"{actor} drew opening hand to {OPENING_HAND_SIZE}.")
        player["prizes_remaining"] = PRIZE_CARD_COUNT
        player["prize_cards"] = _build_zone_cards(actor, "prize", PRIZE_CARD_COUNT)

        has_basic = bool(player.get("opening_has_basic", rng.choice([True, True, False])))
        while not has_basic:
            mulligans[actor] += 1
            player["hand_size"] = OPENING_HAND_SIZE
            player["hand_cards"] = _build_zone_cards(actor, "hand", OPENING_HAND_SIZE)
            has_basic = bool(rng.choice([True, False]))
        if mulligans[actor] > 0:
            events.append(f"{actor} took {mulligans[actor]} mulligan(s).")

        player["bench_size"] = min(MAX_BENCH_SIZE, max(0, int(player.get("bench_size", 0))))

    for actor in ("p1", "p2"):
        bonus = mulligans[_opponent(actor)]
        if bonus > 0:
            state["players"][actor]["hand_size"] = int(state["players"][actor].get("hand_size", 0)) + bonus
            state["players"][actor].setdefault("hand_cards", [])
            current = len(state["players"][actor]["hand_cards"])
            state["players"][actor]["hand_cards"].extend(
                _build_zone_cards(actor, "mulligan-bonus", bonus + current)[current:]
            )
            events.append(f"{actor} drew {bonus} card(s) from opponent mulligan(s).")

    state["official_rules"]["mulligans"] = mulligans
    events.extend(enforce_state_invariants(state))
    events.append("Official setup complete.")
    return events
