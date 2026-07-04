import unittest
from unittest.mock import patch

from core.data_pipeline import run_pipeline_health_check


class DataPipelineTests(unittest.TestCase):
    @patch("core.data_pipeline.fetch_card_detail")
    @patch("core.data_pipeline.fetch_cards_by_regulation_mark")
    def test_pipeline_reports_schema_drift_and_reliability(
        self,
        mock_index,
        mock_detail,
    ) -> None:
        mock_index.return_value = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        def _detail_side_effect(card_id: str):
            if card_id == "a":
                return {"id": "a", "name": "A", "regulationMark": "H", "set": {"id": "x"}}
            if card_id == "b":
                return {"id": "b", "name": "B"}  # intentionally missing keys
            raise RuntimeError("source timeout")

        mock_detail.side_effect = _detail_side_effect

        report = run_pipeline_health_check(limit_cards=3, write_snapshot=False)
        self.assertEqual(report["source_reliability"]["failed_detail_fetches"], 1)
        self.assertTrue(report["schema_drift"]["detected"])
        self.assertGreater(report["schema_drift"]["missing_key_counts"]["regulationMark"], 0)


if __name__ == "__main__":
    unittest.main()

