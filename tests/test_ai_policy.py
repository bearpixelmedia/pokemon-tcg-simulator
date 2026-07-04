import random
import unittest

from core.ai_policy import choose_action_heuristic, generate_legal_actions
from core.effects import create_demo_state


class AIPolicyTests(unittest.TestCase):
    def test_generate_legal_actions_includes_attack_and_pass(self) -> None:
        state = create_demo_state()
        actions = generate_legal_actions(state, "p1")
        action_types = {action["action_type"] for action in actions}

        self.assertIn("attack", action_types)
        self.assertIn("pass", action_types)

    def test_generate_legal_actions_blocks_retreat_when_asleep(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["active"]["status"] = ["Asleep"]
        actions = generate_legal_actions(state, "p1")
        action_types = [action["action_type"] for action in actions]
        self.assertNotIn("retreat", action_types)

    def test_heuristic_prefers_finishing_attack(self) -> None:
        state = create_demo_state()
        state["players"]["p2"]["active"]["hp"] = 30
        actions = generate_legal_actions(state, "p1")
        selected = choose_action_heuristic(state, "p1", actions, random.Random(5))

        self.assertEqual(selected["action_type"], "attack")
        self.assertEqual(selected["blueprint_key"], "volatile_strike")


if __name__ == "__main__":
    unittest.main()

