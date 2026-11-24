import unittest

from core.cost_engine import evaluate_attack_cost, pay_cost
from core.effects import create_demo_state


class CostEngineTests(unittest.TestCase):
    def test_pay_cost_rolls_back_on_failure(self) -> None:
        state = create_demo_state()
        original = state["players"]["p1"]["hand_size"]
        result = pay_cost(state, "p1", {"hand_cards": original + 5})
        self.assertFalse(result.paid)
        self.assertEqual(state["players"]["p1"]["hand_size"], original)

    def test_pay_cost_succeeds_for_hand_and_energy(self) -> None:
        state = create_demo_state()
        result = pay_cost(state, "p1", {"hand_cards": 1, "active_energy": 1})
        self.assertTrue(result.paid)

    def test_evaluate_attack_cost_matches_typed_symbols(self) -> None:
        state = create_demo_state()
        active = state["players"]["p1"]["active"]
        active["attached_energy_cards"] = [
            {"id": "e1", "energy_type": "R"},
            {"id": "e2", "energy_type": "C"},
        ]
        active["energy_attached"] = 2
        result = evaluate_attack_cost(active, {"cost": ["R", "C"]})
        self.assertTrue(result.payable)
        self.assertEqual(result.code, "ok")

    def test_evaluate_attack_cost_reports_missing_symbols(self) -> None:
        state = create_demo_state()
        active = state["players"]["p1"]["active"]
        active["attached_energy_cards"] = [{"id": "e1", "energy_type": "W"}]
        active["energy_attached"] = 1
        result = evaluate_attack_cost(active, {"cost": ["R", "C"]})
        self.assertFalse(result.payable)
        self.assertEqual(result.code, "insufficient_energy")
        self.assertIn("R", result.missing_symbols)


if __name__ == "__main__":
    unittest.main()
