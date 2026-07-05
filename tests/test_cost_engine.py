import unittest

from core.cost_engine import pay_cost
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


if __name__ == "__main__":
    unittest.main()
