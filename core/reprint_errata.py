from __future__ import annotations

from typing import Any

# Representative examples; extend as legality/rulings dataset grows.
REPRINT_MAP: dict[str, dict[str, Any]] = {
    "Rare Candy": {"reprint_regulation_mark": "I", "reprint_source": "MEG"},
    "Boss's Orders": {"reprint_regulation_mark": "I", "reprint_source": "MEG"},
    "Pokémon Catcher": {"reprint_regulation_mark": "J", "reprint_source": "SVI"},
}

ERRATA_MAP: dict[str, dict[str, str]] = {
    "Rare Candy": {
        "errata_note": "Older prints use updated current wording during tournament play.",
        "reference": "Play! Pokémon Tournament Rules Handbook reprint/errata guidance",
    },
    "Pokémon Catcher": {
        "errata_note": "Coin-flip errata applies to legacy printings.",
        "reference": "Standard legality list errata notes",
    },
}


def enrich_legality_record(record: dict[str, Any]) -> dict[str, Any]:
    name = (record.get("name") or "").strip()
    reprint = REPRINT_MAP.get(name)
    errata = ERRATA_MAP.get(name)
    enriched = dict(record)
    enriched["reprint_metadata"] = reprint
    enriched["errata_metadata"] = errata
    enriched["has_reprint_override"] = bool(reprint)
    enriched["has_errata"] = bool(errata)
    if reprint and not enriched.get("is_legal"):
        # Reprint override: if same-name trainer has legal modern printing, mark legacy print as legal proxy.
        enriched["is_legal_via_reprint"] = True
    else:
        enriched["is_legal_via_reprint"] = False
    return enriched

