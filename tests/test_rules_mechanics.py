import unittest

from core.effect_types import EffectOperation, EffectProgram
from core.effects import apply_effect_program
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

    def test_damage_reduction_and_prevent_hook(self) -> None:
        state = create_demo_state()
        reduction_program = EffectProgram(
            source_text="reduction",
            operations=[
                EffectOperation(
                    op="modify_incoming_damage_next_turn",
                    params={"target": "self_active", "amount": 20},
                )
            ],
        )
        apply_effect_program(reduction_program, state, actor="p2")
        damage_program = EffectProgram(
            source_text="damage",
            operations=[EffectOperation(op="deal_damage", params={"target": "opponent_active", "amount": 50})],
        )
        apply_effect_program(damage_program, state, actor="p1")
        self.assertEqual(state["players"]["p2"]["active"]["hp"], 90)


if __name__ == "__main__":
    unittest.main()

