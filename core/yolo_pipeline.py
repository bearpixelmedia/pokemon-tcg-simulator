from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.standard_coverage import run_standard_coverage_analysis
from core.template_mining import mine_unresolved_templates

DEFAULT_OUTPUT_DIR = Path("/workspace/artifacts/yolo")


def _ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _serialize_json(path: Path, payload: dict[str, Any]) -> str:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_delta(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {"available": False}

    cur_summary = current.get("summary", {})
    prev_summary = previous.get("summary", {})
    cur_card = current.get("card_summary", {})
    prev_card = previous.get("card_summary", {})

    return {
        "available": True,
        "text_resolution_percent_delta": round(
            float(cur_summary.get("text_resolution_percent", 0))
            - float(prev_summary.get("text_resolution_percent", 0)),
            2,
        ),
        "resolved_text_blocks_delta": int(cur_summary.get("resolved_text_blocks", 0))
        - int(prev_summary.get("resolved_text_blocks", 0)),
        "fully_resolved_cards_delta": int(cur_card.get("fully_resolved_cards", 0))
        - int(prev_card.get("fully_resolved_cards", 0)),
    }


def run_yolo_pipeline(
    limit_cards: int | None = 350,
    marks: tuple[str, ...] = ("H", "I", "J"),
    include_examples: bool = True,
    force_refresh: bool = False,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    output_path = _ensure_output_dir(Path(output_dir))
    timestamp = started.strftime("%Y%m%dT%H%M%SZ")

    coverage = run_standard_coverage_analysis(
        limit_cards=limit_cards,
        marks=marks,
        include_examples=include_examples,
        force_refresh=force_refresh,
    )
    mining = mine_unresolved_templates(coverage, top_n=30, sample_size=4)

    latest_coverage_path = output_path / "coverage_latest.json"
    latest_mining_path = output_path / "mining_latest.json"
    latest_yolo_path = output_path / "yolo_latest.json"
    coverage_history_path = output_path / f"coverage_{timestamp}.json"
    mining_history_path = output_path / f"mining_{timestamp}.json"
    yolo_history_path = output_path / f"yolo_{timestamp}.json"

    previous_coverage = _load_json(latest_coverage_path)
    delta = _build_delta(coverage, previous_coverage)

    yolo_report = {
        "metadata": {
            "run_id": timestamp,
            "generated_at": datetime.now(UTC).isoformat(),
            "marks": list(marks),
            "limit_cards": limit_cards,
            "include_examples": include_examples,
            "force_refresh": force_refresh,
            "output_dir": str(output_path),
        },
        "coverage_summary": coverage.get("summary", {}),
        "card_summary": coverage.get("card_summary", {}),
        "delta_from_previous": delta,
        "recommendation_summary": {
            "clustered_unresolved_blocks": mining.get("clustered_unresolved_blocks", 0),
            "coverage_of_unresolved_by_clusters_percent": mining.get(
                "coverage_of_unresolved_by_clusters_percent", 0
            ),
            "top_recommendations": mining.get("clusters", [])[:10],
        },
        "artifacts": {},
    }

    yolo_report["artifacts"] = {
        "coverage_latest": _serialize_json(latest_coverage_path, coverage),
        "mining_latest": _serialize_json(latest_mining_path, mining),
        "yolo_latest": _serialize_json(latest_yolo_path, yolo_report),
        "coverage_history": _serialize_json(coverage_history_path, coverage),
        "mining_history": _serialize_json(mining_history_path, mining),
        "yolo_history": _serialize_json(yolo_history_path, yolo_report),
    }

    return yolo_report

