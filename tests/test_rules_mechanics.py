import unittest

from core.effects import create_demo_state
from core.rules_mechanics import (
    attempt_devolve,
    attempt_evolve,
    attempt_retreat,
    resolve_knockouts_and_prizes,
)


class RulesMechanicsTests(unittest.TestCase):
    def test_retreat_requires_bench_and_energy(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["bench_size"] = 1
        state["players"]["p1"]["active"]["energy_attached"] = 1
        ok, events = attempt_retreat(state, "p1")
        self.assertTrue(ok)
        self.assertTrue(any("retreated" in event for event in events))

    def test_evolve_and_devolve_progression(self) -> None:
        state = create_demo_state()
        ok, _ = attempt_evolve(state, "p1")
        self.assertTrue(ok)
        self.assertEqual(state["players"]["p1"]["active"]["stage"], "Stage1")

        ok, _ = attempt_devolve(state, "p1")
        self.assertTrue(ok)
        self.assertEqual(state["players"]["p1"]["active"]["stage"], "Basic")

    def test_knockout_awards_prize(self) -> None:
        state = create_demo_state()
        state["players"]["p2"]["active"]["hp"] = 0
        events = resolve_knockouts_and_prizes(state)
        self.assertTrue(any("Knocked Out" in event for event in events))
        self.assertEqual(state["players"]["p1"]["prizes_remaining"], 5)


if __name__ == "__main__":
    unittest.main()

