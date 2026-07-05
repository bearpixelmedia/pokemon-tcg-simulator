import unittest

from core.effects import create_demo_state
from core.state_model import from_demo_state


class StateModelTests(unittest.TestCase):
    def test_from_demo_state_creates_runtime_model(self) -> None:
        runtime = from_demo_state(create_demo_state())
        self.assertIn("p1", runtime.players)
        self.assertIsNotNone(runtime.players["p1"].active)
        self.assertGreaterEqual(len(runtime.players["p1"].hand), 1)


if __name__ == "__main__":
    unittest.main()
