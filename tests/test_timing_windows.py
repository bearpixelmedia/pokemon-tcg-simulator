import unittest

from core.effect_types import EffectOperation
from core.timing_windows import TimingBus, TimingEvent, TimingHandlerKind, TimingWindow


class TimingWindowTests(unittest.TestCase):
    def test_timing_bus_emits_registered_operations(self) -> None:
        bus = TimingBus()

        def handler(event: TimingEvent) -> list[EffectOperation]:
            _ = event
            return [EffectOperation(op="annotation_noop", params={"window": "ok"})]

        bus.register(TimingWindow.TURN_START, handler)
        ops = bus.emit(TimingEvent(window=TimingWindow.TURN_START, actor="p1"))
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op, "annotation_noop")

    def test_timing_bus_orders_replacement_then_prevention(self) -> None:
        bus = TimingBus()

        def normal(_: TimingEvent) -> list[EffectOperation]:
            return [EffectOperation(op="annotation_noop", params={"kind": "normal"})]

        def prevention(_: TimingEvent) -> list[EffectOperation]:
            return [EffectOperation(op="annotation_noop", params={"kind": "prevention"})]

        def replacement(_: TimingEvent) -> list[EffectOperation]:
            return [EffectOperation(op="annotation_noop", params={"kind": "replacement"})]

        bus.register(TimingWindow.BEFORE_ATTACK, normal, priority=10, kind=TimingHandlerKind.NORMAL)
        bus.register(TimingWindow.BEFORE_ATTACK, prevention, priority=100, kind=TimingHandlerKind.PREVENTION)
        bus.register(TimingWindow.BEFORE_ATTACK, replacement, priority=1, kind=TimingHandlerKind.REPLACEMENT)

        ops = bus.emit(TimingEvent(window=TimingWindow.BEFORE_ATTACK, actor="p1"))
        self.assertEqual([op.params["kind"] for op in ops], ["replacement", "prevention", "normal"])


if __name__ == "__main__":
    unittest.main()
