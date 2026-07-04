def apply_status_effects(active):
    if not active: return
    if "poisoned" in active.get("status", []):
        active["hp"] = max(0, active.get("hp", 0) - 10)

def can_attack(active):
    status = active.get("status", [])
    return "paralyzed" not in status and "asleep" not in status