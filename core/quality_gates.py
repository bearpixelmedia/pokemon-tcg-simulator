from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.battle_state import zone_conservation_report
from core.effects import create_demo_state
from core.fidelity_audit import run_strict_fidelity_audit
from core.golden_regression import run_golden_suite
from core.legality_snapshot import build_standard_legality_snapshot
from core.real_game_fidelity import run_real_game_fixture_suite
from core.setup_engine import run_setup_phase
from core.standard_coverage import run_standard_coverage_analysis
from core.turn_engine import verify_seed_replay

DEFAULT_BASELINE_PATH = Path("artifacts/quality/coverage_baseline.json")
DEFAULT_DASHBOARD_PATH = Path("artifacts/quality/coverage_dashboard.html")
DEFAULT_GOLDEN_SUITE_PATH = Path("tests/fixtures/golden_suite.json")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _save_dashboard(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    coverage = payload.get("coverage", {})
    legality = payload.get("legality", {})
    baseline = payload.get("baseline", {})
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Quality Gate Coverage Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 12px; }}
    .ok {{ color: #18794e; font-weight: 700; }}
    .bad {{ color: #c92a2a; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Pokemon TCG Quality Dashboard</h1>
  <div class="card">
    <h2>Coverage</h2>
    <pre>{json.dumps(coverage, indent=2)}</pre>
  </div>
  <div class="card">
    <h2>Legality</h2>
    <pre>{json.dumps(legality, indent=2)}</pre>
  </div>
  <div class="card">
    <h2>Baseline</h2>
    <pre>{json.dumps(baseline, indent=2)}</pre>
  </div>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def run_quality_gates(
    coverage_limit_cards: int | None = 250,
    legality_limit_cards: int | None = 300,
    marks: tuple[str, ...] = ("H", "I", "J"),
    baseline_path: str | Path = DEFAULT_BASELINE_PATH,
    golden_suite_path: str | Path | None = DEFAULT_GOLDEN_SUITE_PATH,
    fidelity_manifest_path: str | Path = "artifacts/fidelity/hook_manifest_latest.json",
    real_game_fixture_path: str | Path = "tests/fixtures/real_games",
    min_replay_checks: int = 3,
    max_script_hook_share_percent: float = 20.0,
    update_baseline: bool = False,
    force_refresh: bool = False,
) -> dict[str, Any]:
    baseline_file = Path(baseline_path)
    coverage = run_standard_coverage_analysis(
        marks=marks,
        limit_cards=coverage_limit_cards,
        include_examples=False,
        force_refresh=force_refresh,
    )
    legality = build_standard_legality_snapshot(
        marks=marks,
        limit_cards=legality_limit_cards,
    )

    replay_results = [verify_seed_replay(turn_limit=8, seed=seed) for seed in (101, 202, 303)[:min_replay_checks]]
    replay_pass = all(result["deterministic"] for result in replay_results)
    fidelity_report = run_strict_fidelity_audit(
        marks=marks,
        limit_cards=coverage_limit_cards,
        manifest_path=str(fidelity_manifest_path),
    )
    fidelity_pass = float(
        fidelity_report.get("script_hook_registration", {}).get("percent", 0.0)
    ) >= 100.0
    script_hook_share = float(
        fidelity_report.get("operation_mix", {}).get("script_hook_share_percent", 100.0)
    )
    script_hook_share_pass = script_hook_share <= max_script_hook_share_percent

    golden_report: dict[str, Any] | None = None
    golden_pass = True
    if golden_suite_path is not None:
        suite_path = Path(golden_suite_path)
        if suite_path.exists():
            suite_result = run_golden_suite(str(suite_path))
            golden_report = {
                "path": str(suite_path),
                "count": int(suite_result.get("count", 0)),
                "executed": True,
            }
            golden_pass = int(suite_result.get("count", 0)) > 0
        else:
            golden_report = {"path": str(suite_path), "count": 0, "executed": False}

    real_game_report = run_real_game_fixture_suite(real_game_fixture_path)
    real_game_pass = bool(real_game_report.get("passed", False))

    state = create_demo_state()
    run_setup_phase(state, seed=777)
    conservation_report = zone_conservation_report(state)
    conservation_pass = bool(conservation_report.get("all_passed", False))

    baseline = _load_json(baseline_file)
    current_resolution = float(coverage.get("summary", {}).get("text_resolution_percent", 0))
    baseline_resolution = (
        float(baseline.get("summary", {}).get("text_resolution_percent", 0)) if baseline else None
    )
    regression = (
        baseline_resolution is not None and current_resolution + 0.001 < baseline_resolution
    )

    if baseline is None or update_baseline:
        _save_json(
            baseline_file,
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "summary": coverage.get("summary", {}),
                "card_summary": coverage.get("card_summary", {}),
                "metadata": coverage.get("metadata", {}),
            },
        )

    quality_pass = bool(
        replay_pass
        and golden_pass
        and fidelity_pass
        and script_hook_share_pass
        and real_game_pass
        and conservation_pass
        and not regression
    )
    payload = {
        "quality_pass": quality_pass,
        "coverage": coverage.get("summary", {}),
        "legality": legality.get("summary", {}),
        "replay_checks": replay_results,
        "strict_fidelity": fidelity_report,
        "fidelity_thresholds": {
            "max_script_hook_share_percent": max_script_hook_share_percent,
            "actual_script_hook_share_percent": script_hook_share,
            "script_hook_share_pass": script_hook_share_pass,
        },
        "golden_regression": golden_report,
        "real_game_fidelity": real_game_report,
        "zone_conservation": {
            "passed": conservation_pass,
            "report": conservation_report,
        },
        "baseline": {
            "path": str(baseline_file),
            "exists": baseline is not None,
            "updated": baseline is None or update_baseline,
            "baseline_resolution_percent": baseline_resolution,
            "current_resolution_percent": current_resolution,
            "regression_detected": regression,
        },
    }
    _save_dashboard(DEFAULT_DASHBOARD_PATH, payload)
    payload["artifacts"] = {
        "coverage_dashboard_html": str(DEFAULT_DASHBOARD_PATH),
    }
    return payload

