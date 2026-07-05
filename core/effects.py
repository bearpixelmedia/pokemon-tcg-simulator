from __future__ import annotations

import re
import random
from typing import Any

from core.effect_types import EffectOperation, EffectProgram
from core.rules_mechanics import create_active_pokemon
_ROTATING_STATUSES = {"Asleep", "Confused", "Paralyzed"}


def create_demo_state() -> dict[str, Any]:
    return {
        "board": {"stadium": None},
        "players": {
            "p1": {
                "name": "You",
                "hand_size": 5,
                "hand_supporters": 1,
                "hand_stadiums": 1,
                "hand_tools": 1,
                "active": create_active_pokemon(),
                "bench_size": 2,
                "prizes_remaining": 6,
                "knockouts": 0,
                "turn_flags": {},
            },
            "p2": {
                "name": "AI",
                "hand_size": 5,
                "hand_supporters": 1,
                "hand_stadiums": 1,
                "hand_tools": 1,
                "active": create_active_pokemon(),
                "bench_size": 2,
                "prizes_remaining": 6,
                "knockouts": 0,
                "turn_flags": {},
            },
        }
    }


def _opponent(actor: str) -> str:
    return "p2" if actor == "p1" else "p1"


def _target_slot(state: dict[str, Any], actor: str, target: str) -> dict[str, Any]:
    if target in {"self_active", "self_pokemon", "self_bench", "self_other"}:
        return state["players"][actor]["active"]
    if target in {"opponent_active", "opponent_any_pokemon"}:
        return state["players"][_opponent(actor)]["active"]
    if target == "opponent_bench":
        return state["players"][_opponent(actor)]["active"]
    raise ValueError(f"Unsupported target '{target}' for demo engine")


def _coerce_operation(operation: EffectOperation | dict[str, Any]) -> EffectOperation:
    if isinstance(operation, EffectOperation):
        return operation
    return EffectOperation(op=operation.get("op", "unknown"), params=operation.get("params", {}))


def _apply_status_to_slot(slot: dict[str, Any], status: str) -> None:
    statuses = [value for value in slot.get("status", []) if isinstance(value, str)]

    if status in _ROTATING_STATUSES:
        statuses = [existing for existing in statuses if existing not in _ROTATING_STATUSES]
    elif status in statuses:
        slot["status"] = statuses
        return

    if status not in statuses:
        statuses.append(status)
    slot["status"] = statuses

    if status == "Paralyzed":
        # Paralysis expires during Pokémon Checkup after the owner's next turn.
        slot["paralyzed_turns_remaining"] = 1


def _parse_count_token(raw: str | None, default: int = 1) -> int:
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in {"a", "an"}:
        return 1
    if lowered in {"all", "any amount of"}:
        return -1
    return int(lowered)


def _apply_script_hook_inference(
    normalized: EffectOperation,
    state: dict[str, Any],
    actor: str,
    rng: random.Random,
    events: list[str],
) -> bool:
    hook_id = str(normalized.params.get("hook_id", "unknown"))
    clause = str(normalized.params.get("clause", "")).strip()
    opponent = _opponent(actor)

    if hook_id in {"each-player-shuffles-hand-into-deck", "each-player-shuffle-hand-put-bottom"}:
        state["players"][actor]["hand_size"] = 0
        state["players"][opponent]["hand_size"] = 0
        events.append(f"{actor} resolved scripted hook: both players shuffled their hand away.")
        return True

    if hook_id == "opponent-shuffle-hand-to-bottom":
        state["players"][opponent]["hand_size"] = 0
        events.append(f"{actor} resolved scripted hook: opponent shuffled hand away.")
        return True

    if hook_id == "then-you-draw-and-opponent-draws":
        self_count = int(normalized.params.get("self_count", 0))
        opp_count = int(normalized.params.get("opp_count", 0))
        state["players"][actor]["hand_size"] += self_count
        state["players"][opponent]["hand_size"] += opp_count
        events.append(f"{actor} resolved scripted hook: draw split {self_count}/{opp_count}.")
        return True

    if hook_id == "then-draw-per-opponent-hand-cards":
        draw = int(state["players"][opponent].get("hand_size", 0))
        state["players"][actor]["hand_size"] += draw
        events.append(f"{actor} resolved scripted hook: drew {draw} from opponent hand count.")
        return True

    if hook_id == "opponent-discards-until-hand-size":
        cap = int(normalized.params.get("count", 0))
        state["players"][opponent]["hand_size"] = min(int(state["players"][opponent].get("hand_size", 0)), cap)
        events.append(f"{actor} resolved scripted hook: opponent hand reduced to {cap}.")
        return True

    if hook_id == "your-turn-ends":
        state["players"][actor].setdefault("turn_flags", {})["force_end_turn"] = True
        events.append(f"{actor} resolved scripted hook: turn will end.")
        return True

    if hook_id == "search-then-shuffle-generic" and clause:
        hand_match = re.match(
            r"^Search your deck for (?:up to )?(?P<count>\d+|a|an) .+ and put (?:them|it) into your hand\. Then, shuffle your deck\.$",
            clause,
            flags=re.IGNORECASE,
        )
        if hand_match:
            count = _parse_count_token(hand_match.group("count"))
            if count < 0:
                count = 1
            _apply_operation(
                EffectOperation(op="search_deck_to_hand", params={"count": count, "descriptor": "matching", "allow_less": True}),
                state,
                actor,
                rng,
                events,
            )
            _apply_operation(EffectOperation(op="shuffle_deck", params={}), state, actor, rng, events)
            return True

        bench_match = re.match(
            r"^Search your deck for (?:up to )?(?P<count>\d+|a|an) .+ and put (?:them|it) onto your Bench\. Then, shuffle your deck\.$",
            clause,
            flags=re.IGNORECASE,
        )
        if bench_match:
            count = _parse_count_token(bench_match.group("count"))
            if count < 0:
                count = 1
            _apply_operation(
                EffectOperation(op="search_deck_to_bench", params={"count": count, "descriptor": "matching", "allow_less": True}),
                state,
                actor,
                rng,
                events,
            )
            _apply_operation(EffectOperation(op="shuffle_deck", params={}), state, actor, rng, events)
            return True

        attach_match = re.match(
            r"^Search your deck for (?:up to )?(?P<count>\d+|a|an) .+ and attach (?:them|it) to .+\. Then, shuffle your deck\.$",
            clause,
            flags=re.IGNORECASE,
        )
        if attach_match:
            count = _parse_count_token(attach_match.group("count"))
            if count < 0:
                count = 1
            _apply_operation(EffectOperation(op="attach_energy", params={"source": "deck", "count": count}), state, actor, rng, events)
            _apply_operation(EffectOperation(op="shuffle_deck", params={}), state, actor, rng, events)
            return True

        if clause.lower().startswith("search your deck for"):
            _apply_operation(EffectOperation(op="shuffle_deck", params={}), state, actor, rng, events)
            events.append(f"{actor} resolved scripted hook: generic search+shuffle.")
            return True

    if clause:
        if hook_id == "generic-this-attack-clause":
            energy_self = re.match(
                r"^This attack does (?P<amount>\d+) (?P<kind>more )?damage for each \{[A-Z]\} Energy attached to this (?:Pokemon|Pokémon)\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if energy_self:
                _apply_operation(
                    EffectOperation(
                        op="damage_per_attached_energy",
                        params={
                            "target": "self_active",
                            "amount_per_energy": int(energy_self.group("amount")),
                            "kind": "bonus" if energy_self.group("kind") else "base",
                        },
                    ),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            prize_taken = re.match(
                r"^This attack does (?P<amount>\d+) damage for each Prize card your opponent has taken\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if prize_taken:
                _apply_operation(
                    EffectOperation(
                        op="damage_per_prize_taken",
                        params={"target": "opponent_active", "amount_per_prize": int(prize_taken.group("amount")), "kind": "base"},
                    ),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            self_in_play = re.match(
                r"^This attack does (?P<amount>\d+) damage for each of your .+ in play\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if self_in_play:
                _apply_operation(
                    EffectOperation(
                        op="damage_per_pokemon_in_play",
                        params={"target": "opponent_active", "amount_per_pokemon": int(self_in_play.group("amount")), "scope": "self"},
                    ),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            opponent_hand = re.match(
                r"^This attack does (?P<amount>\d+) damage for each card in your opponent's hand\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if opponent_hand:
                total = int(opponent_hand.group("amount")) * int(state["players"][opponent].get("hand_size", 0))
                _apply_operation(
                    EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": total}),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            many_targets = re.match(
                r"^This attack does (?P<amount>\d+) damage to each of (?P<count>\d+) of your opponent's (?:Pokemon|Pokémon)\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if many_targets:
                total = int(many_targets.group("amount")) * int(many_targets.group("count"))
                _apply_operation(
                    EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": total}),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            per_counter = re.match(
                r"^This attack does (?P<amount>\d+) more damage for each damage counter on your opponent's Active (?:Pokemon|Pokémon)\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if per_counter:
                _apply_operation(
                    EffectOperation(op="damage_per_target_damage_counter", params={"amount_per_counter": int(per_counter.group("amount"))}),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            simple_damage = re.match(r"^This attack does (?P<amount>\d+) damage\.$", clause, flags=re.IGNORECASE)
            if simple_damage:
                _apply_operation(
                    EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": int(simple_damage.group("amount"))}),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

        if hook_id == "generic-discard-clause":
            hand_draw = re.match(r"^Discard your hand and draw (?P<count>\d+) cards\.$", clause, flags=re.IGNORECASE)
            if hand_draw:
                state["players"][actor]["hand_size"] = 0
                _apply_operation(
                    EffectOperation(op="draw_cards", params={"count": int(hand_draw.group("count"))}),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

            discard_energy_damage = re.match(
                r"^Discard any amount of \{[A-Z]\} Energy from among your (?:Pokemon|Pokémon), and this attack does (?P<amount>\d+) damage for each card you discarded in this way\.$",
                clause,
                flags=re.IGNORECASE,
            )
            if discard_energy_damage:
                _apply_operation(EffectOperation(op="discard_energy", params={"target": "self_pokemon", "count": -1}), state, actor, rng, events)
                _apply_operation(
                    EffectOperation(
                        op="damage_per_discarded_energy",
                        params={"target": "opponent_active", "amount_per_energy": int(discard_energy_damage.group("amount")), "kind": "base"},
                    ),
                    state,
                    actor,
                    rng,
                    events,
                )
                return True

        match = re.match(r"^Discard (?P<count>\d+|a|an) cards? from your hand\.$", clause, flags=re.IGNORECASE)
        if match:
            count = _parse_count_token(match.group("count"))
            _apply_operation(EffectOperation(op="discard_cards", params={"target": "self_hand", "count": count}), state, actor, rng, events)
            return True

        if re.match(r"^Discard all Energy from this (?:Pokemon|Pokémon)\.$", clause, flags=re.IGNORECASE):
            _apply_operation(EffectOperation(op="discard_energy", params={"target": "self_active", "count": -1}), state, actor, rng, events)
            return True

        match = re.match(r"^Discard (?P<count>\d+) Energy from this (?:Pokemon|Pokémon)\.$", clause, flags=re.IGNORECASE)
        if match:
            _apply_operation(
                EffectOperation(op="discard_energy", params={"target": "self_active", "count": int(match.group("count"))}),
                state,
                actor,
                rng,
                events,
            )
            return True

        match = re.match(r"^Attach (?:up to )?(?P<count>\d+|a|an) .*Energy card.*\.$", clause, flags=re.IGNORECASE)
        if match:
            count = _parse_count_token(match.group("count"))
            if count < 0:
                count = 1
            _apply_operation(EffectOperation(op="attach_energy", params={"source": "script", "count": count}), state, actor, rng, events)
            return True

        match = re.match(r"^Heal (?P<amount>\d+) damage .+\.$", clause, flags=re.IGNORECASE)
        if match:
            _apply_operation(
                EffectOperation(op="heal_damage", params={"target": "self_active", "amount": int(match.group("amount"))}),
                state,
                actor,
                rng,
                events,
            )
            return True

        match = re.match(
            r"^Move (?P<count>\d+|all|any amount of|a|an) .*Energy from this (?:Pokemon|Pokémon) to \d+ of your Benched (?:Pokemon|Pokémon)\.$",
            clause,
            flags=re.IGNORECASE,
        )
        if match:
            count = _parse_count_token(match.group("count"))
            _apply_operation(
                EffectOperation(op="move_energy", params={"source": "self_active", "target": "self_bench", "count": count}),
                state,
                actor,
                rng,
                events,
            )
            return True

        match = re.match(r"^Put (?P<count>\d+) damage counters on your opponent's Active (?:Pokemon|Pokémon)\.$", clause, flags=re.IGNORECASE)
        if match:
            _apply_operation(
                EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": int(match.group("count")) * 10}),
                state,
                actor,
                rng,
                events,
            )
            return True

        if re.match(r"^This (?:Pokemon|Pokémon) recovers from all Special Conditions\.$", clause, flags=re.IGNORECASE):
            state["players"][actor]["active"]["status"] = []
            events.append(f"{actor} resolved scripted hook: active recovered from all statuses.")
            return True

        if re.match(r"^Make your opponent's Active (?:Pokemon|Pokémon) Confused\.$", clause, flags=re.IGNORECASE):
            _apply_operation(
                EffectOperation(op="apply_status", params={"target": "opponent_active", "status": "Confused"}),
                state,
                actor,
                rng,
                events,
            )
            return True

    return False


def apply_effect_program(
    program: EffectProgram,
    state: dict[str, Any],
    actor: str,
    rng: random.Random | None = None,
) -> list[str]:
    rng = rng or random.Random()
    events: list[str] = []
    for operation in program.operations:
        _apply_operation(operation, state, actor, rng, events)
    return events


def _apply_operation(
    operation: EffectOperation | dict[str, Any],
    state: dict[str, Any],
    actor: str,
    rng: random.Random,
    events: list[str],
) -> None:
    normalized = _coerce_operation(operation)

    if normalized.op == "deal_damage":
        slot = _target_slot(state, actor, normalized.params["target"])
        amount = int(normalized.params["amount"])
        if int(slot.get("prevent_all_damage_turns_remaining", 0)) > 0:
            events.append(
                f"{actor}'s damage was prevented on {normalized.params['target']}."
            )
            return

        reduction_amount = 0
        if int(slot.get("incoming_damage_reduction_turns_remaining", 0)) > 0:
            reduction_amount = int(slot.get("incoming_damage_reduction_amount", 0))
        final_amount = max(0, amount - reduction_amount)
        slot["hp"] = max(0, slot["hp"] - final_amount)
        if reduction_amount > 0:
            events.append(
                f"{actor} dealt {final_amount} damage to {normalized.params['target']} "
                f"after {reduction_amount} reduction."
            )
        else:
            events.append(f"{actor} dealt {final_amount} damage to {normalized.params['target']}.")
        return

    if normalized.op == "heal_damage":
        slot = _target_slot(state, actor, normalized.params["target"])
        amount = int(normalized.params["amount"])
        slot["hp"] = min(slot["max_hp"], slot["hp"] + amount)
        events.append(f"{actor} healed {amount} damage on {normalized.params['target']}.")
        return

    if normalized.op == "apply_status":
        slot = _target_slot(state, actor, normalized.params["target"])
        status = normalized.params["status"]
        _apply_status_to_slot(slot, status)
        events.append(f"{actor} applied {status} to {normalized.params['target']}.")
        return

    if normalized.op == "draw_cards":
        draw_count = int(normalized.params["count"])
        state["players"][actor]["hand_size"] += draw_count
        events.append(f"{actor} drew {draw_count} cards.")
        return

    if normalized.op == "draw_until_hand_size":
        target_size = int(normalized.params["count"])
        current = state["players"][actor]["hand_size"]
        if current < target_size:
            drawn = target_size - current
            state["players"][actor]["hand_size"] = target_size
            events.append(f"{actor} drew {drawn} cards to reach hand size {target_size}.")
        else:
            events.append(f"{actor} already has at least {target_size} cards in hand.")
        return

    if normalized.op == "triggered_effect":
        for nested in normalized.params.get("operations", []):
            _apply_operation(nested, state, actor, rng, events)
        events.append(f"{actor} resolved triggered effect ({normalized.params.get('trigger')}).")
        return

    if normalized.op == "search_deck_to_hand":
        count = int(normalized.params.get("count", 1))
        state["players"][actor]["hand_size"] += count
        descriptor = normalized.params.get("descriptor", "matching")
        events.append(f"{actor} searched deck for {count} {descriptor} card(s).")
        return

    if normalized.op == "shuffle_hand_into_deck":
        player = state["players"][actor]
        player["hand_size"] = 0
        events.append(f"{actor} shuffled hand into deck.")
        return

    if normalized.op == "search_deck_to_bench":
        count = int(normalized.params.get("count", 1))
        descriptor = normalized.params.get("descriptor", "matching")
        player = state["players"][actor]
        player["bench_size"] = player.get("bench_size", 0) + count
        events.append(f"{actor} benched up to {count} {descriptor} card(s) from deck.")
        return

    if normalized.op == "shuffle_deck":
        events.append(f"{actor} shuffled their deck.")
        return

    if normalized.op == "switch_active_with_bench":
        target = normalized.params.get("target", "self_player")
        owner = actor if target == "self_player" else _opponent(actor)
        events.append(f"{owner} switched their Active Pokémon with a Benched Pokémon.")
        return

    if normalized.op == "discard_energy":
        slot = _target_slot(state, actor, normalized.params["target"])
        count = int(normalized.params.get("count", 1))
        if count < 0:
            discarded = slot.get("energy_attached", 0)
            slot["energy_attached"] = 0
        else:
            discarded = min(slot.get("energy_attached", 0), count)
            slot["energy_attached"] = max(0, slot.get("energy_attached", 0) - discarded)
        state["players"][actor]["active"]["last_discarded_energy_count"] = int(discarded)
        events.append(f"{actor} discarded {discarded} Energy from {normalized.params['target']}.")
        return

    if normalized.op == "attach_energy":
        count = int(normalized.params.get("count", 1))
        slot = state["players"][actor]["active"]
        slot["energy_attached"] = slot.get("energy_attached", 0) + count
        events.append(f"{actor} attached {count} Energy from {normalized.params.get('source', 'unknown')}.")
        return

    if normalized.op == "modify_incoming_damage_next_turn":
        slot = state["players"][actor]["active"]
        slot["incoming_damage_reduction_amount"] = int(normalized.params.get("amount", 0))
        slot["incoming_damage_reduction_turns_remaining"] = 1
        events.append(
            f"{actor} gained {slot['incoming_damage_reduction_amount']} damage reduction for next turn."
        )
        return

    if normalized.op == "move_energy":
        slot = state["players"][actor]["active"]
        available = int(slot.get("energy_attached", 0))
        requested = int(normalized.params.get("count", 1))
        count = available if requested < 0 else min(requested, available)
        slot["energy_attached"] = max(0, available - count)
        events.append(f"{actor} moved {count} Energy to the Bench.")
        return

    if normalized.op == "discard_random_card":
        target_player = state["players"][_opponent(actor)]
        discarded = min(int(normalized.params.get("count", 1)), int(target_player.get("hand_size", 0)))
        target_player["hand_size"] = max(0, int(target_player.get("hand_size", 0)) - discarded)
        events.append(f"{actor} discarded {discarded} random card(s) from opponent hand.")
        return

    if normalized.op == "discard_cards":
        target = normalized.params.get("target", "self_hand")
        count = int(normalized.params.get("count", 1))
        if target == "self_hand":
            player = state["players"][actor]
            discarded = min(count, int(player.get("hand_size", 0)))
            player["hand_size"] = max(0, int(player.get("hand_size", 0)) - discarded)
            events.append(f"{actor} discarded {discarded} card(s) from hand.")
            return
        if target == "opponent_hand":
            player = state["players"][_opponent(actor)]
            discarded = min(count, int(player.get("hand_size", 0)))
            player["hand_size"] = max(0, int(player.get("hand_size", 0)) - discarded)
            events.append(f"{actor} made opponent discard {discarded} card(s) from hand.")
            return

    if normalized.op == "recover_from_discard_to_hand":
        count = int(normalized.params.get("count", 1))
        state["players"][actor]["hand_size"] = int(state["players"][actor].get("hand_size", 0)) + count
        events.append(f"{actor} recovered {count} card(s) from discard to hand.")
        return

    if normalized.op == "look_top_deck_pick":
        picked = int(normalized.params.get("pick_count", 1))
        state["players"][actor]["hand_size"] = int(state["players"][actor].get("hand_size", 0)) + picked
        events.append(f"{actor} looked at top deck cards and picked {picked}.")
        return

    if normalized.op == "mill_top_deck":
        events.append(f"{actor} discarded top card(s) from opponent deck.")
        return

    if normalized.op == "discard_tools":
        events.append(f"{actor} discarded Pokémon Tools from opponent Active Pokémon.")
        return

    if normalized.op == "damage_per_self_damage_counter":
        active = state["players"][actor]["active"]
        counters = max(0, (int(active.get("max_hp", 0)) - int(active.get("hp", 0))) // 10)
        total_damage = counters * int(normalized.params.get("amount_per_counter", 0))
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on self damage counters.")
        return

    if normalized.op == "damage_per_discarded_energy":
        amount = int(normalized.params.get("amount_per_energy", 0))
        discarded = int(state["players"][actor]["active"].get("last_discarded_energy_count", 0))
        total_damage = amount * discarded
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on discarded Energy.")
        return

    if normalized.op == "damage_per_benched":
        amount = int(normalized.params.get("amount_per_bench", 0))
        scope = normalized.params.get("scope", "self")
        if scope == "both":
            count = int(state["players"][actor].get("bench_size", 0)) + int(
                state["players"][_opponent(actor)].get("bench_size", 0)
            )
        elif scope == "opponent":
            count = int(state["players"][_opponent(actor)].get("bench_size", 0))
        else:
            count = int(state["players"][actor].get("bench_size", 0))
        total_damage = amount * count
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on Benched Pokémon count.")
        return

    if normalized.op == "damage_per_attached_energy":
        amount = int(normalized.params.get("amount_per_energy", 0))
        target = normalized.params.get("target", "self_active")
        count = 0
        if target == "self_active":
            count = int(state["players"][actor]["active"].get("energy_attached", 0))
        elif target == "opponent_active":
            count = int(state["players"][_opponent(actor)]["active"].get("energy_attached", 0))
        elif target == "both_active":
            count = int(state["players"][actor]["active"].get("energy_attached", 0)) + int(
                state["players"][_opponent(actor)]["active"].get("energy_attached", 0)
            )
        elif target == "all_self_pokemon":
            count = int(state["players"][actor]["active"].get("energy_attached", 0))
        total_damage = amount * count
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on attached Energy.")
        return

    if normalized.op == "damage_per_target_damage_counter":
        target = state["players"][_opponent(actor)]["active"]
        counters = max(0, (int(target.get("max_hp", 0)) - int(target.get("hp", 0))) // 10)
        total_damage = counters * int(normalized.params.get("amount_per_counter", 0))
        target["hp"] = max(0, int(target.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on target damage counters.")
        return

    if normalized.op == "damage_per_prize_taken":
        amount = int(normalized.params.get("amount_per_prize", 0))
        taken = 6 - int(state["players"][_opponent(actor)].get("prizes_remaining", 6))
        total_damage = max(0, taken) * amount
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on prizes taken.")
        return

    if normalized.op == "damage_per_pokemon_in_play":
        amount = int(normalized.params.get("amount_per_pokemon", 0))
        scope = normalized.params.get("scope", "self")
        if scope == "self":
            count = 1 + int(state["players"][actor].get("bench_size", 0))
        else:
            count = 1 + int(state["players"][actor].get("bench_size", 0)) + 1 + int(
                state["players"][_opponent(actor)].get("bench_size", 0)
            )
        total_damage = amount * count
        target = state["players"][_opponent(actor)]["active"]
        target["hp"] = max(0, int(target.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on Pokémon in play.")
        return

    if normalized.op == "flip_until_tails_damage_bonus":
        amount = int(normalized.params.get("amount_per_heads", 0))
        heads = 0
        while True:
            result = rng.choice(["heads", "tails"])
            if result == "heads":
                heads += 1
                continue
            break
        total_damage = heads * amount
        target = state["players"][_opponent(actor)]["active"]
        target["hp"] = max(0, int(target.get("hp", 0)) - total_damage)
        events.append(f"{actor} flipped {heads} heads before tails for {total_damage} bonus damage.")
        return

    if normalized.op == "attach_energy_per_benched_pokemon":
        bench = int(state["players"][actor].get("bench_size", 0))
        events.append(f"{actor} attached Energy from deck to up to {bench} Benched Pokémon.")
        return

    if normalized.op == "reveal_hand":
        events.append(f"{actor} revealed opponent hand.")
        return

    if normalized.op == "discard_stadium":
        state.setdefault("board", {})["stadium"] = None
        events.append(f"{actor} discarded the Stadium in play.")
        return

    if normalized.op == "evolve_from_deck":
        events.append(f"{actor} evolved using a card searched from deck.")
        return

    if normalized.op == "heal_equal_last_damage_dealt":
        events.append(f"{actor} healed equal to previously dealt damage.")
        return

    if normalized.op == "place_damage_counters":
        counters = int(normalized.params.get("count", 0))
        events.append(f"{actor} placed {counters} damage counters on target Pokémon.")
        return

    if normalized.op == "shuffle_attached_energy_into_deck":
        count = int(normalized.params.get("count", 0))
        slot = state["players"][actor]["active"]
        moved = min(count, int(slot.get("energy_attached", 0)))
        slot["energy_attached"] = max(0, int(slot.get("energy_attached", 0)) - moved)
        events.append(f"{actor} shuffled {moved} attached Energy into deck.")
        return

    if normalized.op == "damage_per_tool_attached":
        amount = int(normalized.params.get("amount_per_tool", 0))
        tools = 1 if state["players"][actor]["active"].get("tool_attached") else 0
        total_damage = tools * amount
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} dealt {total_damage} damage based on attached Tools.")
        return

    if normalized.op == "choose_random_opponent_hand_card":
        events.append(f"{actor} chose a random card from opponent hand.")
        return

    if normalized.op in {"shuffle_selected_opponent_hand_card_into_deck", "shuffle_random_opponent_hand_card_into_deck"}:
        events.append(f"{actor} shuffled a random opponent hand card into deck.")
        return

    if normalized.op == "choose_self_pokemon":
        events.append(f"{actor} chose their own Pokémon.")
        return

    if normalized.op == "return_attached_energy_to_hand":
        slot = state["players"][actor]["active"]
        if int(slot.get("energy_attached", 0)) > 0:
            slot["energy_attached"] = int(slot.get("energy_attached", 0)) - 1
            state["players"][actor]["hand_size"] = int(state["players"][actor].get("hand_size", 0)) + 1
        events.append(f"{actor} returned an attached Energy to hand.")
        return

    if normalized.op == "scoop_up_self":
        events.append(f"{actor} scooped up their Active Pokémon and attached cards.")
        return

    if normalized.op == "put_card_on_bottom_of_deck":
        events.append(f"{actor} put card(s) on bottom of deck.")
        return

    if normalized.op == "flip_coins_for_damage":
        coin_count = int(normalized.params.get("coin_count", 0))
        damage_per_heads = int(normalized.params.get("damage_per_heads", 0))
        heads = 0
        for _ in range(coin_count):
            if rng.choice(["heads", "tails"]) == "heads":
                heads += 1
        total_damage = heads * damage_per_heads
        slot = state["players"][_opponent(actor)]["active"]
        slot["hp"] = max(0, int(slot.get("hp", 0)) - total_damage)
        events.append(f"{actor} flipped {heads}/{coin_count} heads for {total_damage} damage.")
        return

    if normalized.op == "flip_coins":
        coin_count = int(normalized.params.get("count", 0))
        heads = 0
        for _ in range(coin_count):
            if rng.choice(["heads", "tails"]) == "heads":
                heads += 1
        events.append(f"{actor} flipped {heads}/{coin_count} heads.")
        return

    if normalized.op in {
        "ignore_weakness_resistance",
        "ignore_defending_effects",
        "ignore_weakness_resistance_and_effects_on_targets",
        "ignore_resistance",
        "apply_temporary_rule",
        "select_opponent_bench",
        "choose_attack",
        "annotation_noop",
    }:
        events.append(f"{actor} prepared effect: {normalized.op}.")
        return

    if normalized.op == "script_hook":
        hook_id = normalized.params.get("hook_id", "unknown")
        if hook_id == "prevent-all-damage-next-turn":
            slot = state["players"][actor]["active"]
            slot["prevent_all_damage_turns_remaining"] = 1
            events.append(f"{actor} set prevent-all-damage shield for next opponent turn.")
            return
        if _apply_script_hook_inference(normalized, state, actor, rng, events):
            return
        events.append(f"{actor} queued scripted hook: {hook_id}.")
        return

    if normalized.op == "flip_coin":
        result = rng.choice(["heads", "tails"])
        events.append(f"{actor} flipped {result}.")
        for branch_operation in normalized.params.get(result, []):
            _apply_operation(branch_operation, state, actor, rng, events)
        return

    events.append(f"{actor} has unsupported operation: {normalized.op}")


def apply_pokemon_checkup(
    state: dict[str, Any], actor: str, rng: random.Random | None = None
) -> list[str]:
    rng = rng or random.Random()
    events: list[str] = []
    target = state["players"][actor]["active"]
    statuses = list(target.get("status", []))

    # Pokémon Checkup special condition order:
    # Poisoned -> Burned -> Asleep -> Paralyzed
    if "Poisoned" in statuses:
        target["hp"] = max(0, target["hp"] - 10)
        events.append(f"{actor} took 10 poison damage.")

    if "Burned" in statuses:
        target["hp"] = max(0, target["hp"] - 20)
        events.append(f"{actor} took 20 burn damage.")
        if rng.choice(["heads", "tails"]) == "heads":
            target["status"] = [status for status in target["status"] if status != "Burned"]
            events.append(f"{actor} recovered from Burned.")

    if "Asleep" in statuses and rng.choice(["heads", "tails"]) == "heads":
        target["status"] = [status for status in target["status"] if status != "Asleep"]
        events.append(f"{actor} woke up from Asleep.")

    if "Paralyzed" in statuses:
        remaining = int(target.get("paralyzed_turns_remaining", 1))
        remaining -= 1
        if remaining <= 0:
            target["status"] = [status for status in target["status"] if status != "Paralyzed"]
            target.pop("paralyzed_turns_remaining", None)
            events.append(f"{actor} recovered from Paralyzed.")
        else:
            target["paralyzed_turns_remaining"] = remaining

    if int(target.get("incoming_damage_reduction_turns_remaining", 0)) > 0:
        target["incoming_damage_reduction_turns_remaining"] -= 1
        if target["incoming_damage_reduction_turns_remaining"] <= 0:
            target["incoming_damage_reduction_turns_remaining"] = 0
            target["incoming_damage_reduction_amount"] = 0

    if int(target.get("prevent_all_damage_turns_remaining", 0)) > 0:
        target["prevent_all_damage_turns_remaining"] -= 1
        if target["prevent_all_damage_turns_remaining"] <= 0:
            target["prevent_all_damage_turns_remaining"] = 0

    return events

