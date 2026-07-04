from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.standard_coverage import fetch_card_detail, fetch_cards_by_regulation_mark


def _parse_as_of(value: str | None) -> date:
    if not value:
        return datetime.now(UTC).date()
    return date.fromisoformat(value)


def _is_release_gate_satisfied(release_date: str | None, as_of: date, waiting_days: int) -> bool:
    if not release_date:
        return True
    release = date.fromisoformat(release_date)
    return release <= as_of - timedelta(days=waiting_days)


def build_standard_legality_snapshot(
    as_of_date: str | None = None,
    marks: tuple[str, ...] = ("H", "I", "J"),
    waiting_days: int = 14,
    limit_cards: int | None = 500,
    max_workers: int = 24,
) -> dict[str, Any]:
    as_of = _parse_as_of(as_of_date)
    indexed_cards = fetch_cards_by_regulation_mark(marks=marks)
    cards_to_scan = indexed_cards[:limit_cards] if limit_cards and limit_cards > 0 else indexed_cards

    details: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_card_detail, card["id"]): card for card in cards_to_scan}
        for future in as_completed(futures):
            indexed = futures[future]
            detail = future.result()
            detail["_indexed_regulation_mark"] = indexed.get("regulationMark")
            details.append(detail)

    details.sort(key=lambda card: card["id"])

    legal_cards = 0
    blocked_by_release = 0
    blocked_examples: list[dict[str, Any]] = []
    scanned_cards: list[dict[str, Any]] = []

    for detail in details:
        regulation_mark = detail.get("regulationMark") or detail.get("_indexed_regulation_mark")
        set_info = detail.get("set", {}) or {}
        release_date = set_info.get("releaseDate")
        release_ok = _is_release_gate_satisfied(release_date, as_of, waiting_days)
        is_legal = bool(regulation_mark in marks and release_ok)
        if is_legal:
            legal_cards += 1
        else:
            blocked_by_release += 1
            if len(blocked_examples) < 40:
                blocked_examples.append(
                    {
                        "id": detail["id"],
                        "name": detail.get("name"),
                        "regulation_mark": regulation_mark,
                        "release_date": release_date,
                    }
                )

        scanned_cards.append(
            {
                "id": detail["id"],
                "name": detail.get("name"),
                "regulation_mark": regulation_mark,
                "set_id": set_info.get("id"),
                "set_name": set_info.get("name"),
                "release_date": release_date,
                "release_gate_satisfied": release_ok,
                "is_legal": is_legal,
            }
        )

    return {
        "metadata": {
            "as_of_date": as_of.isoformat(),
            "marks": list(marks),
            "waiting_days": waiting_days,
            "cards_available": len(indexed_cards),
            "cards_scanned": len(scanned_cards),
        },
        "summary": {
            "legal_cards": legal_cards,
            "blocked_by_release_gate_or_other": blocked_by_release,
            "legal_percent": round((legal_cards / len(scanned_cards) * 100) if scanned_cards else 0, 2),
        },
        "blocked_examples": blocked_examples,
        "cards": scanned_cards,
    }

