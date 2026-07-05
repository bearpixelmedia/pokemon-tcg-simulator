import unittest

from core.effect_layers import ContinuousRule, ContinuousRuleEngine, EffectLayer


class EffectLayerTests(unittest.TestCase):
    def test_layer_engine_applies_numeric_rules_in_order(self) -> None:
        engine = ContinuousRuleEngine()
        engine.add_rule(ContinuousRule(source="a", layer=EffectLayer.HP, priority=1, rule={"max_hp": 20}))
        engine.add_rule(ContinuousRule(source="b", layer=EffectLayer.HP, priority=2, rule={"max_hp": 30}))
        resolved = engine.resolve({"max_hp": 100})
        self.assertEqual(resolved["max_hp"], 150)


if __name__ == "__main__":
    unittest.main()
