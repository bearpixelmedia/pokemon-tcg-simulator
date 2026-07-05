import unittest

from core.standard_coverage import analyze_text_blocks, extract_text_blocks


class StandardCoverageTests(unittest.TestCase):
    def test_extract_text_blocks_collects_trainer_ability_and_attacks(self) -> None:
        card = {
            "id": "demo-1",
            "name": "Demo Card",
            "trainerType": "Item",
            "effect": "Draw 2 cards.",
            "abilities": [{"name": "Tutor", "effect": "Search your deck for a Basic Pokémon card, reveal it, and put it into your hand. Then, shuffle your deck."}],
            "attacks": [
                {"name": "Simple Hit", "damage": 30},
                {"name": "Poison Hit", "effect": "Your opponent's Active Pokémon is now Poisoned."},
            ],
        }

        blocks = extract_text_blocks(card)
        self.assertEqual(len(blocks), 4)
        source_types = {block["source_type"] for block in blocks}
        self.assertIn("trainer_effect", source_types)
        self.assertIn("ability_effect", source_types)
        self.assertIn("attack_damage_only", source_types)
        self.assertIn("attack_effect", source_types)

    def test_analyze_text_blocks_marks_resolved_and_unresolved(self) -> None:
        blocks = [
            {"source_type": "attack_effect", "source_name": "Hit", "text": "30 damage."},
            {
                "source_type": "attack_effect",
                "source_name": "Unknown",
                "text": "Frobulate until the match state sparkles.",
            },
        ]

        analyzed = analyze_text_blocks("demo-2", "Demo", "H", blocks)
        self.assertEqual(len(analyzed), 2)
        self.assertTrue(analyzed[0]["is_resolved"])
        self.assertFalse(analyzed[1]["is_resolved"])


if __name__ == "__main__":
    unittest.main()

