import unittest

from core.effects import create_demo_state
from core.setup_engine import run_setup_phase


class SetupEngineTests(unittest.TestCase):
    def test_setup_phase_sets_opening_invariants(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["hand_size"] = 0
        state["players"]["p2"]["prizes_remaining"] = 0
        events = run_setup_phase(state, seed=1)
        self.assertGreaterEqual(state["players"]["p1"]["hand_size"], 7)
        self.assertEqual(state["players"]["p2"]["prizes_remaining"], 6)
        self.assertTrue(any("Setup phase complete." in event for event in events))


if __name__ == "__main__":
    unittest.main()
