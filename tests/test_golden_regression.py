import json
import tempfile
import unittest
from pathlib import Path

from core.golden_regression import run_golden_case, run_golden_suite


class GoldenRegressionTests(unittest.TestCase):
    def test_run_golden_case_executes_operations(self) -> None:
        case = {
            "name": "simple-damage",
            "actor": "p1",
            "operations": [{"op": "deal_damage", "params": {"target": "opponent_active", "amount": 20}}],
        }
        result = run_golden_case(case)
        self.assertEqual(result["name"], "simple-damage")
        self.assertTrue(any("dealt" in event for event in result["events"]))

    def test_run_golden_suite_reads_fixture(self) -> None:
        payload = {
            "cases": [
                {"name": "noop", "operations": [{"op": "annotation_noop", "params": {}}]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "suite.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = run_golden_suite(str(path))
        self.assertEqual(result["count"], 1)


if __name__ == "__main__":
    unittest.main()
