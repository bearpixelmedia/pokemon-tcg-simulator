import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.yolo_pipeline import run_yolo_pipeline


def _fake_coverage(resolution: float = 40.0, resolved_blocks: int = 40) -> dict:
    return {
        "metadata": {"cards_scanned": 10, "templates_supported": 5},
        "summary": {
            "total_text_blocks": 100,
            "resolved_text_blocks": resolved_blocks,
            "unresolved_text_blocks": 100 - resolved_blocks,
            "text_resolution_percent": resolution,
        },
        "card_summary": {
            "cards_with_text_blocks": 10,
            "fully_resolved_cards": 3,
            "partially_or_unresolved_cards": 7,
        },
        "top_unresolved_clauses": [
            ["Search your deck for up to 2 Basic Energy cards and attach them.", 20],
            ["During your opponent's next turn, prevent all damage done to this Pokémon.", 15],
        ],
    }


class YoloPipelineTests(unittest.TestCase):
    def test_pipeline_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("core.yolo_pipeline.run_standard_coverage_analysis", return_value=_fake_coverage()):
                report = run_yolo_pipeline(limit_cards=10, output_dir=temp_dir, force_refresh=True)

            artifacts = report["artifacts"]
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), f"Missing artifact {artifact_path}")

            with open(artifacts["yolo_latest"], encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertIn("coverage_summary", saved)
            self.assertIn("recommendation_summary", saved)

    def test_pipeline_delta_available_after_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("core.yolo_pipeline.run_standard_coverage_analysis", return_value=_fake_coverage(40.0, 40)):
                first = run_yolo_pipeline(limit_cards=10, output_dir=temp_dir, force_refresh=True)
            self.assertFalse(first["delta_from_previous"]["available"])

            with patch("core.yolo_pipeline.run_standard_coverage_analysis", return_value=_fake_coverage(55.0, 55)):
                second = run_yolo_pipeline(limit_cards=10, output_dir=temp_dir, force_refresh=True)
            self.assertTrue(second["delta_from_previous"]["available"])
            self.assertEqual(second["delta_from_previous"]["resolved_text_blocks_delta"], 15)


if __name__ == "__main__":
    unittest.main()

