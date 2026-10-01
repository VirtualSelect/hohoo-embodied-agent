import math
import unittest
from monitor import PhaseMonitor


def packet(tick, **kwargs):
    return {"seq": tick, "capture_tick": tick, "contacts": "left_pad|right_pad",
            "cube_z": .18, "grasp_error": .005, **kwargs}


class MonitorTests(unittest.TestCase):
    def test_config(self):
        for kwargs in ({"policy": "unknown"}, {"age": True}, {"age": 0}, {"bad_span": .5},
                       {"height": math.nan}, {"error": 0}, {"error": math.inf}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PhaseMonitor(**{"policy": "phase-aware", **kwargs})

    def test_invalid_packets(self):
        for bad in ({"seq": True}, {"seq": -1}, {"capture_tick": 2}, {"capture_tick": -1},
                    {"contacts": []}, {"grasp_error": -1}, {"cube_z": math.nan}, {"cube_z": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                PhaseMonitor("phase-aware").update(1, "transfer", [packet(1, **bad)])

    def test_clock(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "approach")
        for tick in (1, 0, 1.5, True):
            with self.subTest(tick=tick), self.assertRaises(ValueError):
                m.update(tick, "approach")

    def test_transfer_predicate_all_policies(self):
        for policy in ("transfer-only", "reuse-transfer", "phase-aware"):
            for bad in ({"contacts": "left_pad"}, {"grasp_error": .05}, {"cube_z": .12}):
                with self.subTest(policy=policy, bad=bad):
                    m = PhaseMonitor(policy)
                    m.update(1, "transfer", [packet(1, **bad)])
                    m.update(11, "transfer", [packet(11, **bad)])
                    self.assertFalse(m.stopped)
                    m.update(21, "transfer", [packet(21, **bad)])
                    self.assertEqual(m.events[0]["reason"], "grasp")

    def test_lower_height_depends_on_policy(self):
        for policy, expected in (("transfer-only", False), ("reuse-transfer", True), ("phase-aware", False)):
            m = PhaseMonitor(policy)
            for tick in (1, 11, 21):
                m.update(tick, "lower", [packet(tick, cube_z=.06)])
            self.assertEqual(m.stopped, expected)

    def test_age_boundary(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower", [packet(1)])
        m.update(30, "lower")
        self.assertFalse(m.stopped)
        m.update(31, "lower")
        self.assertEqual(m.events[0]["reason"], "stale")

    def test_replay_does_not_refresh_age(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower", [packet(1)])
        for tick in (11, 21, 31):
            m.update(tick, "lower", [packet(1)])
        self.assertEqual(m.ignored, 3)
        self.assertEqual(m.events[0]["age_ticks"], 30)

    def test_sequence_alone_cannot_refresh_age(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower", [packet(1)])
        m.update(31, "lower", [packet(31, capture_tick=1)])
        self.assertTrue(m.stopped)

    def test_old_sequence_is_ignored(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower", [packet(1)])
        m.update(31, "lower", [packet(31, seq=1)])
        self.assertTrue(m.stopped)

    def test_one_bad_report_does_not_stop(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower", [packet(1, contacts="")])
        m.update(11, "lower", [packet(11)])
        m.update(21, "lower", [packet(21, contacts="")])
        m.update(31, "lower", [packet(31)])
        self.assertFalse(m.stopped)
        self.assertIsNone(m.bad_since)

    def test_phase_change_resets_bad_span(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "transfer", [packet(1, contacts="")])
        m.update(21, "lower", [packet(21, contacts="")])
        self.assertFalse(m.stopped)
        m.update(41, "lower", [packet(41, contacts="")])
        self.assertTrue(m.stopped)

    def test_release_intentionally_ends_grasp_monitoring(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower", [packet(1)])
        m.update(100, "release", [packet(100, contacts="")])
        self.assertFalse(m.stopped)

    def test_stop_is_latched(self):
        m = PhaseMonitor("phase-aware")
        m.update(1, "lower")
        m.update(2, "hold", [packet(2)])
        self.assertTrue(m.stopped)
        self.assertEqual(len(m.events), 1)


if __name__ == "__main__":
    unittest.main()
