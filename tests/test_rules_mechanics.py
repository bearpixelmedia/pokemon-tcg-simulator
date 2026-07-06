import unittest
import json
import tempfile
from pathlib import Path

from core.effect_types import EffectOperation, EffectProgram
from core.effects import advance_temporary_rule_durations, apply_effect_program, create_demo_state
from core.hook_manifest import hook_signature
from core.rules_mechanics import (
    attempt_devolve,
    attempt_evolve,
    attempt_retreat,
    resolve_knockouts_and_prizes,
)


class RulesMechanicsTests(unittest.TestCase):
    def test_retreat_requires_bench_and_energy(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["bench_size"] = 1
        state["players"]["p1"]["active"]["energy_attached"] = 1
        original_active = state["players"]["p1"]["active"]["card_id"]
        promoted = state["players"]["p1"]["bench"][0]["card_id"]
        ok, events = attempt_retreat(state, "p1")
        self.assertTrue(ok)
        self.assertTrue(any("retreated" in event for event in events))
        self.assertEqual(state["players"]["p1"]["active"]["card_id"], promoted)
        self.assertTrue(any(pokemon["card_id"] == original_active for pokemon in state["players"]["p1"]["bench"]))

    def test_evolve_and_devolve_progression(self) -> None:
        state = create_demo_state()
        ok, _ = attempt_evolve(state, "p1")
        self.assertTrue(ok)
        self.assertEqual(state["players"]["p1"]["active"]["stage"], "Stage1")

        ok, _ = attempt_devolve(state, "p1")
        self.assertTrue(ok)
        self.assertEqual(state["players"]["p1"]["active"]["stage"], "Basic")

    def test_knockout_awards_prize(self) -> None:
        state = create_demo_state()
        knocked_out_id = state["players"]["p2"]["active"]["card_id"]
        state["players"]["p2"]["active"]["hp"] = 0
        prior_discard = len(state["players"]["p2"]["discard_pile"])
        events = resolve_knockouts_and_prizes(state)
        self.assertTrue(any("Knocked Out" in event for event in events))
        self.assertEqual(state["players"]["p1"]["prizes_remaining"], 5)
        self.assertGreaterEqual(len(state["players"]["p2"]["discard_pile"]), prior_discard + 1)
        self.assertTrue(
            any(item.get("card_id") == knocked_out_id for item in state["players"]["p2"]["discard_pile"] if isinstance(item, dict))
        )

    def test_damage_reduction_and_prevent_hook(self) -> None:
        state = create_demo_state()
        reduction_program = EffectProgram(
            source_text="reduction",
            operations=[
                EffectOperation(
                    op="modify_incoming_damage_next_turn",
                    params={"target": "self_active", "amount": 20},
                )
            ],
        )
        apply_effect_program(reduction_program, state, actor="p2")
        damage_program = EffectProgram(
            source_text="damage",
            operations=[EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": 50})],
        )
        apply_effect_program(damage_program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 90)

    def test_search_to_bench_and_hand_disruption_ops(self) -> None:
        state = create_demo_state()
        utility_program = EffectProgram(
            source_text="utility",
            operations=[
                EffectOperation(op="search_deck_to_bench", params={"count": 2, "descriptor": "Basic Pokémon"}),
                EffectOperation(op="discard_random_card", params={"target": "opponent_hand", "count": 1}),
            ],
        )
        apply_effect_program(utility_program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["bench_size"], 4)
        self.assertEqual(state["players"]["p2"]["hand_size"], 4)

    def test_damage_per_self_counter_operation(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["active"]["hp"] = 90  # 3 damage counters from 120 max_hp
        program = EffectProgram(
            source_text="counter scaling",
            operations=[
                EffectOperation(
                    op="damage_per_self_damage_counter",
                    params={"target": "opponent_active", "amount_per_counter": 20},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 60)

    def test_damage_per_prize_taken_operation(self) -> None:
        state = create_demo_state()
        state["players"]["p2"]["prizes_remaining"] = 3
        program = EffectProgram(
            source_text="prize scaling",
            operations=[
                EffectOperation(
                    op="damage_per_prize_taken",
                    params={"target": "opponent_active", "amount_per_prize": 20},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 60)

    def test_damage_per_pokemon_in_play_operation(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["bench_size"] = 3
        program = EffectProgram(
            source_text="board scaling",
            operations=[
                EffectOperation(
                    op="damage_per_pokemon_in_play",
                    params={"target": "opponent_active", "amount_per_pokemon": 10, "scope": "self"},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 80)

    def test_script_hook_infers_discard_from_hand_clause(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="script discard",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={"hook_id": "generic-discard-clause", "clause": "Discard 2 cards from your hand."},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["hand_size"], 3)

    def test_script_hook_infers_each_player_shuffle_hand(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["hand_size"] = 6
        state["players"]["p2"]["hand_size"] = 7
        program = EffectProgram(
            source_text="both shuffle",
            operations=[EffectOperation(op="script_hook", params={"hook_id": "each-player-shuffles-hand-into-deck"})],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["hand_size"], 0)
        self.assertEqual(state["players"]["p2"]["hand_size"], 0)

    def test_script_hook_infers_recover_from_all_special_conditions(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["active"]["status"] = ["Poisoned", "Asleep"]
        program = EffectProgram(
            source_text="recover statuses",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={"hook_id": "generic_tcg_clause", "clause": "This Pokémon recovers from all Special Conditions."},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["active"]["status"], [])

    def test_script_hook_infers_search_then_shuffle_to_hand(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="search+shuffle",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={
                        "hook_id": "search-then-shuffle-generic",
                        "clause": "Search your deck for up to 2 cards and put them into your hand. Then, shuffle your deck.",
                    },
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["hand_size"], 7)

    def test_script_hook_infers_generic_attack_energy_scaling(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["active"]["energy_attached"] = 3
        program = EffectProgram(
            source_text="attack scale",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={
                        "hook_id": "generic-this-attack-clause",
                        "clause": "This attack does 50 more damage for each {W} Energy attached to this Pokémon.",
                    },
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 0)

    def test_script_hook_infers_discard_hand_and_draw(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["hand_size"] = 6
        program = EffectProgram(
            source_text="discard draw",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={"hook_id": "generic-discard-clause", "clause": "Discard your hand and draw 5 cards."},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["hand_size"], 5)

    def test_script_hook_infers_conditional_nested_effect(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="conditional nested",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={"hook_id": "conditional_clause", "effect": "Draw 2 cards.", "condition": "demo"},
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["hand_size"], 7)

    def test_script_hook_infers_generic_put_recover(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="recover",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={
                        "hook_id": "generic-put-clause",
                        "clause": "Put up to 2 Basic Energy cards from your discard pile into your hand.",
                    },
                )
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p1"]["hand_size"], 7)

    def test_script_hook_unknown_raises_in_strict_mode(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="passthrough",
            operations=[
                EffectOperation(
                    op="script_hook",
                    params={"hook_id": "unrecognized-hook", "clause": "Some new future card text."},
                )
            ],
        )
        with self.assertRaises(RuntimeError):
            apply_effect_program(program, state, actor="p1")

    def test_script_hook_manifest_backed_fallback_is_allowed(self) -> None:
        state = create_demo_state()
        hook_id = "unrecognized-hook"
        clause = "Some new future card text."
        signature = hook_signature(hook_id, clause)
        manifest = {"entries": [{"signature": signature, "hook_id": hook_id, "clause": clause}]}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hook_manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            state["fidelity_contract"]["manifest_path"] = str(path)
            program = EffectProgram(
                source_text="manifest fallback",
                operations=[EffectOperation(op="script_hook", params={"hook_id": hook_id, "clause": clause})],
            )
            events = apply_effect_program(program, state, actor="p1")
        self.assertTrue(any("manifest-backed fallback" in event for event in events))

    def test_pay_cost_operation_updates_turn_flag(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="pay cost",
            operations=[EffectOperation(op="pay_cost", params={"requirements": {"hand_cards": 1}})],
        )
        events = apply_effect_program(program, state, actor="p1")
        self.assertTrue(any("Cost payment succeeded" in event for event in events))
        self.assertTrue(state["players"]["p1"]["turn_flags"]["last_cost_paid"])

    def test_temporary_rule_damage_modifier_is_applied(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="temporary modifier",
            operations=[
                EffectOperation(
                    op="apply_temporary_rule",
                    params={"rule": "bonus", "layer": "DAMAGE_MODIFIER", "modifiers": {"damage": 20}},
                ),
                EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": 30}),
            ],
        )
        apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 70)

    def test_replacement_then_prevention_stack_order(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="stack ordering",
            operations=[
                EffectOperation(
                    op="apply_temporary_rule",
                    params={
                        "rule": "replace_to_80",
                        "kind": "replacement",
                        "priority": 200,
                        "set_amount": 80,
                        "target": "opponent_active",
                    },
                ),
                EffectOperation(
                    op="apply_temporary_rule",
                    params={
                        "rule": "prevent_30",
                        "kind": "prevention",
                        "priority": 100,
                        "prevent_amount": 30,
                        "target": "opponent_active",
                    },
                ),
                EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": 30}),
            ],
        )
        events = apply_effect_program(program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 70)
        replacement_index = next(i for i, event in enumerate(events) if "Replacement rule" in event)
        prevention_index = next(i for i, event in enumerate(events) if "Prevention rule" in event)
        self.assertLess(replacement_index, prevention_index)

    def test_temporary_stack_rule_expires_at_turn_advance(self) -> None:
        state = create_demo_state()
        setup = EffectProgram(
            source_text="one-turn prevention",
            operations=[
                EffectOperation(
                    op="apply_temporary_rule",
                    params={
                        "rule": "one_turn_prevent",
                        "kind": "prevention",
                        "prevent_amount": 20,
                        "turns": 1,
                        "target": "opponent_active",
                    },
                )
            ],
        )
        apply_effect_program(setup, state, actor="p1")
        advance_temporary_rule_durations(state, actor="p1")
        attack = EffectProgram(
            source_text="post expiry damage",
            operations=[EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": 30})],
        )
        apply_effect_program(attack, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 90)

    def test_registered_timing_rule_applies_before_attack(self) -> None:
        state = create_demo_state()
        register = EffectProgram(
            source_text="register timing modifier",
            operations=[
                EffectOperation(
                    op="register_timing_rule",
                    params={
                        "window": "BEFORE_ATTACK",
                        "kind": "replacement",
                        "priority": 100,
                        "turns": 2,
                        "operation": {
                            "op": "apply_temporary_rule",
                            "params": {
                                "rule": "timed_bonus",
                                "kind": "replacement",
                                "set_amount": 30,
                                "target": "opponent_active",
                            },
                        },
                    },
                )
            ],
        )
        apply_effect_program(register, state, actor="p1")
        damage = EffectProgram(
            source_text="timed damage",
            operations=[EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": 20})],
        )
        apply_effect_program(damage, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 90)


if __name__ == "__main__":
    unittest.main()

