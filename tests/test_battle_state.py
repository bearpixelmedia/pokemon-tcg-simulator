import unittest

from core.battle_state import ensure_battle_state, zone_conservation_report
from core.effects import create_demo_state
from core.setup_engine import run_setup_phase


class BattleStateTests(unittest.TestCase):
    def test_ensure_battle_state_fills_identity_stable_zones(self) -> None:
        state = create_demo_state()
        ensure_battle_state(state)
        for actor in ("p1", "p2"):
            player = state["players"][actor]
            self.assertIsInstance(player.get("deck_cards"), list)
            self.assertIsInstance(player.get("hand_cards"), list)
            self.assertIsInstance(player.get("prize_cards"), list)
            self.assertIsInstance(player.get("discard_pile"), list)
            self.assertIsInstance(player.get("bench"), list)
            self.assertGreater(len(player.get("deck_cards", [])), 0)

    def test_zone_conservation_after_setup(self) -> None:
        state = create_demo_state()
        run_setup_phase(state, seed=13)
        report = zone_conservation_report(state)
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["players"]["p1"]["counted_cards"], 60)
        self.assertEqual(report["players"]["p2"]["counted_cards"], 60)


if __name__ == "__main__":
    unittest.main()
