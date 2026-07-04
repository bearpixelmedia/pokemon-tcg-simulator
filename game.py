import random
from core.effects import apply_status_effects, can_attack

def run_simulation():
    turns = 0
    p1_hp, p2_hp = 60, 60
    while p1_hp > 0 and p2_hp > 0 and turns < 30:
        turns += 1
        if can_attack({"status": []}):
            p2_hp -= random.randint(20, 45)
        if random.random() > 0.6:
            apply_status_effects({"hp": p1_hp, "status": ["poisoned"]})
    return {
        "winner": "You" if p2_hp <= 0 else "AI",
        "turns": turns,
        "final_hp": {"you": max(0, p1_hp), "ai": max(0, p2_hp)}
    }