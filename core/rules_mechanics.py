from __future__ import annotations

from typing import Any

from core.battle_state import ensure_battle_state


def create_active_pokemon(
    hp: int = 120,
    stage: str = "Basic",
    energy_attached: int = 1,
    retreat_cost: int = 1,
    prize_value: int = 1,
    card_id: str | None = None,
    card_name: str | None = None,
) -> dict[str, Any]:
    if card_id is None:
        card_id = f"pokemon-{stage.lower()}-{hp}-{energy_attached}"
    if card_name is None:
        card_name = "Pokemon"
    return {
        "card_id": card_id,
        "card_name": card_name,
        "hp": hp,
        "max_hp": hp,
        "status": [],
        "energy_attached": energy_attached,
        "attached_energy_cards": [],
        "attached_tool_cards": [],
        "stage": stage,
        "retreat_cost": retreat_cost,
        "prize_value": max(1, prize_value),
        "attacks": [{"name": "Default Attack", "cost": ["C"], "damage": 20}],
        "turns_in_play": 0,
        "just_played_this_turn": False,
        "evolved_this_turn": False,
    }


def attempt_retreat(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    ensure_battle_state(state)
    events: list[str] = []
    player = state["players"][actor]
    active = player["active"]
    bench = player.get("bench", [])
    statuses = set(active.get("status", []))

    if not bench:
        return False, [f"{actor} cannot retreat without Benched Pokémon."]
    if "Asleep" in statuses or "Paralyzed" in statuses:
        return False, [f"{actor} cannot retreat while Asleep or Paralyzed."]

    retreat_cost = int(active.get("retreat_cost", 1))
    if int(active.get("energy_attached", 0)) < retreat_cost:
        return False, [f"{actor} lacks enough Energy to retreat (cost {retreat_cost})."]

    active["energy_attached"] = max(0, int(active.get("energy_attached", 0)) - retreat_cost)
    attached = list(active.get("attached_energy_cards", []))
    if retreat_cost > 0 and attached:
        active["attached_energy_cards"] = attached[:-retreat_cost] if retreat_cost < len(attached) else []
    outgoing = player["active"]
    outgoing["status"] = []
    promoted = bench.pop(0)
    player["bench"].append(outgoing)
    player["active"] = promoted
    player["bench_size"] = len(player["bench"])
    events.append(f"{actor} retreated and paid {retreat_cost} Energy (promoted {promoted.get('card_name', 'Benched Pokémon')}).")
    return True, events


def attempt_evolve(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    ensure_battle_state(state)
    active = state["players"][actor]["active"]
    if bool(active.get("just_played_this_turn", False)):
        return False, [f"{actor}'s Active Pokémon was played this turn and cannot evolve."]
    if bool(active.get("evolved_this_turn", False)):
        return False, [f"{actor}'s Active Pokémon already evolved this turn."]
    stage = active.get("stage", "Basic")
    if stage == "Basic":
        active["stage"] = "Stage1"
    elif stage == "Stage1":
        active["stage"] = "Stage2"
    else:
        return False, [f"{actor}'s Active Pokémon cannot evolve further."]

    active["status"] = []
    active["evolved_this_turn"] = True
    heal_amount = 20
    active["hp"] = min(active["max_hp"], active["hp"] + heal_amount)
    return True, [f"{actor} evolved Active Pokémon to {active['stage']} and healed {heal_amount}."]


def attempt_devolve(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    ensure_battle_state(state)
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
    ensure_battle_state(state)
    events: list[str] = []
    for owner, opponent in (("p1", "p2"), ("p2", "p1")):
        owner_player = state["players"][owner]
        opponent_player = state["players"][opponent]
        owner_active = state["players"][owner]["active"]
        if int(owner_active.get("hp", 0)) > 0:
            continue

        owner_player["knockouts"] = int(owner_player.get("knockouts", 0)) + 1
        owner_player.setdefault("discard_pile", []).append(owner_active)
        owner_player.setdefault("discard_pile", []).extend(owner_active.get("attached_energy_cards", []))
        owner_player.setdefault("discard_pile", []).extend(owner_active.get("attached_tool_cards", []))
        events.append(f"{owner}'s Active Pokémon was Knocked Out.")

        prize_value = max(1, int(owner_active.get("prize_value", 1)))
        if int(opponent_player.get("prizes_remaining", 0)) > 0:
            prizes_to_take = min(prize_value, len(opponent_player.get("prize_cards", [])))
            for _ in range(prizes_to_take):
                prize_card = opponent_player["prize_cards"].pop(0)
                opponent_player.setdefault("hand_cards", []).append(prize_card)
            opponent_player["hand_size"] = len(opponent_player.get("hand_cards", []))
            opponent_player["prizes_remaining"] = len(opponent_player.get("prize_cards", []))
            events.append(
                f"{opponent} took {prizes_to_take} Prize card(s) ({opponent_player['prizes_remaining']} remaining)."
            )

        bench = owner_player.get("bench", [])
        if bench:
            promoted = bench.pop(0)
            owner_player["active"] = promoted
            owner_player["bench_size"] = len(bench)
            events.append(f"{owner} promoted {promoted.get('card_name', 'a Benched Pokémon')} to Active.")
        else:
            owner_player["active"] = create_active_pokemon(hp=0, energy_attached=0, card_name="No Active Pokémon")
            owner_player["bench_size"] = 0
            events.append(f"{owner} has no Benched Pokémon left to promote.")

    return events


def begin_turn_state_update(state: dict[str, Any], actor: str) -> None:
    ensure_battle_state(state)
    player = state["players"][actor]
    active = player.get("active", {})
    active["turns_in_play"] = int(active.get("turns_in_play", 0)) + 1
    active["evolved_this_turn"] = False
    active["just_played_this_turn"] = False
    for bench_pokemon in player.get("bench", []):
        bench_pokemon["turns_in_play"] = int(bench_pokemon.get("turns_in_play", 0)) + 1
        bench_pokemon["evolved_this_turn"] = False
        bench_pokemon["just_played_this_turn"] = False

