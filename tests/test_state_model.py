import unittest

from core.effects import create_demo_state
from core.setup_engine import run_setup_phase
from core.state_model import from_demo_state


class StateModelTests(unittest.TestCase):
    def test_from_demo_state_creates_runtime_model(self) -> None:
        runtime = from_demo_state(create_demo_state())
        self.assertIn("p1", runtime.players)
        self.assertIsNotNone(runtime.players["p1"].active)
        self.assertGreaterEqual(len(runtime.players["p1"].hand), 1)

    def test_runtime_model_preserves_zone_card_identity(self) -> None:
        state = create_demo_state()
        run_setup_phase(state, seed=17)
        runtime = from_demo_state(state)
        self.assertTrue(runtime.players["p1"].active.card.card_id.startswith("p1-"))
        self.assertTrue(all(card.card_id.startswith("p1-") for card in runtime.players["p1"].hand))


if __name__ == "__main__":
    unittest.main()
