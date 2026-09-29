import unittest
from monitor import Monitor

def packet(seq, tick, good=True):
    return {"seq":seq,"capture_tick":tick,"contacts":"left_pad|right_pad" if good else ""}

class MonitorTests(unittest.TestCase):
    def test_three_unique_samples(self):
        m=Monitor("count3")
        for i in range(1,4):
            m.update(i,"transfer",packet(i,i,False))
            self.assertEqual(m.alarm,i==3)
    def test_duplicates_do_not_count(self):
        m=Monitor("count3")
        for i in range(1,20): m.update(i,"transfer",packet(1,1,False))
        self.assertFalse(m.alarm); self.assertEqual(m.streak,1)
    def test_time_threshold_not_sample_count(self):
        m=Monitor("elapsed40")
        for t in [1,6,11,16,20]: m.update(t,"transfer",packet(t,t,False))
        self.assertFalse(m.alarm)
        m.update(21,"transfer",packet(21,21,False))
        self.assertTrue(m.alarm)
    def test_good_resets(self):
        m=Monitor("elapsed40")
        m.update(1,"transfer",packet(1,1,False));m.update(20,"transfer",packet(2,20))
        m.update(21,"transfer",packet(3,21,False));self.assertEqual(m.bad_since,21)
    def test_time_needs_new_bad_evidence(self):
        m=Monitor("elapsed40")
        m.update(1,"transfer",packet(1,1,False));m.update(30,"transfer")
        self.assertFalse(m.alarm)
    def test_stale_exact_boundary(self):
        m=Monitor("fresh60")
        m.update(1,"transfer",packet(1,1));m.update(30,"transfer",packet(1,1))
        self.assertFalse(m.alarm)
        m.update(31,"transfer",packet(1,1));self.assertEqual(m.cause,"stale")
    def test_silence(self):
        m=Monitor("fresh60")
        m.update(1,"transfer",packet(1,1));m.update(31,"transfer")
        self.assertEqual(m.cause,"stale")
    def test_packet_on_expiry_boundary_refreshes_before_age_check(self):
        m=Monitor("fresh60")
        m.update(1,"transfer",packet(1,1));m.update(31,"transfer",packet(2,31))
        self.assertFalse(m.alarm)
    def test_missing_initial_observation(self):
        m=Monitor("fresh60");m.update(1,"transfer");self.assertEqual(m.cause,"stale")
    def test_latched_after_fresh_good_and_phase_exit(self):
        m=Monitor("fresh60");m.update(1,"transfer");m.update(2,"release",packet(2,2))
        self.assertTrue(m.alarm)
    def test_inactive_phase_does_not_alarm(self):
        m=Monitor("fresh60");m.update(1,"release");self.assertFalse(m.alarm)
    def test_future_packet_rejected(self):
        with self.assertRaises(ValueError): Monitor("fresh60").update(1,"transfer",packet(1,2))
    def test_backward_clock_rejected(self):
        m=Monitor("count3");m.update(1,"transfer",packet(1,1))
        with self.assertRaises(ValueError): m.update(1,"transfer")
    def test_reordered_packet_ignored(self):
        m=Monitor("fresh60");m.update(10,"transfer",packet(2,10))
        self.assertFalse(m.update(11,"transfer",packet(1,1,False)))
        self.assertEqual(m.latest["seq"],2)
    def test_new_sequence_cannot_refresh_old_capture(self):
        m=Monitor("fresh60");m.update(1,"transfer",packet(1,1))
        m.update(31,"transfer",packet(2,1));self.assertEqual(m.cause,"stale")
    def test_phase_exit_resets_bad_streak(self):
        m=Monitor("count3");m.update(1,"transfer",packet(1,1,False));m.update(2,"release")
        self.assertEqual(m.streak,0)
    def test_invalid_policy_and_durations(self):
        for args in [("unknown",),("fresh60",0,30),("fresh60",20,0)]:
            with self.assertRaises(ValueError): Monitor(*args)
if __name__=="__main__": unittest.main()
