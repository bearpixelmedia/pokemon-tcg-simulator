import unittest

from core.effect_types import EffectOperation
from core.timing_windows import TimingBus, TimingEvent, TimingWindow


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


if __name__ == "__main__":
    unittest.main()
