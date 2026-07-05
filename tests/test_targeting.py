import unittest

from core.effects import create_demo_state
from core.targeting import validate_target_count, validate_target_selector


class TargetingTests(unittest.TestCase):
    def test_validate_target_selector_bench(self) -> None:
        state = create_demo_state()
        result = validate_target_selector(state, "p1", "self_bench")
        self.assertTrue(result.valid)

    def test_validate_target_count_allow_less(self) -> None:
        result = validate_target_count(requested=3, available=1, allow_less=True)
        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()
