from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.hook_manifest import build_hook_manifest, write_hook_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build script-hook manifest for strict fidelity mode.")
    parser.add_argument("--marks", nargs="+", default=["H", "I", "J"], help="Regulation marks to scan.")
    parser.add_argument("--limit-cards", type=int, default=0, help="Optional card limit (0 means all).")
    parser.add_argument(
        "--output",
        default="artifacts/fidelity/hook_manifest_latest.json",
        help="Output manifest path.",
    )
    args = parser.parse_args()

    limit_cards = args.limit_cards if args.limit_cards > 0 else None
    payload = build_hook_manifest(marks=tuple(args.marks), limit_cards=limit_cards)
    destination = write_hook_manifest(payload, path=args.output)
    print(json.dumps({"path": destination, "entry_count": payload.get("entry_count", 0)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
