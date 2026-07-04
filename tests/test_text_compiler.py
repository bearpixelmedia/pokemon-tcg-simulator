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


if __name__ == "__main__":
    unittest.main()

