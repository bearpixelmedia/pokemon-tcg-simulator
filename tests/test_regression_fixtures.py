import json
import random
import unittest
from pathlib import Path

from core.effect_types import EffectOperation, EffectProgram
from core.effects import apply_effect_program, create_demo_state

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "regression_cases.json"


class RegressionFixtureTests(unittest.TestCase):
    def test_regression_cases(self) -> None:
        cases = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                state = create_demo_state()
                setup_operations = [EffectOperation(**op) for op in case.get("setup_operations", [])]
                if setup_operations:
                    setup_program = EffectProgram(source_text=case["name"], operations=setup_operations)
                    apply_effect_program(
                        setup_program,
                        state,
                        actor=case.get("setup_actor", case.get("actor", "p1")),
                        rng=random.Random(1),
                    )

                program = EffectProgram(
                    source_text=case["name"],
                    operations=[EffectOperation(**op) for op in case["operations"]],
                )
                apply_effect_program(
                    program,
                    state,
                    actor=case.get("actor", "p1"),
                    rng=random.Random(1),
                )

                if "expected_statuses" in case:
                    self.assertEqual(state["players"]["p1"]["active"]["status"], case["expected_statuses"])
                if "expected_target_hp" in case:
                    self.assertEqual(state["players"]["p2"]["active"]["hp"], case["expected_target_hp"])


if __name__ == "__main__":
    unittest.main()

