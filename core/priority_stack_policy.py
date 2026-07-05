from __future__ import annotations

from typing import Any

DEFAULT_KIND_PRECEDENCE: dict[str, int] = {
    "replacement": 0,
    "prevention": 1,
    "normal": 2,
}


def normalize_kind(value: str | None, fallback: str = "normal") -> str:
    raw = (value or "").strip().lower()
    if raw in DEFAULT_KIND_PRECEDENCE:
        return raw
    return fallback


def infer_stack_kind(params: dict[str, Any]) -> str:
    explicit = normalize_kind(str(params.get("kind", "")), fallback="")
    if explicit:
        return explicit

    source = " ".join(str(params.get(key, "")) for key in ("rule", "clause", "hook_id")).lower()
    if "prevent" in source or "immune" in source:
        return "prevention"
    if "replace" in source or "instead" in source:
        return "replacement"
    return "normal"


def stack_order_key(rule: dict[str, Any], index: int = 0) -> tuple[int, int, int]:
    kind = normalize_kind(str(rule.get("kind", "normal")))
    return (DEFAULT_KIND_PRECEDENCE.get(kind, 99), -int(rule.get("priority", 100)), index)


def target_owner_from_selector(actor: str, selector: str, opponent_actor: str) -> str:
    if selector.startswith("self_"):
        return actor
    if selector.startswith("opponent_"):
        return opponent_actor
    return actor


def _rule_scope_applies(owner: str, target_scope: str, observed_target_owner: str) -> bool:
    if owner not in {"p1", "p2"}:
        return True
    if target_scope in {"any", "any_pokemon", "both_active"}:
        return True
    if target_scope in {"self_player", "self_active", "self_pokemon"}:
        return observed_target_owner == owner
    if target_scope in {"opponent_player", "opponent_active", "opponent_pokemon"}:
        return observed_target_owner != owner
    return True


def rule_applies_to_damage_target(
    rule: dict[str, Any],
    attacker: str,
    target_selector: str,
    opponent_actor: str,
) -> bool:
    target_owner = target_owner_from_selector(attacker, target_selector, opponent_actor)
    return _rule_scope_applies(
        owner=str(rule.get("owner", "")),
        target_scope=str(rule.get("target", "any")),
        observed_target_owner=target_owner,
    )


def resolve_damage_with_priority_stack(
    base_amount: int,
    rules: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    resolved = max(0, int(base_amount))
    traces: list[str] = []
    ordered = sorted(enumerate(rules), key=lambda item: stack_order_key(item[1], item[0]))

    for _, rule in ordered:
        kind = normalize_kind(str(rule.get("kind", "normal")))
        source = str(rule.get("source", "rule"))
        if kind == "replacement":
            if "set_amount" in rule:
                resolved = max(0, int(rule["set_amount"]))
                traces.append(f"Replacement rule '{source}' set damage to {resolved}.")
            if "amount_delta" in rule:
                resolved = max(0, resolved + int(rule["amount_delta"]))
                traces.append(f"Replacement rule '{source}' adjusted damage to {resolved}.")
            if "multiplier" in rule:
                resolved = max(0, int(round(resolved * float(rule["multiplier"]))))
                traces.append(f"Replacement rule '{source}' multiplied damage to {resolved}.")
        elif kind == "prevention":
            if bool(rule.get("prevent_all", False)):
                traces.append(f"Prevention rule '{source}' prevented all damage.")
                return 0, traces
            prevent_amount = int(rule.get("prevent_amount", 0))
            if prevent_amount > 0:
                resolved = max(0, resolved - prevent_amount)
                traces.append(f"Prevention rule '{source}' reduced damage by {prevent_amount} to {resolved}.")

    return resolved, traces


def operations_from_timing_rules(
    timing_rules: list[dict[str, Any]],
    actor: str,
    opponent_actor: str,
    window: str,
) -> list[dict[str, Any]]:
    applicable: list[tuple[int, int, int, dict[str, Any]]] = []
    for index, rule in enumerate(timing_rules):
        if str(rule.get("window", "")) != window:
            continue
        if int(rule.get("turns_remaining", 1)) <= 0:
            continue

        owner = str(rule.get("owner", ""))
        target_scope = str(rule.get("target", "self_player"))
        observed_target_owner = actor
        if target_scope.startswith("opponent_"):
            observed_target_owner = opponent_actor
        if not _rule_scope_applies(owner, target_scope, observed_target_owner):
            continue

        operation = rule.get("operation", {})
        if not isinstance(operation, dict):
            continue
        kind = normalize_kind(str(rule.get("kind", "normal")))
        applicable.append((DEFAULT_KIND_PRECEDENCE.get(kind, 99), -int(rule.get("priority", 100)), index, operation))

    applicable.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in applicable]
