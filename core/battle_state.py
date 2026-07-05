from __future__ import annotations

from typing import Any

MAX_DECK_SIZE = 60


def _placeholder_card(prefix: str, actor: str, index: int) -> dict[str, str]:
    return {"id": f"{actor}-{prefix}-{index}", "name": f"{prefix}-{index}"}


def _placeholder_pokemon(actor: str, label: str) -> dict[str, Any]:
    return {
        "card_id": f"{actor}-{label}",
        "card_name": label,
        "hp": 120,
        "max_hp": 120,
        "status": [],
        "energy_attached": 1,
        "stage": "Basic",
        "retreat_cost": 1,
        "prize_value": 1,
        "attacks": [{"name": "Default Attack", "cost": ["C"], "damage": 20}],
        "turns_in_play": 0,
        "just_played_this_turn": False,
        "evolved_this_turn": False,
        "attached_energy_cards": [],
        "attached_tool_cards": [],
    }


def _make_card(actor: str, index: int, supertype: str) -> dict[str, Any]:
    return {
        "id": f"{actor}-card-{index:03d}",
        "name": f"{supertype.title()} {index:03d}",
        "supertype": supertype,
        "is_basic": supertype == "pokemon",
    }


def _build_default_pool(actor: str, size: int = MAX_DECK_SIZE) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for index in range(1, size + 1):
        if index <= 24:
            supertype = "pokemon"
        elif index <= 40:
            supertype = "energy"
        else:
            supertype = "trainer"
        pool.append(_make_card(actor, index, supertype))
    return pool


def _zone_ids(cards: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for card in cards:
        if isinstance(card, dict) and isinstance(card.get("id"), str):
            ids.append(card["id"])
    return ids


def count_player_cards(player: dict[str, Any]) -> int:
    total = 0
    total += len(player.get("deck_cards", []))
    total += len(player.get("hand_cards", []))
    total += len(player.get("prize_cards", []))
    total += len(player.get("discard_pile", []))
    if isinstance(player.get("active"), dict) and player["active"].get("card_id"):
        total += 1
    total += len(player.get("bench", []))
    if isinstance(player.get("active"), dict):
        total += len(player["active"].get("attached_energy_cards", []))
        total += len(player["active"].get("attached_tool_cards", []))
    for bench_pokemon in player.get("bench", []):
        if isinstance(bench_pokemon, dict):
            total += len(bench_pokemon.get("attached_energy_cards", []))
            total += len(bench_pokemon.get("attached_tool_cards", []))
    return total


def ensure_player_battle_state(state: dict[str, Any], actor: str, total_cards: int = MAX_DECK_SIZE) -> dict[str, Any]:
    player = state["players"][actor]

    if "active" not in player or not isinstance(player["active"], dict):
        player["active"] = _placeholder_pokemon(actor, f"{actor}-active")

    # Zone seed: if all major zones are missing, build an identity-stable 60-card pool.
    if not isinstance(player.get("deck_cards"), list) and not isinstance(player.get("hand_cards"), list):
        player["deck_cards"] = _build_default_pool(actor, size=total_cards)
        player["hand_cards"] = []
        player["prize_cards"] = []
        player["discard_pile"] = []

    bench = player.get("bench")
    if not isinstance(bench, list):
        bench = []
    bench_size = int(player.get("bench_size", len(bench)))
    while len(bench) < bench_size:
        bench.append(_placeholder_pokemon(actor, f"{actor}-bench-{len(bench) + 1}"))
    if len(bench) > bench_size:
        bench_size = len(bench)
    player["bench"] = bench
    player["bench_size"] = bench_size

    hand_cards = player.get("hand_cards")
    if not isinstance(hand_cards, list):
        hand_cards = []
    while len(hand_cards) < int(player.get("hand_size", len(hand_cards))):
        hand_cards.append(_placeholder_card("hand", actor, len(hand_cards) + 1))
    player["hand_cards"] = hand_cards
    player["hand_size"] = len(hand_cards)

    prize_cards = player.get("prize_cards")
    if not isinstance(prize_cards, list):
        prize_cards = []
    prizes_remaining = int(player.get("prizes_remaining", len(prize_cards) or 6))
    while len(prize_cards) < prizes_remaining:
        prize_cards.append(_placeholder_card("prize", actor, len(prize_cards) + 1))
    if len(prize_cards) > prizes_remaining:
        prize_cards = prize_cards[:prizes_remaining]
    player["prize_cards"] = prize_cards
    player["prizes_remaining"] = len(prize_cards)

    discard_pile = player.get("discard_pile")
    if not isinstance(discard_pile, list):
        discard_pile = []
    player["discard_pile"] = discard_pile

    deck_cards = player.get("deck_cards")
    if not isinstance(deck_cards, list):
        deck_cards = []
    player["deck_cards"] = deck_cards

    # Repair missing card identities if totals fall short.
    ids_seen: set[str] = set()
    ids_seen.update(_zone_ids(player["deck_cards"]))
    ids_seen.update(_zone_ids(player["hand_cards"]))
    ids_seen.update(_zone_ids(player["prize_cards"]))
    ids_seen.update(_zone_ids(player["discard_pile"]))
    active = player.get("active", {})
    if isinstance(active, dict) and isinstance(active.get("card_id"), str):
        ids_seen.add(active["card_id"])
    for pokemon in player.get("bench", []):
        if isinstance(pokemon, dict) and isinstance(pokemon.get("card_id"), str):
            ids_seen.add(pokemon["card_id"])

    while count_player_cards(player) < total_cards:
        next_index = len(ids_seen) + 1
        candidate = _make_card(actor, next_index, "trainer")
        while candidate["id"] in ids_seen:
            next_index += 1
            candidate = _make_card(actor, next_index, "trainer")
        player["deck_cards"].append(candidate)
        ids_seen.add(candidate["id"])

    return player


def ensure_battle_state(state: dict[str, Any], total_cards: int = MAX_DECK_SIZE) -> None:
    for actor in ("p1", "p2"):
        if actor in state.get("players", {}):
            ensure_player_battle_state(state, actor, total_cards=total_cards)


def zone_conservation_report(state: dict[str, Any], total_cards: int = MAX_DECK_SIZE) -> dict[str, Any]:
    report: dict[str, Any] = {"players": {}, "all_passed": True}
    for actor in ("p1", "p2"):
        if actor not in state.get("players", {}):
            continue
        player = state["players"][actor]
        counted = count_player_cards(player)
        passed = counted == total_cards
        report["players"][actor] = {
            "counted_cards": counted,
            "expected_cards": total_cards,
            "passed": passed,
        }
        report["all_passed"] = bool(report["all_passed"] and passed)
    return report
