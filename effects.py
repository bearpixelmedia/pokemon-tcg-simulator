"""Backward-compatible exports for legacy imports."""


def apply_status_effects(active: dict | None) -> None:
    """
    Legacy helper kept for compatibility with the original prototype shape.

    The modern engine lives in `core.effects.apply_pokemon_checkup`, but some
    callers still pass a single `active` dict with `hp` and `status`.
    """
    if not active:
        return

    statuses = {status.lower() for status in active.get("status", [])}
    if "poisoned" in statuses:
        active["hp"] = max(0, int(active.get("hp", 0)) - 10)
    if "burned" in statuses:
        active["hp"] = max(0, int(active.get("hp", 0)) - 20)


__all__ = ["apply_status_effects"]