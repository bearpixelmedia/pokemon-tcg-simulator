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
    ko_owners: list[str] = []
    for owner in ("p1", "p2"):
        active = state["players"][owner].get("active", {})
        if not isinstance(active, dict):
            continue
        if bool(active.get("no_active_placeholder", False)):
            continue
        if int(active.get("hp", 0)) <= 0:
            ko_owners.append(owner)

    if not ko_owners:
        return events

    # Resolve all knockout packets first so simultaneous KOs are deterministic.
    knockout_packets: dict[str, dict[str, Any]] = {}
    for owner in ko_owners:
        owner_player = state["players"][owner]
        opponent = "p2" if owner == "p1" else "p1"
        owner_active = owner_player["active"]
        energy_cards = list(owner_active.get("attached_energy_cards", []))
        tool_cards = list(owner_active.get("attached_tool_cards", []))
        knocked_out_card = dict(owner_active)
        knocked_out_card["attached_energy_cards"] = []
        knocked_out_card["attached_tool_cards"] = []
        knocked_out_card["energy_attached"] = 0
        knockout_packets[owner] = {
            "opponent": opponent,
            "knocked_out_card": knocked_out_card,
            "energy_cards": energy_cards,
            "tool_cards": tool_cards,
            "prize_value": max(1, int(owner_active.get("prize_value", 1))),
        }

    for owner in ko_owners:
        owner_player = state["players"][owner]
        packet = knockout_packets[owner]
        owner_player["knockouts"] = int(owner_player.get("knockouts", 0)) + 1
        owner_player.setdefault("discard_pile", []).append(packet["knocked_out_card"])
        owner_player.setdefault("discard_pile", []).extend(packet["energy_cards"])
        owner_player.setdefault("discard_pile", []).extend(packet["tool_cards"])
        events.append(f"{owner}'s Active Pokémon was Knocked Out.")

    for owner in ko_owners:
        packet = knockout_packets[owner]
        opponent = packet["opponent"]
        opponent_player = state["players"][opponent]
        prizes_to_take = min(packet["prize_value"], len(opponent_player.get("prize_cards", [])))
        for _ in range(prizes_to_take):
            prize_card = opponent_player["prize_cards"].pop(0)
            opponent_player.setdefault("hand_cards", []).append(prize_card)
        opponent_player["hand_size"] = len(opponent_player.get("hand_cards", []))
        opponent_player["prizes_remaining"] = len(opponent_player.get("prize_cards", []))
        if prizes_to_take > 0:
            events.append(
                f"{opponent} took {prizes_to_take} Prize card(s) ({opponent_player['prizes_remaining']} remaining)."
            )

    for owner in ko_owners:
        owner_player = state["players"][owner]
        bench = owner_player.get("bench", [])
        if bench:
            promoted = bench.pop(0)
            promoted["just_played_this_turn"] = False
            owner_player["active"] = promoted
            owner_player["bench_size"] = len(bench)
            owner_player["out_of_pokemon"] = False
            events.append(f"{owner} promoted {promoted.get('card_name', 'a Benched Pokémon')} to Active.")
        else:
            placeholder = create_active_pokemon(
                hp=0,
                energy_attached=0,
                prize_value=0,
                card_id=f"{owner}-no-active",
                card_name="No Active Pokémon",
            )
            placeholder["no_active_placeholder"] = True
            owner_player["active"] = placeholder
            owner_player["bench_size"] = 0
            owner_player["out_of_pokemon"] = True
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

