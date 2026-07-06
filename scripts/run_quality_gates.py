from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.quality_gates import run_quality_gates


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Pokémon TCG simulator quality gates.")
    parser.add_argument("--coverage-limit-cards", type=int, default=150)
    parser.add_argument("--legality-limit-cards", type=int, default=150)
    parser.add_argument("--marks", nargs="+", default=["H", "I", "J"])
    parser.add_argument("--baseline-path", default="artifacts/quality/coverage_baseline.json")
    parser.add_argument("--real-game-fixture-path", default="tests/fixtures/real_games")
    parser.add_argument("--max-script-hook-share-percent", type=float, default=20.0)
    parser.add_argument("--output-path", default="artifacts/quality/quality_report.json")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_quality_gates(
        coverage_limit_cards=args.coverage_limit_cards,
        legality_limit_cards=args.legality_limit_cards,
        marks=tuple(mark.upper() for mark in args.marks),
        baseline_path=args.baseline_path,
        real_game_fixture_path=args.real_game_fixture_path,
        max_script_hook_share_percent=args.max_script_hook_share_percent,
        update_baseline=args.update_baseline,
        force_refresh=args.force_refresh,
    )

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("quality_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())

