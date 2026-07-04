from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.data_pipeline import run_pipeline_health_check


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ingest/pipeline health checks.")
    parser.add_argument("--limit-cards", type=int, default=200)
    parser.add_argument("--marks", nargs="+", default=["H", "I", "J"])
    parser.add_argument("--output-path", default="artifacts/pipeline/health_latest.json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_pipeline_health_check(
        marks=tuple(mark.upper() for mark in args.marks),
        limit_cards=args.limit_cards,
        write_snapshot=False,
    )
    output = Path(args.output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    reliability = float(report["source_reliability"]["reliability_percent"])
    return 0 if reliability >= 95 else 1


if __name__ == "__main__":
    raise SystemExit(main())

