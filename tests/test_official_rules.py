import unittest

from core.effects import create_demo_state
from core.official_rules import (
    MAX_BENCH_SIZE,
    enforce_state_invariants,
    run_official_setup,
    set_turn_context,
    validate_action_against_rules,
)


class OfficialRulesTests(unittest.TestCase):
    def test_opening_player_cannot_attack_or_supporter_on_turn_one(self) -> None:
        state = create_demo_state()
        run_official_setup(state, seed=1, opening_player="p1")
        set_turn_context(state, actor="p1", turn=1)

        attack_ok, _ = validate_action_against_rules(state, "p1", "attack")
        supporter_ok, _ = validate_action_against_rules(state, "p1", "play_supporter")
        self.assertFalse(attack_ok)
        self.assertFalse(supporter_ok)

    def test_opponent_can_attack_on_turn_one(self) -> None:
        state = create_demo_state()
        run_official_setup(state, seed=2, opening_player="p1")
        set_turn_context(state, actor="p2", turn=1)
        attack_ok, _ = validate_action_against_rules(state, "p2", "attack")
        self.assertTrue(attack_ok)

    def test_enforce_state_invariants_caps_bench(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["bench_size"] = 10
        events = enforce_state_invariants(state)
        self.assertEqual(state["players"]["p1"]["bench_size"], MAX_BENCH_SIZE)
        self.assertTrue(any("capped" in event for event in events))

    def test_setup_applies_mulligan_bonus_draw(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["opening_has_basic"] = False
        state["players"]["p2"]["opening_has_basic"] = True
        events = run_official_setup(state, seed=3, opening_player="p1")
        self.assertGreaterEqual(state["players"]["p2"]["hand_size"], 7)
        self.assertTrue(any("mulligan" in event.lower() for event in events))


if __name__ == "__main__":
    unittest.main()
