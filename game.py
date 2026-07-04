import random

def run_simulation():
    turns = 0
    p1_hp = 60
    p2_hp = 60
    
    while p1_hp > 0 and p2_hp > 0 and turns < 30:
        turns += 1
        # Player attacks
        p2_hp -= random.randint(20, 45)
        # Status effect simulation
        if random.random() > 0.6:
            p1_hp -= 10  # Poison damage
    
    winner = "You" if p2_hp <= 0 else "AI"
    return {
        "winner": winner,
        "turns": turns,
        "final_hp": {
            "you": max(0, p1_hp),
            "ai": max(0, p2_hp)
        }
    }