from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CardInstance:
    card_id: str
    name: str
    supertype: str = "unknown"
    tags: list[str] = field(default_factory=list)


@dataclass
class PokemonInPlay:
    card: CardInstance
    hp: int
    max_hp: int
    stage: str = "Basic"
    status: list[str] = field(default_factory=list)
    attached_energy: list[CardInstance] = field(default_factory=list)
    attached_tools: list[CardInstance] = field(default_factory=list)
    damage_counters: int = 0


@dataclass
class PlayerZones:
    deck: list[CardInstance] = field(default_factory=list)
    hand: list[CardInstance] = field(default_factory=list)
    discard: list[CardInstance] = field(default_factory=list)
    prizes: list[CardInstance] = field(default_factory=list)
    active: PokemonInPlay | None = None
    bench: list[PokemonInPlay] = field(default_factory=list)


@dataclass
class GameRuntimeState:
    players: dict[str, PlayerZones]
    turn: int = 1
    actor: str = "p1"
    global_rules: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _placeholder_card(name: str, index: int, supertype: str) -> CardInstance:
    return CardInstance(card_id=f"{supertype}-{index}", name=name, supertype=supertype)


def _card_instance_from_zone(card: dict[str, Any], fallback_prefix: str, index: int, supertype: str = "unknown") -> CardInstance:
    if isinstance(card, dict):
        card_id = str(card.get("id") or card.get("card_id") or f"{fallback_prefix}-{index}")
        name = str(card.get("name") or card.get("card_name") or f"{fallback_prefix}-{index}")
        card_supertype = str(card.get("supertype", supertype))
        return CardInstance(card_id=card_id, name=name, supertype=card_supertype)
    return _placeholder_card(fallback_prefix, index, supertype)


def from_demo_state(state: dict[str, Any]) -> GameRuntimeState:
    players: dict[str, PlayerZones] = {}
    for actor, player in state.get("players", {}).items():
        hand_size = int(player.get("hand_size", 0))
        bench_size = int(player.get("bench_size", 0))
        prizes_remaining = int(player.get("prizes_remaining", 6))
        active_raw = player.get("active", {})
        energy_count = int(active_raw.get("energy_attached", 0))

        active_card = _card_instance_from_zone(
            {"id": active_raw.get("card_id"), "name": active_raw.get("card_name"), "supertype": "pokemon"},
            f"{actor}-active",
            0,
            "pokemon",
        )
        active = PokemonInPlay(
            card=active_card,
            hp=int(active_raw.get("hp", 120)),
            max_hp=int(active_raw.get("max_hp", 120)),
            stage=str(active_raw.get("stage", "Basic")),
            status=list(active_raw.get("status", [])),
            attached_energy=[_placeholder_card(f"{actor}-energy", i, "energy") for i in range(energy_count)],
            damage_counters=max(0, (int(active_raw.get("max_hp", 120)) - int(active_raw.get("hp", 120))) // 10),
        )

        zones = PlayerZones(
            deck=[
                _card_instance_from_zone(card, f"{actor}-deck", index, "unknown")
                for index, card in enumerate(player.get("deck_cards", []), start=1)
            ]
            or [_placeholder_card(f"{actor}-deck", i, "pokemon") for i in range(max(0, 60 - hand_size - prizes_remaining))],
            hand=[
                _card_instance_from_zone(card, f"{actor}-hand", index, "unknown")
                for index, card in enumerate(player.get("hand_cards", []), start=1)
            ]
            or [_placeholder_card(f"{actor}-hand", i, "trainer") for i in range(hand_size)],
            discard=[
                _card_instance_from_zone(card, f"{actor}-discard", index, "unknown")
                for index, card in enumerate(player.get("discard_pile", []), start=1)
            ],
            prizes=[
                _card_instance_from_zone(card, f"{actor}-prize", index, "prize")
                for index, card in enumerate(player.get("prize_cards", []), start=1)
            ]
            or [_placeholder_card(f"{actor}-prize", i, "prize") for i in range(prizes_remaining)],
            active=active,
            bench=[],
        )
        bench_entries = player.get("bench", [])
        if isinstance(bench_entries, list) and bench_entries:
            for index, bench_raw in enumerate(bench_entries, start=1):
                zones.bench.append(
                    PokemonInPlay(
                        card=_card_instance_from_zone(
                            {"id": bench_raw.get("card_id"), "name": bench_raw.get("card_name"), "supertype": "pokemon"},
                            f"{actor}-bench",
                            index,
                            "pokemon",
                        ),
                        hp=int(bench_raw.get("hp", 120)),
                        max_hp=int(bench_raw.get("max_hp", 120)),
                        stage=str(bench_raw.get("stage", "Basic")),
                        status=list(bench_raw.get("status", [])),
                        attached_energy=[
                            _card_instance_from_zone(energy, f"{actor}-bench-energy", energy_index, "energy")
                            for energy_index, energy in enumerate(bench_raw.get("attached_energy_cards", []), start=1)
                        ],
                    )
                )
        else:
            zones.bench.extend(
                [
                    PokemonInPlay(
                        card=_placeholder_card(f"{actor}-bench-{i}", i, "pokemon"),
                        hp=120,
                        max_hp=120,
                    )
                    for i in range(bench_size)
                ]
            )
        players[actor] = zones

    return GameRuntimeState(players=players, turn=1, actor="p1")
