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


def _draw_from_deck(player: dict[str, Any], count: int) -> list[dict[str, Any]]:
    deck = player.setdefault("deck_cards", [])
    drawn: list[dict[str, Any]] = []
    for _ in range(max(0, count)):
        if not deck:
            break
        drawn.append(deck.pop(0))
    return drawn


def _shuffle_into_deck(player: dict[str, Any], cards: list[dict[str, Any]], rng: random.Random) -> None:
    if not cards:
        return
    deck = player.setdefault("deck_cards", [])
    deck.extend(cards)
    rng.shuffle(deck)


def _has_basic_in_hand(player: dict[str, Any]) -> bool:
    for card in player.get("hand_cards", []):
        if isinstance(card, dict) and bool(card.get("is_basic", False)):
            return True
    return False


def _card_to_pokemon(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": card["id"],
        "card_name": card.get("name", "Pokemon"),
        "hp": 120,
        "max_hp": 120,
        "status": [],
        "energy_attached": 0,
        "attached_energy_cards": [],
        "attached_tool_cards": [],
        "stage": "Basic",
        "retreat_cost": 1,
        "prize_value": 1,
        "attacks": [{"name": "Default Attack", "cost": ["C"], "damage": 20}],
        "turns_in_play": 0,
        "just_played_this_turn": True,
        "evolved_this_turn": False,
    }


def _reset_player_zones_into_deck(player: dict[str, Any]) -> None:
    consolidated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _add_card(card: Any, fallback_name: str = "Card", supertype: str = "trainer", is_basic: bool = False) -> None:
        if not isinstance(card, dict):
            return
        card_id = card.get("id")
        if not isinstance(card_id, str) or not card_id or card_id in seen_ids:
            return
        consolidated.append(
            {
                "id": card_id,
                "name": card.get("name", fallback_name),
                "supertype": card.get("supertype", supertype),
                "is_basic": bool(card.get("is_basic", is_basic)),
            }
        )
        seen_ids.add(card_id)

    for zone_name in ("deck_cards", "hand_cards", "prize_cards", "discard_pile"):
        for card in player.get(zone_name, []):
            _add_card(card)

    active = player.get("active")
    if isinstance(active, dict):
        active_id = active.get("card_id")
        if isinstance(active_id, str) and active_id not in seen_ids:
            consolidated.append(
                {
                    "id": active_id,
                    "name": active.get("card_name", "Pokemon"),
                    "supertype": "pokemon",
                    "is_basic": True,
                }
            )
            seen_ids.add(active_id)
        for card in active.get("attached_energy_cards", []):
            _add_card(card, fallback_name="Basic Energy", supertype="energy")
        for card in active.get("attached_tool_cards", []):
            _add_card(card, fallback_name="Pokemon Tool", supertype="trainer")

    for bench_pokemon in player.get("bench", []):
        if not isinstance(bench_pokemon, dict):
            continue
        bench_id = bench_pokemon.get("card_id")
        if isinstance(bench_id, str) and bench_id not in seen_ids:
            consolidated.append(
                {
                    "id": bench_id,
                    "name": bench_pokemon.get("card_name", "Pokemon"),
                    "supertype": "pokemon",
                    "is_basic": True,
                }
            )
            seen_ids.add(bench_id)
        for card in bench_pokemon.get("attached_energy_cards", []):
            _add_card(card, fallback_name="Basic Energy", supertype="energy")
        for card in bench_pokemon.get("attached_tool_cards", []):
            _add_card(card, fallback_name="Pokemon Tool", supertype="trainer")

    player["deck_cards"] = consolidated
    player["hand_cards"] = []
    player["prize_cards"] = []
    player["discard_pile"] = []
    player["active"] = None
    player["bench"] = []
    player["hand_size"] = 0
    player["bench_size"] = 0


def _promote_opening_pokemon(player: dict[str, Any]) -> None:
    hand = player.setdefault("hand_cards", [])
    basic_indices = [index for index, card in enumerate(hand) if bool(card.get("is_basic", False))]
    if not basic_indices:
        return
    active_card = hand.pop(basic_indices[0])
    player["active"] = _card_to_pokemon(active_card)

    bench_target = min(MAX_BENCH_SIZE, int(player.get("bench_size", 0)))
    bench_cards: list[dict[str, Any]] = []
    scan_index = 0
    while len(bench_cards) < bench_target and scan_index < len(hand):
        card = hand[scan_index]
        if bool(card.get("is_basic", False)):
            bench_cards.append(hand.pop(scan_index))
            continue
        scan_index += 1

    player["bench"] = [_card_to_pokemon(card) for card in bench_cards]
    player["bench_size"] = len(player["bench"])
    player["hand_size"] = len(hand)


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
    flags = player.setdefault("turn_flags", {})
    active = player.get("active", {}) if isinstance(player.get("active"), dict) else {}
    bench = player.get("bench", [])
    bench_size = len(bench) if isinstance(bench, list) else int(player.get("bench_size", 0))

    if action_type == "retreat" and bench_size <= 0:
        return False, "cannot retreat without a benched Pokémon"
    if action_type == "retreat" and any(status in {"Asleep", "Paralyzed"} for status in active.get("status", [])):
        return False, "active status prevents retreat"
    if action_type == "play_supporter" and bool(flags.get("supporter_played", False)):
        return False, "supporter already played this turn"
    if action_type == "play_stadium" and bool(flags.get("stadium_played", False)):
        return False, "stadium already played this turn"
    if action_type == "attach_tool" and bool(flags.get("tool_attached", False)):
        return False, "tool already attached this turn"
    if action_type == "attach_tool" and bool(active.get("tool_attached", False)):
        return False, "active pokemon already has a tool attached"
    if action_type == "bench_pokemon" and bench_size >= MAX_BENCH_SIZE:
        return False, f"bench is full ({MAX_BENCH_SIZE})"
    if action_type == "evolve" and bool(active.get("just_played_this_turn", False)):
        return False, "pokemon cannot evolve on the turn it was played"
    if action_type == "evolve" and bool(active.get("evolved_this_turn", False)):
        return False, "pokemon already evolved this turn"

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
        _reset_player_zones_into_deck(player)
        rng.shuffle(player.setdefault("deck_cards", []))
        player["hand_cards"] = _draw_from_deck(player, OPENING_HAND_SIZE)
        player["hand_size"] = len(player["hand_cards"])
        events.append(f"{actor} drew opening hand to {player['hand_size']}.")

        forced_opening_has_basic = player.pop("opening_has_basic", None)
        def _opening_has_basic() -> bool:
            nonlocal forced_opening_has_basic
            if forced_opening_has_basic is None:
                return _has_basic_in_hand(player)
            forced_value = bool(forced_opening_has_basic)
            forced_opening_has_basic = None
            return forced_value

        attempt_guard = 0
        while not _opening_has_basic():
            mulligans[actor] += 1
            _shuffle_into_deck(player, player.get("hand_cards", []), rng)
            player["hand_cards"] = _draw_from_deck(player, OPENING_HAND_SIZE)
            player["hand_size"] = len(player["hand_cards"])
            attempt_guard += 1
            if attempt_guard >= 200:
                # Hard stop for malformed decks with no basic Pokémon.
                player.setdefault("hand_cards", []).append(
                    {"id": f"{actor}-forced-basic", "name": "Forced Basic", "supertype": "pokemon", "is_basic": True}
                )
                player["hand_size"] = len(player["hand_cards"])
                events.append(f"{actor} setup guard injected a Basic Pokémon after repeated mulligans.")
                break

        if mulligans[actor] > 0:
            events.append(f"{actor} took {mulligans[actor]} mulligan(s).")

        player["prize_cards"] = _draw_from_deck(player, PRIZE_CARD_COUNT)
        player["prizes_remaining"] = len(player["prize_cards"])
        player["discard_pile"] = list(player.get("discard_pile", []))
        _promote_opening_pokemon(player)

    for actor in ("p1", "p2"):
        bonus = mulligans[_opponent(actor)]
        if bonus > 0:
            bonus_cards = _draw_from_deck(state["players"][actor], bonus)
            state["players"][actor].setdefault("hand_cards", []).extend(bonus_cards)
            state["players"][actor]["hand_size"] = len(state["players"][actor]["hand_cards"])
            events.append(f"{actor} drew {bonus} card(s) from opponent mulligan(s).")

    state["official_rules"]["mulligans"] = mulligans
    events.extend(enforce_state_invariants(state))
    events.append("Official setup complete.")
    return events
