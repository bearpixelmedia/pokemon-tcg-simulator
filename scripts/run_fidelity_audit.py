from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.fidelity_audit import run_strict_fidelity_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict fidelity registration audit.")
    parser.add_argument("--marks", nargs="+", default=["H", "I", "J"], help="Regulation marks to scan.")
    parser.add_argument("--limit-cards", type=int, default=0, help="Optional card scan limit (0 means all).")
    parser.add_argument(
        "--manifest-path",
        default="artifacts/fidelity/hook_manifest_latest.json",
        help="Manifest path to validate against.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/fidelity/fidelity_audit_latest.json",
        help="Output report path.",
    )
    args = parser.parse_args()

    limit_cards = args.limit_cards if args.limit_cards > 0 else None
    report = run_strict_fidelity_audit(
        marks=tuple(args.marks),
        limit_cards=limit_cards,
        manifest_path=args.manifest_path,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
