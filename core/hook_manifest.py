from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.standard_coverage import (
    STANDARD_MARKS,
    extract_text_blocks,
    fetch_card_detail,
    fetch_cards_by_regulation_mark,
)
from core.text_compiler import compile_effect_text

DEFAULT_HOOK_MANIFEST_PATH = Path("artifacts/fidelity/hook_manifest_latest.json")


def hook_signature(hook_id: str, clause: str) -> str:
    raw = f"{hook_id}|{clause.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_hook_manifest(
    marks: tuple[str, ...] = STANDARD_MARKS,
    limit_cards: int | None = None,
) -> dict[str, Any]:
    cards = fetch_cards_by_regulation_mark(marks=marks)
    selected = cards[:limit_cards] if limit_cards and limit_cards > 0 else cards

    entries: dict[str, dict[str, str]] = {}
    for card in selected:
        detail = fetch_card_detail(card["id"])
        blocks = extract_text_blocks(detail)
        for block in blocks:
            program = compile_effect_text(block["text"])
            for operation in program.operations:
                if operation.op != "script_hook":
                    continue
                hook_id = str(operation.params.get("hook_id", "unknown"))
                clause = str(operation.params.get("clause", "")).strip()
                signature = hook_signature(hook_id, clause)
                if signature not in entries:
                    entries[signature] = {
                        "signature": signature,
                        "hook_id": hook_id,
                        "clause": clause,
                    }

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "marks": list(marks),
        "cards_scanned": len(selected),
        "entries": sorted(entries.values(), key=lambda item: (item["hook_id"], item["clause"])),
        "entry_count": len(entries),
    }
    return payload


def write_hook_manifest(
    payload: dict[str, Any],
    path: str | Path = DEFAULT_HOOK_MANIFEST_PATH,
) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(destination)


def load_hook_manifest(path: str | Path = DEFAULT_HOOK_MANIFEST_PATH) -> dict[str, Any] | None:
    source = Path(path)
    if not source.exists():
        return None
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_registered_hook(
    hook_id: str,
    clause: str,
    manifest: dict[str, Any] | None,
) -> bool:
    if not manifest:
        return False
    signature = hook_signature(hook_id, clause)
    entries = manifest.get("entries", [])
    return any(entry.get("signature") == signature for entry in entries)
