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
        "turns_in_play": 0,
        "just_played_this_turn": False,
        "evolved_this_turn": False,
    }


def ensure_player_battle_state(state: dict[str, Any], actor: str) -> dict[str, Any]:
    player = state["players"][actor]

    if "active" not in player or not isinstance(player["active"], dict):
        player["active"] = _placeholder_pokemon(actor, f"{actor}-active")

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
    min_remaining = max(
        0,
        MAX_DECK_SIZE
        - (1 + len(player["bench"]))
        - len(player["hand_cards"])
        - len(player["prize_cards"])
        - len(player["discard_pile"]),
    )
    while len(deck_cards) < min_remaining:
        deck_cards.append(_placeholder_card("deck", actor, len(deck_cards) + 1))
    player["deck_cards"] = deck_cards

    return player


def ensure_battle_state(state: dict[str, Any]) -> None:
    for actor in ("p1", "p2"):
        if actor in state.get("players", {}):
            ensure_player_battle_state(state, actor)
