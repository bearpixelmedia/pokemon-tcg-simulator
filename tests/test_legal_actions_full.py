import unittest

from core.effects import create_demo_state
from core.legal_actions_full import generate_legal_actions_full
from core.official_rules import run_official_setup, set_turn_context


class LegalActionsFullTests(unittest.TestCase):
    def test_generate_legal_actions_full_returns_reasoned_actions(self) -> None:
        state = create_demo_state()
        actions = generate_legal_actions_full(state, "p1")
        self.assertTrue(any(action["action_type"] == "attack" for action in actions))
        self.assertTrue(all("reason" in action for action in actions))
        self.assertTrue(all("illegal_reasons" in action for action in actions))

    def test_first_turn_opening_player_attack_is_illegal(self) -> None:
        state = create_demo_state()
        run_official_setup(state, seed=5, opening_player="p1")
        set_turn_context(state, actor="p1", turn=1)
        actions = generate_legal_actions_full(state, "p1")
        attack = next(action for action in actions if action["action_type"] == "attack")
        self.assertFalse(attack["legal"])

    def test_attack_cost_reports_structured_reason_when_insufficient_energy(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["active"]["attacks"] = [{"name": "Heavy Blaze", "cost": ["R", "R", "C"], "damage": 140}]
        state["players"]["p1"]["active"]["energy_attached"] = 1
        state["players"]["p1"]["active"]["attached_energy_cards"] = [{"id": "p1-energy-1", "energy_type": "R"}]
        actions = generate_legal_actions_full(state, "p1")
        attack = next(action for action in actions if action["action_type"] == "attack")
        self.assertFalse(attack["legal"])
        self.assertTrue(any(reason["code"] == "insufficient_energy" for reason in attack["illegal_reasons"]))

    def test_retreat_illegal_reason_includes_status_block(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["active"]["status"] = ["Asleep"]
        actions = generate_legal_actions_full(state, "p1")
        retreat = next(action for action in actions if action["action_type"] == "retreat")
        self.assertFalse(retreat["legal"])
        self.assertTrue(any(reason["code"] == "status_blocks_retreat" for reason in retreat["illegal_reasons"]))

    def test_supporter_blocked_after_once_per_turn_flag(self) -> None:
        state = create_demo_state()
        state["official_rules"] = {"opening_player": "p1", "turn": 2, "active_player": "p1"}
        state["players"]["p1"]["turn_flags"] = {"supporter_played": True}
        actions = generate_legal_actions_full(state, "p1")
        supporter = next(action for action in actions if action["action_type"] == "play_supporter")
        self.assertFalse(supporter["legal"])
        self.assertTrue(any(reason["code"] in {"official_rule", "supporter_lifecycle"} for reason in supporter["illegal_reasons"]))

    def test_bench_action_requires_basic_in_hand(self) -> None:
        state = create_demo_state()
        state["players"]["p1"]["hand_cards"] = [{"id": "x1", "name": "Trainer 1", "supertype": "trainer"}]
        state["players"]["p1"]["hand_basics"] = 0
        actions = generate_legal_actions_full(state, "p1")
        bench = next(action for action in actions if action["action_type"] == "bench_pokemon")
        self.assertFalse(bench["legal"])
        self.assertTrue(any(reason["code"] == "no_basic_in_hand" for reason in bench["illegal_reasons"]))


if __name__ == "__main__":
    unittest.main()
