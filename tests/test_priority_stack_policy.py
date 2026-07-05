import unittest

from core.priority_stack_policy import (
    infer_stack_kind,
    operations_from_timing_rules,
    resolve_damage_with_priority_stack,
    rule_applies_to_damage_target,
)


class PriorityStackPolicyTests(unittest.TestCase):
    def test_infer_stack_kind_prefers_explicit(self) -> None:
        self.assertEqual(infer_stack_kind({"kind": "prevention", "rule": "replace"}), "prevention")

    def test_rule_applies_to_damage_target_self_scope(self) -> None:
        rule = {"owner": "p1", "target": "self_active"}
        self.assertTrue(rule_applies_to_damage_target(rule, attacker="p2", target_selector="opponent_active", opponent_actor="p1"))
        self.assertFalse(rule_applies_to_damage_target(rule, attacker="p1", target_selector="opponent_active", opponent_actor="p2"))

    def test_resolve_damage_with_priority_stack_orders_replacement_before_prevention(self) -> None:
        rules = [
            {"source": "prevent", "kind": "prevention", "priority": 10, "prevent_amount": 20},
            {"source": "replace", "kind": "replacement", "priority": 1, "set_amount": 80},
        ]
        resolved, traces = resolve_damage_with_priority_stack(30, rules)
        self.assertEqual(resolved, 60)
        self.assertTrue("Replacement rule 'replace' set damage to 80." in traces[0])

    def test_operations_from_timing_rules_orders_by_kind_and_priority(self) -> None:
        timing_rules = [
            {
                "owner": "p1",
                "window": "BEFORE_ATTACK",
                "kind": "normal",
                "priority": 100,
                "target": "self_player",
                "turns_remaining": 1,
                "operation": {"op": "annotation_noop", "params": {"id": "normal"}},
            },
            {
                "owner": "p1",
                "window": "BEFORE_ATTACK",
                "kind": "replacement",
                "priority": 1,
                "target": "self_player",
                "turns_remaining": 1,
                "operation": {"op": "annotation_noop", "params": {"id": "replacement"}},
            },
            {
                "owner": "p1",
                "window": "BEFORE_ATTACK",
                "kind": "prevention",
                "priority": 200,
                "target": "self_player",
                "turns_remaining": 1,
                "operation": {"op": "annotation_noop", "params": {"id": "prevention"}},
            },
        ]
        ops = operations_from_timing_rules(
            timing_rules=timing_rules,
            actor="p1",
            opponent_actor="p2",
            window="BEFORE_ATTACK",
        )
        self.assertEqual([entry["params"]["id"] for entry in ops], ["replacement", "prevention", "normal"])


if __name__ == "__main__":
    unittest.main()
