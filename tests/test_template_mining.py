import unittest

from core.template_mining import clause_signature, mine_unresolved_templates


class TemplateMiningTests(unittest.TestCase):
    def test_clause_signature_normalizes_numbers(self) -> None:
        signature = clause_signature("During your opponent's next turn, this Pokémon takes 30 less damage.")
        self.assertIn("{n}", signature)
        self.assertNotIn("30", signature)

    def test_mining_returns_clusters(self) -> None:
        coverage_report = {
            "summary": {"unresolved_text_blocks": 8},
            "top_unresolved_clauses": [
                ["Search your deck for up to 2 Basic Energy cards and attach them.", 3],
                ["Search your deck for up to 3 Basic Energy cards and attach them.", 2],
                ["Choose 2 of your opponent's Benched Pokémon.", 2],
                ["Choose 1 of your opponent's Benched Pokémon.", 1],
            ],
        }
        mined = mine_unresolved_templates(coverage_report, top_n=5, sample_size=2)
        self.assertGreaterEqual(len(mined["clusters"]), 2)
        self.assertEqual(mined["total_unresolved_blocks"], 8)
        self.assertTrue(
            any("{n}" in cluster["signature"] for cluster in mined["clusters"]),
            "Expected at least one numeric placeholder in cluster signatures",
        )


if __name__ == "__main__":
    unittest.main()

