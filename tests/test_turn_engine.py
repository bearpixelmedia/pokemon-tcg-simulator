import random
import unittest

from core.effect_types import EffectOperation, EffectProgram
from core.effects import apply_effect_program, create_demo_state
from core.turn_engine import TurnPhase, run_turn_based_simulation, verify_seed_replay


class TurnEngineTests(unittest.TestCase):
    def test_same_seed_produces_same_checksums(self) -> None:
        first = run_turn_based_simulation(turn_limit=6, seed=1337)
        second = run_turn_based_simulation(turn_limit=6, seed=1337)

        self.assertEqual(first["replay"]["state_checksum"], second["replay"]["state_checksum"])
        self.assertEqual(first["replay"]["event_log_checksum"], second["replay"]["event_log_checksum"])
        self.assertEqual(first["final_hp"], second["final_hp"])

    def test_phase_order_exists_on_each_turn(self) -> None:
        result = run_turn_based_simulation(turn_limit=2, seed=11)
        expected_order = [
            TurnPhase.TURN_START.value,
            TurnPhase.ACTION_SELECTION.value,
            TurnPhase.BEFORE_ATTACK.value,
            TurnPhase.ATTACK_RESOLUTION.value,
            TurnPhase.BETWEEN_TURNS_CHECKUP.value,
            TurnPhase.TURN_END.value,
        ]

        self.assertGreaterEqual(len(result["event_log"]), 1)
        first_turn_phases = [entry["phase"] for entry in result["event_log"][0]["phases"]]
        self.assertEqual(first_turn_phases, expected_order)

    def test_verify_seed_replay_reports_deterministic(self) -> None:
        report = verify_seed_replay(turn_limit=4, seed=27)
        self.assertTrue(report["deterministic"])

    def test_simulation_includes_setup_and_runtime_checksum(self) -> None:
        result = run_turn_based_simulation(turn_limit=2, seed=19)
        self.assertIn("setup_events", result)
        self.assertIn("runtime_state_checksum", result["replay"])

    def test_opening_player_turn_one_cannot_attack(self) -> None:
        result = run_turn_based_simulation(
            turn_limit=1,
            seed=41,
            scripted_actions=[{"action_type": "attack", "blueprint_key": "volatile_strike"}],
        )
        first_action = result["replay"]["turn_actions"][0]
        self.assertEqual(first_action["action_type"], "pass")
        self.assertIn("forced pass", result["event_log"][0]["phases"][1]["events"][0])

    def test_rotating_statuses_do_not_stack(self) -> None:
        state = create_demo_state()
        program = EffectProgram(
            source_text="status chain",
            operations=[
                EffectOperation(op="apply_status", params={"target": "self_active", "status": "Asleep"}),
                EffectOperation(op="apply_status", params={"target": "self_active", "status": "Confused"}),
                EffectOperation(op="apply_status", params={"target": "self_active", "status": "Paralyzed"}),
            ],
        )
        apply_effect_program(program, state, actor="p1", rng=random.Random(1))
        statuses = state["players"]["p1"]["active"]["status"]

        self.assertEqual(statuses, ["Paralyzed"])
        self.assertEqual(state["players"]["p1"]["active"].get("paralyzed_turns_remaining"), 1)


if __name__ == "__main__":
    unittest.main()

