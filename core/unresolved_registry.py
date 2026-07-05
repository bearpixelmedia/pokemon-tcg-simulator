from __future__ import annotations

import threading
from collections import Counter, deque
from datetime import UTC, datetime
from typing import Any

_COUNTER: Counter[str] = Counter()
_RECENT: deque[dict[str, Any]] = deque(maxlen=500)
_LOCK = threading.Lock()


def register_unresolved_clause(clause: str, source_text: str | None = None) -> None:
    normalized = clause.strip()
    if not normalized:
        return

    with _LOCK:
        _COUNTER[normalized] += 1
        _RECENT.appendleft(
            {
                "clause": normalized,
                "source_text": source_text,
                "registered_at": datetime.now(UTC).isoformat(),
            }
        )


def snapshot_unresolved_registry(limit: int = 100) -> dict[str, Any]:
    with _LOCK:
        return {
            "total_unique_clauses": len(_COUNTER),
            "top_clauses": _COUNTER.most_common(limit),
            "recent_examples": list(_RECENT)[:limit],
        }


def clear_unresolved_registry() -> None:
    with _LOCK:
        _COUNTER.clear()
        _RECENT.clear()

