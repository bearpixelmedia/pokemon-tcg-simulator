import json
import unittest
from pathlib import Path
from typing import Any

from core.real_game_fidelity import run_real_game_fixture, run_real_game_fixture_suite


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "real_games"


def _assert_subset(testcase: unittest.TestCase, expected: Any, actual: Any, path: str = "root") -> None:
    if isinstance(expected, dict):
        testcase.assertIsInstance(actual, dict, msg=f"{path}: expected dict")
        for key, value in expected.items():
            testcase.assertIn(key, actual, msg=f"{path}: missing key '{key}'")
            _assert_subset(testcase, value, actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        testcase.assertEqual(expected, actual, msg=f"{path}: list mismatch")
        return
    testcase.assertEqual(expected, actual, msg=f"{path}: value mismatch")


class RealGameFidelityTests(unittest.TestCase):
    def test_real_game_fixtures_match_expected_turn_snapshots(self) -> None:
        fixture_paths = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertGreaterEqual(len(fixture_paths), 2)

        for fixture_path in fixture_paths:
            fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            result = run_real_game_fixture(fixture_path)
            self.assertGreaterEqual(len(result["turns"]), 1, msg=f"{fixture_path.name}: no turns executed")

            for turn_index, fixture_turn in enumerate(fixture_payload.get("turns", []), start=1):
                expected_snapshot = fixture_turn.get("expected_snapshot")
                if expected_snapshot is None:
                    continue
                actual_snapshot = result["turns"][turn_index - 1]["snapshot"]
                _assert_subset(self, expected_snapshot, actual_snapshot, path=f"{fixture_path.name}.turn{turn_index}")

    def test_real_game_fixture_suite_reports_passed(self) -> None:
        report = run_real_game_fixture_suite(FIXTURE_DIR)
        self.assertGreaterEqual(report["count"], 2)
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
