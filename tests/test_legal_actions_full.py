import unittest

from core.effects import create_demo_state
from core.legal_actions_full import generate_legal_actions_full


class LegalActionsFullTests(unittest.TestCase):
    def test_generate_legal_actions_full_returns_reasoned_actions(self) -> None:
        state = create_demo_state()
        actions = generate_legal_actions_full(state, "p1")
        self.assertTrue(any(action["action_type"] == "attack" for action in actions))
        self.assertTrue(all("reason" in action for action in actions))


if __name__ == "__main__":
    unittest.main()
