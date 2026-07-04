from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.standard_coverage import fetch_card_detail, fetch_cards_by_regulation_mark

DEFAULT_PIPELINE_SNAPSHOT = Path("/workspace/artifacts/pipeline/health_latest.json")
EXPECTED_TOP_LEVEL_KEYS = {
    "id",
    "name",
    "regulationMark",
    "set",
}


def run_pipeline_health_check(
    marks: tuple[str, ...] = ("H", "I", "J"),
    limit_cards: int | None = 200,
    write_snapshot: bool = True,
    snapshot_path: str | Path = DEFAULT_PIPELINE_SNAPSHOT,
) -> dict[str, Any]:
    indexed_cards = fetch_cards_by_regulation_mark(marks=marks)
    cards_to_scan = indexed_cards[:limit_cards] if limit_cards and limit_cards > 0 else indexed_cards

    missing_key_counts: dict[str, int] = {key: 0 for key in EXPECTED_TOP_LEVEL_KEYS}
    schema_drift_examples: list[dict[str, Any]] = []
    detail_failures: list[dict[str, str]] = []

    for card in cards_to_scan:
        card_id = card["id"]
        try:
            detail = fetch_card_detail(card_id)
        except Exception as error:
            detail_failures.append({"id": card_id, "error": str(error)})
            continue

        missing = [key for key in EXPECTED_TOP_LEVEL_KEYS if key not in detail]
        for key in missing:
            missing_key_counts[key] += 1
        if missing and len(schema_drift_examples) < 25:
            schema_drift_examples.append({"id": card_id, "missing_keys": missing})

    scanned = len(cards_to_scan)
    failures = len(detail_failures)
    successful = scanned - failures
    reliability_percent = round((successful / scanned * 100) if scanned else 0, 2)
    schema_drift_detected = any(count > 0 for count in missing_key_counts.values())

    report = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "marks": list(marks),
            "cards_available": len(indexed_cards),
            "cards_scanned": scanned,
        },
        "source_reliability": {
            "successful_detail_fetches": successful,
            "failed_detail_fetches": failures,
            "reliability_percent": reliability_percent,
            "failure_examples": detail_failures[:25],
        },
        "schema_drift": {
            "detected": schema_drift_detected,
            "missing_key_counts": missing_key_counts,
            "examples": schema_drift_examples,
        },
    }

    if write_snapshot:
        path = Path(snapshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact_path"] = str(path)

    return report

