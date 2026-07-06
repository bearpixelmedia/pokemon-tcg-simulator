from __future__ import annotations

from datetime import UTC, datetime
from collections import Counter
from typing import Any

from core.hook_manifest import is_registered_hook, load_hook_manifest
from core.standard_coverage import (
    STANDARD_MARKS,
    extract_text_blocks,
    fetch_card_detail,
    fetch_cards_by_regulation_mark,
)
from core.text_compiler import compile_effect_text


def run_strict_fidelity_audit(
    marks: tuple[str, ...] = STANDARD_MARKS,
    limit_cards: int | None = None,
    manifest_path: str = "artifacts/fidelity/hook_manifest_latest.json",
) -> dict[str, Any]:
    manifest = load_hook_manifest(manifest_path)
    cards = fetch_cards_by_regulation_mark(marks=marks)
    selected = cards[:limit_cards] if limit_cards and limit_cards > 0 else cards

    total_hooks = 0
    registered_hooks = 0
    total_operations = 0
    missing_examples: list[dict[str, str]] = []
    hook_id_counts: Counter[str] = Counter()

    for card in selected:
        detail = fetch_card_detail(card["id"])
        for block in extract_text_blocks(detail):
            program = compile_effect_text(block["text"])
            for op in program.operations:
                total_operations += 1
                if op.op != "script_hook":
                    continue
                total_hooks += 1
                hook_id = str(op.params.get("hook_id", "unknown"))
                hook_id_counts[hook_id] += 1
                clause = str(op.params.get("clause", "")).strip()
                if is_registered_hook(hook_id, clause, manifest):
                    registered_hooks += 1
                elif len(missing_examples) < 20:
                    missing_examples.append(
                        {
                            "card_id": card["id"],
                            "card_name": card.get("name", ""),
                            "hook_id": hook_id,
                            "clause": clause,
                        }
                    )

    percent = (registered_hooks / total_hooks * 100) if total_hooks else 100.0
    script_hook_share = (total_hooks / total_operations * 100) if total_operations else 0.0
    top_hook_families = [
        {"hook_id": hook_id, "count": count}
        for hook_id, count in hook_id_counts.most_common(25)
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "marks": list(marks),
        "cards_scanned": len(selected),
        "manifest_path": manifest_path,
        "operation_mix": {
            "total_operations": total_operations,
            "script_hook_operations": total_hooks,
            "script_hook_share_percent": round(script_hook_share, 2),
            "top_script_hook_families": top_hook_families,
        },
        "script_hook_registration": {
            "registered": registered_hooks,
            "total": total_hooks,
            "percent": round(percent, 2),
            "missing_examples": missing_examples,
        },
    }
