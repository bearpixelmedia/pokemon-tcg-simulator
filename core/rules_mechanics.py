from __future__ import annotations

from typing import Any


def create_active_pokemon(
    hp: int = 120,
    stage: str = "Basic",
    energy_attached: int = 1,
    retreat_cost: int = 1,
) -> dict[str, Any]:
    return {
        "hp": hp,
        "max_hp": hp,
        "status": [],
        "energy_attached": energy_attached,
        "stage": stage,
        "retreat_cost": retreat_cost,
    }


def attempt_retreat(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    events: list[str] = []
    player = state["players"][actor]
    active = player["active"]
    statuses = set(active.get("status", []))

    if player.get("bench_size", 0) <= 0:
        return False, [f"{actor} cannot retreat without Benched Pokémon."]
    if "Asleep" in statuses or "Paralyzed" in statuses:
        return False, [f"{actor} cannot retreat while Asleep or Paralyzed."]

    retreat_cost = int(active.get("retreat_cost", 1))
    if int(active.get("energy_attached", 0)) < retreat_cost:
        return False, [f"{actor} lacks enough Energy to retreat (cost {retreat_cost})."]

    active["energy_attached"] = max(0, int(active.get("energy_attached", 0)) - retreat_cost)
    active["status"] = []
    events.append(f"{actor} retreated and paid {retreat_cost} Energy.")
    return True, events


def attempt_evolve(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    active = state["players"][actor]["active"]
    stage = active.get("stage", "Basic")
    if stage == "Basic":
        active["stage"] = "Stage1"
    elif stage == "Stage1":
        active["stage"] = "Stage2"
    else:
        return False, [f"{actor}'s Active Pokémon cannot evolve further."]

    active["status"] = []
    heal_amount = 20
    active["hp"] = min(active["max_hp"], active["hp"] + heal_amount)
    return True, [f"{actor} evolved Active Pokémon to {active['stage']} and healed {heal_amount}."]


def attempt_devolve(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    active = state["players"][actor]["active"]
    stage = active.get("stage", "Basic")
    if stage == "Stage2":
        active["stage"] = "Stage1"
    elif stage == "Stage1":
        active["stage"] = "Basic"
    else:
        return False, [f"{actor}'s Active Pokémon cannot devolve further."]
    return True, [f"{actor} devolved Active Pokémon to {active['stage']}."]


def resolve_knockouts_and_prizes(state: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for owner, opponent in (("p1", "p2"), ("p2", "p1")):
        owner_active = state["players"][owner]["active"]
        if int(owner_active.get("hp", 0)) > 0:
            continue

        state["players"][owner]["knockouts"] = int(state["players"][owner].get("knockouts", 0)) + 1
        events.append(f"{owner}'s Active Pokémon was Knocked Out.")

        if int(state["players"][opponent].get("prizes_remaining", 0)) > 0:
            state["players"][opponent]["prizes_remaining"] -= 1
            events.append(
                f"{opponent} took a Prize card ({state['players'][opponent]['prizes_remaining']} remaining)."
            )

        bench_size = int(state["players"][owner].get("bench_size", 0))
        if bench_size > 0:
            state["players"][owner]["bench_size"] = bench_size - 1
            state["players"][owner]["active"] = create_active_pokemon()
            events.append(f"{owner} promoted a Benched Pokémon to Active.")
        else:
            events.append(f"{owner} has no Benched Pokémon left to promote.")

    return events

