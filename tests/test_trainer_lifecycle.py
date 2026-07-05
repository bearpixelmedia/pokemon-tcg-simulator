import unittest

from core.effects import create_demo_state
from core.trainer_lifecycle import (
    attach_tool,
    can_play_supporter,
    play_stadium,
    play_supporter,
    reset_turn_flags,
)


class TrainerLifecycleTests(unittest.TestCase):
    def test_supporter_once_per_turn(self) -> None:
        state = create_demo_state()
        reset_turn_flags(state, "p1")

        ok, events = play_supporter(state, "p1")
        self.assertTrue(ok)
        self.assertTrue(any("played a Supporter" in event for event in events))

        can_again, reason = can_play_supporter(state, "p1")
        self.assertFalse(can_again)
        self.assertIn("already played", reason.lower())

    def test_stadium_play_replaces_board_stadium(self) -> None:
        state = create_demo_state()
        reset_turn_flags(state, "p1")
        ok, _ = play_stadium(state, "p1")
        self.assertTrue(ok)
        self.assertEqual(state["board"]["stadium"], "p1-stadium")

    def test_attach_tool_respects_one_per_turn_flag(self) -> None:
        state = create_demo_state()
        reset_turn_flags(state, "p1")
        ok, _ = attach_tool(state, "p1")
        self.assertTrue(ok)
        self.assertTrue(state["players"]["p1"]["active"]["tool_attached"])

        ok_again, events = attach_tool(state, "p1")
        self.assertFalse(ok_again)
        self.assertTrue(any("could not attach Tool" in event for event in events))


if __name__ == "__main__":
    unittest.main()

