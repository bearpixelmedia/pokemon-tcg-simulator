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


def from_demo_state(state: dict[str, Any]) -> GameRuntimeState:
    players: dict[str, PlayerZones] = {}
    for actor, player in state.get("players", {}).items():
        hand_size = int(player.get("hand_size", 0))
        bench_size = int(player.get("bench_size", 0))
        prizes_remaining = int(player.get("prizes_remaining", 6))
        active_raw = player.get("active", {})
        energy_count = int(active_raw.get("energy_attached", 0))

        active_card = _placeholder_card(f"{actor}-active", 0, "pokemon")
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
            deck=[_placeholder_card(f"{actor}-deck", i, "pokemon") for i in range(max(0, 60 - hand_size - prizes_remaining))],
            hand=[_placeholder_card(f"{actor}-hand", i, "trainer") for i in range(hand_size)],
            discard=[],
            prizes=[_placeholder_card(f"{actor}-prize", i, "prize") for i in range(prizes_remaining)],
            active=active,
            bench=[
                PokemonInPlay(
                    card=_placeholder_card(f"{actor}-bench-{i}", i, "pokemon"),
                    hp=120,
                    max_hp=120,
                )
                for i in range(bench_size)
            ],
        )
        players[actor] = zones

    return GameRuntimeState(players=players, turn=1, actor="p1")
