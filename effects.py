def apply_status_effects(active):
    if active and "poisoned" in active.get("status", []):
        active["hp"] = max(0, active.get("hp", 0) - 10)