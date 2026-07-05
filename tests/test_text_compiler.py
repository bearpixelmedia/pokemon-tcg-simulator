import unittest

from core.text_compiler import compile_effect_text
from core.unresolved_registry import clear_unresolved_registry, snapshot_unresolved_registry


class TextCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_unresolved_registry()

    def test_damage_and_status_resolves(self) -> None:
        program = compile_effect_text("30 damage. Your opponent's Active Pokémon is now Poisoned.")
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(len(program.operations), 2)
        self.assertEqual(program.operations[0].op, "deal_damage")
        self.assertEqual(program.operations[1].op, "apply_status")

    def test_search_deck_template_resolves(self) -> None:
        text = (
            "Search your deck for a Basic Pokémon card, reveal it, and put it into your hand. "
            "Then, shuffle your deck."
        )
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual([op.op for op in program.operations], ["search_deck_to_hand", "shuffle_deck"])

    def test_coin_flip_branch_resolves(self) -> None:
        text = (
            "Flip a coin. If heads, this attack does 30 more damage. "
            "If tails, this Pokémon is now Confused."
        )
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(len(program.operations), 1)
        self.assertEqual(program.operations[0].op, "flip_coin")
        coin_params = program.operations[0].params
        self.assertIn("heads", coin_params)
        self.assertIn("tails", coin_params)
        self.assertEqual(coin_params["heads_unresolved"], None)
        self.assertEqual(coin_params["tails_unresolved"], None)

    def test_unresolved_text_is_reported(self) -> None:
        program = compile_effect_text("You may play any number of Item cards during your turn.")
        self.assertFalse(program.is_fully_resolved)
        self.assertIsNotNone(program.unresolved_text)
        registry = snapshot_unresolved_registry(limit=10)
        self.assertGreaterEqual(registry["total_unique_clauses"], 1)

    def test_script_fallback_resolves_known_clause(self) -> None:
        text = "Discard your hand and draw 7 cards."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "script_hook")

    def test_optional_clause_composition(self) -> None:
        text = "You may draw 2 cards."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "optional_effect")

    def test_conditional_clause_composition(self) -> None:
        text = "If you have no cards in your hand, draw 3 cards."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "conditional_effect")

    def test_recoil_clause_resolves(self) -> None:
        program = compile_effect_text("This Pokémon also does 20 damage to itself.")
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "deal_damage")
        self.assertEqual(program.operations[0].params["target"], "self_active")

    def test_draw_a_card_resolves(self) -> None:
        program = compile_effect_text("Draw a card.")
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "draw_cards")
        self.assertEqual(program.operations[0].params["count"], 1)

    def test_single_branch_coin_flip_resolves(self) -> None:
        text = "Flip a coin. If tails, this attack does nothing."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "flip_coin")

    def test_switch_this_pokemon_resolves(self) -> None:
        text = "Switch this Pokémon with 1 of your Benched Pokémon."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "switch_active_with_bench")

    def test_search_deck_to_bench_resolves(self) -> None:
        text = "Search your deck for up to 2 Basic Pokémon and put them onto your Bench. Then, shuffle your deck."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "search_deck_to_bench")

    def test_parenthetical_noop_clause_resolves(self) -> None:
        program = compile_effect_text("(Your opponent chooses the new Active Pokémon.)")
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "annotation_noop")

    def test_prevent_all_damage_clause_resolves(self) -> None:
        text = "During your opponent's next turn, prevent all damage from and effects of attacks done to this Pokémon."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "script_hook")

    def test_ignore_all_modifiers_clause_resolves(self) -> None:
        text = "This attack's damage isn't affected by Weakness or Resistance, or by any effects on your opponent's Active Pokémon."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(len(program.operations), 2)

    def test_flip_multiple_coins_damage_clause_resolves(self) -> None:
        text = "Flip 2 coins. This attack does 10 damage for each heads."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "flip_coins_for_damage")

    def test_once_during_turn_ability_note_resolves(self) -> None:
        text = "Once during your turn, you may use this Ability."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "annotation_noop")

    def test_item_lock_clause_resolves(self) -> None:
        text = "During your opponent's next turn, they can't play any Item cards from their hand."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "apply_temporary_rule")

    def test_once_during_turn_attach_energy_resolves(self) -> None:
        text = "Once during your turn, you may attach a Basic {G} Energy card from your hand to this Pokémon."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "triggered_effect")

    def test_damage_per_prize_taken_resolves(self) -> None:
        text = "This attack does 50 more damage for each Prize card your opponent has taken."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "damage_per_prize_taken")

    def test_search_evolution_from_deck_resolves(self) -> None:
        text = "Search your deck for a card that evolves from this Pokémon and put it onto this Pokémon to evolve it. Then, shuffle your deck."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "evolve_from_deck")

    def test_reveal_and_shuffle_random_hand_card_resolves(self) -> None:
        text = "Choose a random card from your opponent's hand. Your opponent reveals that card and shuffles it into their deck."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(len(program.operations), 2)

    def test_tool_card_rule_text_resolves(self) -> None:
        text = "Play this card as if it were a 60-HP Basic {C} Pokémon. This card can't be affected by any Special Conditions and can't retreat. At any time during your turn, you may discard this card from play."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(len(program.operations), 3)

    def test_prevent_damage_from_basic_pokemon_resolves(self) -> None:
        text = "During your opponent's next turn, prevent all damage done to this Pokémon by attacks from Basic Pokémon."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "apply_temporary_rule")

    def test_discard_top_n_cards_resolves(self) -> None:
        text = "Discard the top 2 cards of your opponent's deck."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "mill_top_deck")

    def test_conditional_discard_all_energy_combo_resolves(self) -> None:
        text = "If your opponent's Active Pokémon is an Evolution Pokémon, this attack does 140 more damage, and discard all Energy from this Pokémon."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "conditional_effect")

    def test_then_shuffle_your_deck_resolves(self) -> None:
        program = compile_effect_text("Then, shuffle your deck.")
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "shuffle_deck")

    def test_search_up_to_n_pokemon_to_hand_resolves(self) -> None:
        text = "Search your deck for up to 3 Pokémon, reveal them, and put them into your hand. Then, shuffle your deck."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(program.operations[0].op, "search_deck_to_hand")

    def test_status_asleep_and_poisoned_resolves(self) -> None:
        text = "Your opponent's Active Pokémon is now Asleep and Poisoned."
        program = compile_effect_text(text)
        self.assertTrue(program.is_fully_resolved)
        self.assertEqual(len(program.operations), 2)


if __name__ == "__main__":
    unittest.main()

