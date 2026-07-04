from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from core.text_compiler import compile_effect_text, supported_templates

API_BASE_URL = "https://api.tcgdex.net/v2/en"
STANDARD_MARKS = ("H", "I", "J")
_CACHE_TTL_SECONDS = 300
_coverage_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _fetch_json(url: str, retries: int = 3, timeout: int = 45) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return json.load(response)
        except Exception as error:  # pragma: no cover - network branch
            last_error = error
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    if last_error is None:
        raise RuntimeError("Failed to fetch JSON without a concrete error.")
    raise last_error


def fetch_cards_by_regulation_mark(
    marks: tuple[str, ...] = STANDARD_MARKS,
    page_size: int = 500,
) -> list[dict[str, str]]:
    cards: dict[str, dict[str, str]] = {}
    for mark in marks:
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {
                    "regulationMark": f"eq:{mark}",
                    "pagination:itemsPerPage": str(page_size),
                    "pagination:page": str(page),
                }
            )
            url = f"{API_BASE_URL}/cards?{query}"
            payload = _fetch_json(url)
            if not payload:
                break
            for card in payload:
                cards[card["id"]] = {
                    "id": card["id"],
                    "name": card.get("name", ""),
                    "localId": card.get("localId", ""),
                    "regulationMark": mark,
                }
            page += 1
    return sorted(cards.values(), key=lambda item: item["id"])


def fetch_card_detail(card_id: str) -> dict[str, Any]:
    return _fetch_json(f"{API_BASE_URL}/cards/{card_id}")


def _damage_value_to_text(damage: Any) -> str | None:
    if isinstance(damage, int):
        return f"{damage} damage."
    if isinstance(damage, str):
        normalized = damage.strip()
        if re.fullmatch(r"\d+", normalized):
            return f"{normalized} damage."
    return None


def extract_text_blocks(card: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    trainer_effect = (card.get("effect") or "").strip()
    if trainer_effect:
        blocks.append(
            {
                "source_type": "trainer_effect",
                "source_name": card.get("trainerType", "Trainer"),
                "text": trainer_effect,
            }
        )

    for index, ability in enumerate(card.get("abilities", []) or [], start=1):
        effect = (ability.get("effect") or "").strip()
        if effect:
            blocks.append(
                {
                    "source_type": "ability_effect",
                    "source_name": ability.get("name", f"Ability {index}"),
                    "text": effect,
                }
            )

    for index, attack in enumerate(card.get("attacks", []) or [], start=1):
        effect = (attack.get("effect") or "").strip()
        if effect:
            blocks.append(
                {
                    "source_type": "attack_effect",
                    "source_name": attack.get("name", f"Attack {index}"),
                    "text": effect,
                }
            )
            continue

        fallback_text = _damage_value_to_text(attack.get("damage"))
        if fallback_text:
            blocks.append(
                {
                    "source_type": "attack_damage_only",
                    "source_name": attack.get("name", f"Attack {index}"),
                    "text": fallback_text,
                }
            )

    return blocks


def analyze_text_blocks(
    card_id: str,
    card_name: str,
    regulation_mark: str,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    analyzed: list[dict[str, Any]] = []
    for block in blocks:
        program = compile_effect_text(block["text"])
        analyzed.append(
            {
                "card_id": card_id,
                "card_name": card_name,
                "regulation_mark": regulation_mark,
                "source_type": block["source_type"],
                "source_name": block["source_name"],
                "text": block["text"],
                "template_name": program.template_name,
                "is_resolved": program.is_fully_resolved,
                "unresolved_text": program.unresolved_text,
                "operations": [op.to_dict() for op in program.operations],
            }
        )
    return analyzed


def _get_cache(key: tuple[Any, ...]) -> dict[str, Any] | None:
    with _cache_lock:
        entry = _coverage_cache.get(key)
        if not entry:
            return None
        age = time.time() - entry["timestamp"]
        if age > _CACHE_TTL_SECONDS:
            _coverage_cache.pop(key, None)
            return None
        cached = dict(entry["data"])
        metadata = dict(cached.get("metadata", {}))
        metadata["cached"] = True
        metadata["cache_age_seconds"] = round(age, 2)
        cached["metadata"] = metadata
        return cached


def _set_cache(key: tuple[Any, ...], value: dict[str, Any]) -> None:
    with _cache_lock:
        _coverage_cache[key] = {"timestamp": time.time(), "data": value}


def run_standard_coverage_analysis(
    marks: tuple[str, ...] = STANDARD_MARKS,
    limit_cards: int | None = 250,
    include_examples: bool = True,
    max_workers: int = 20,
    force_refresh: bool = False,
) -> dict[str, Any]:
    cache_key = (marks, limit_cards, include_examples)
    if not force_refresh:
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

    started_at = time.time()
    index_cards = fetch_cards_by_regulation_mark(marks=marks)
    cards_to_process = index_cards[:limit_cards] if limit_cards and limit_cards > 0 else index_cards

    details: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_card_detail, card["id"]): card for card in cards_to_process
        }
        for future in as_completed(futures):
            index_card = futures[future]
            detail = future.result()
            detail["_index_regulation_mark"] = index_card.get("regulationMark")
            details.append(detail)

    details.sort(key=lambda card: card["id"])

    source_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"resolved": 0, "total": 0})
    template_usage = Counter()
    unresolved_counter = Counter()
    unresolved_examples: list[dict[str, Any]] = []
    analyzed_cards = 0
    cards_with_text = 0
    fully_resolved_cards = 0
    total_blocks = 0
    resolved_blocks = 0

    for card in details:
        blocks = extract_text_blocks(card)
        analyzed_cards += 1
        if not blocks:
            continue

        cards_with_text += 1
        mark = card.get("regulationMark") or card.get("_index_regulation_mark") or "Unknown"
        analyzed_blocks = analyze_text_blocks(card["id"], card.get("name", ""), mark, blocks)
        card_fully_resolved = True
        for block in analyzed_blocks:
            total_blocks += 1
            summary = source_summary[block["source_type"]]
            summary["total"] += 1

            if block["is_resolved"]:
                resolved_blocks += 1
                summary["resolved"] += 1
                if block["template_name"]:
                    for template_name in block["template_name"].split(" + "):
                        template_usage[template_name] += 1
            else:
                card_fully_resolved = False
                unresolved_counter[block["unresolved_text"] or block["text"]] += 1
                if include_examples and len(unresolved_examples) < 40:
                    unresolved_examples.append(
                        {
                            "card_id": block["card_id"],
                            "card_name": block["card_name"],
                            "regulation_mark": block["regulation_mark"],
                            "source_type": block["source_type"],
                            "source_name": block["source_name"],
                            "text": block["text"],
                            "unresolved_text": block["unresolved_text"],
                        }
                    )

        if card_fully_resolved:
            fully_resolved_cards += 1

    coverage_pct = (resolved_blocks / total_blocks * 100) if total_blocks else 0.0
    elapsed = round(time.time() - started_at, 2)
    result = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "elapsed_seconds": elapsed,
            "cached": False,
            "marks": list(marks),
            "cards_available": len(index_cards),
            "cards_scanned": len(cards_to_process),
            "cards_analyzed": analyzed_cards,
            "templates_supported": len(supported_templates()),
        },
        "summary": {
            "total_text_blocks": total_blocks,
            "resolved_text_blocks": resolved_blocks,
            "unresolved_text_blocks": total_blocks - resolved_blocks,
            "text_resolution_percent": round(coverage_pct, 2),
        },
        "card_summary": {
            "cards_with_text_blocks": cards_with_text,
            "fully_resolved_cards": fully_resolved_cards,
            "partially_or_unresolved_cards": max(cards_with_text - fully_resolved_cards, 0),
        },
        "source_breakdown": dict(source_summary),
        "template_usage_top": template_usage.most_common(30),
        "top_unresolved_clauses": unresolved_counter.most_common(30),
        "unresolved_examples": unresolved_examples if include_examples else [],
    }

    _set_cache(cache_key, result)
    return result

