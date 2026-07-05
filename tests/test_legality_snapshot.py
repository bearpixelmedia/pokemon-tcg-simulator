import unittest
from unittest.mock import patch

from core.legality_snapshot import build_standard_legality_snapshot


class LegalitySnapshotTests(unittest.TestCase):
    @patch("core.legality_snapshot.fetch_card_detail")
    @patch("core.legality_snapshot.fetch_cards_by_regulation_mark")
    def test_release_gate_blocks_recent_cards(self, mock_index, mock_detail) -> None:
        mock_index.return_value = [
            {"id": "c1", "regulationMark": "H"},
            {"id": "c2", "regulationMark": "I"},
        ]
        mock_detail.side_effect = [
            {"id": "c1", "name": "Old Card", "regulationMark": "H", "set": {"releaseDate": "2025-01-01"}},
            {"id": "c2", "name": "Recent Card", "regulationMark": "I", "set": {"releaseDate": "2026-07-01"}},
        ]

        snapshot = build_standard_legality_snapshot(
            as_of_date="2026-07-04",
            waiting_days=14,
            limit_cards=2,
        )
        self.assertEqual(snapshot["summary"]["legal_cards"], 1)
        self.assertEqual(snapshot["summary"]["blocked_by_release_gate_or_other"], 1)

    @patch("core.legality_snapshot.fetch_card_detail")
    @patch("core.legality_snapshot.fetch_cards_by_regulation_mark")
    def test_reprint_override_marks_legacy_print_as_legal(self, mock_index, mock_detail) -> None:
        mock_index.return_value = [{"id": "c1", "regulationMark": "G"}]
        mock_detail.return_value = {
            "id": "c1",
            "name": "Rare Candy",
            "regulationMark": "G",
            "set": {"releaseDate": "2021-01-01"},
        }

        snapshot = build_standard_legality_snapshot(
            as_of_date="2026-07-04",
            waiting_days=14,
            marks=("H", "I", "J"),
            limit_cards=1,
        )
        self.assertEqual(snapshot["summary"]["legal_via_reprint"], 1)
        self.assertEqual(snapshot["summary"]["cards_with_errata"], 1)
        self.assertEqual(snapshot["summary"]["legal_cards"], 1)


if __name__ == "__main__":
    unittest.main()

