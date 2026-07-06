import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.quality_gates import run_quality_gates


class QualityGateTests(unittest.TestCase):
    @patch("core.quality_gates.run_real_game_fixture_suite")
    @patch("core.quality_gates.run_strict_fidelity_audit")
    @patch("core.quality_gates.verify_seed_replay")
    @patch("core.quality_gates.build_standard_legality_snapshot")
    @patch("core.quality_gates.run_standard_coverage_analysis")
    def test_quality_gates_detect_regression(
        self,
        mock_coverage,
        mock_legality,
        mock_replay,
        mock_fidelity_audit,
        mock_real_game_suite,
    ) -> None:
        mock_coverage.return_value = {
            "summary": {"text_resolution_percent": 45.0},
            "card_summary": {},
            "metadata": {},
        }
        mock_legality.return_value = {"summary": {"legal_cards": 10}}
        mock_replay.return_value = {"deterministic": True}
        mock_fidelity_audit.return_value = {
            "script_hook_registration": {"percent": 100.0},
            "operation_mix": {"script_hook_share_percent": 5.0},
        }
        mock_real_game_suite.return_value = {"count": 2, "passed": True, "cases": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = Path(temp_dir) / "baseline.json"
            baseline_path.write_text(
                '{"summary":{"text_resolution_percent":60.0}}',
                encoding="utf-8",
            )
            report = run_quality_gates(baseline_path=baseline_path)

        self.assertFalse(report["quality_pass"])
        self.assertTrue(report["baseline"]["regression_detected"])


if __name__ == "__main__":
    unittest.main()

