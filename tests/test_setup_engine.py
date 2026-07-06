import unittest

from core.battle_state import zone_conservation_report
from core.effects import create_demo_state
from core.setup_engine import run_setup_phase


class SetupEngineTests(unittest.TestCase):
    def test_setup_phase_sets_opening_invariants(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["hand_size"] = 0
        state["players"]["p2"]["prizes_remaining"] = 0
        events = run_setup_phase(state, seed=1)
        self.assertGreaterEqual(state["players"]["p1"]["hand_size"], 1)
        self.assertEqual(state["players"]["p2"]["prizes_remaining"], 6)
        self.assertIn("active", state["players"]["p1"])
        self.assertTrue(any("Setup phase complete." in event for event in events))
        conservation = zone_conservation_report(state)
        self.assertTrue(conservation["all_passed"])


if __name__ == "__main__":
    unittest.main()
