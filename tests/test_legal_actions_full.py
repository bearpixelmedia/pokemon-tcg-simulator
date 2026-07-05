import unittest

from core.effects import create_demo_state
from core.legal_actions_full import generate_legal_actions_full
from core.official_rules import run_official_setup, set_turn_context


class LegalActionsFullTests(unittest.TestCase):
    def test_generate_legal_actions_full_returns_reasoned_actions(self) -> None:
        state = create_demo_state()
        actions = generate_legal_actions_full(state, "p1")
        self.assertTrue(any(action["action_type"] == "attack" for action in actions))
        self.assertTrue(all("reason" in action for action in actions))

    def test_first_turn_opening_player_attack_is_illegal(self) -> None:
        state = create_demo_state()
        run_official_setup(state, seed=5, opening_player="p1")
        set_turn_context(state, actor="p1", turn=1)
        actions = generate_legal_actions_full(state, "p1")
        attack = next(action for action in actions if action["action_type"] == "attack")
        self.assertFalse(attack["legal"])


if __name__ == "__main__":
    unittest.main()
