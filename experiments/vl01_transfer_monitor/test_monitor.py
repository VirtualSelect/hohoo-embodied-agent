import unittest
from run import ContactMonitor
BOTH = "left_pad|right_pad"

class MonitorTests(unittest.TestCase):
    def test_clean_never_alarms(self):
        for n in (0,1,3):
            m=ContactMonitor(n)
            self.assertFalse(any(m.update("transfer",BOTH) for _ in range(80)))
    def test_once_observes_without_interrupting(self):
        m=ContactMonitor(0)
        self.assertFalse(any(m.update("transfer","") for _ in range(80)))
        self.assertEqual(m.bad_streak,80)
    def test_immediate_requires_only_one_bad_sample(self):
        self.assertTrue(ContactMonitor(1).update("transfer","left_pad"))
    def test_three_sample_boundary(self):
        m=ContactMonitor(3)
        self.assertEqual([m.update("transfer","") for _ in range(3)],[False,False,True])
    def test_single_missing_observation_recovers(self):
        m=ContactMonitor(3)
        for value in (BOTH,"",BOTH,BOTH):
            self.assertFalse(m.update("transfer",value))
        self.assertEqual(m.bad_streak,0)
    def test_nonconsecutive_losses_do_not_accumulate(self):
        m=ContactMonitor(3)
        self.assertFalse(any(m.update("transfer",v) for v in ["","",BOTH]*10))
    def test_intended_release_is_not_a_fault(self):
        for phase in ("release","lower","retreat","settle","hold_after_loss"):
            self.assertFalse(ContactMonitor(1).update(phase,""))
    def test_alarm_latches_even_when_contact_returns(self):
        m=ContactMonitor(1)
        self.assertTrue(m.update("transfer",""))
        self.assertTrue(m.update("transfer",BOTH))
        self.assertTrue(m.update("release",BOTH))
    def test_other_contact_is_not_finger_contact(self):
        self.assertTrue(ContactMonitor(1).update("transfer","floor|palm|left_pad"))
    def test_stage_boundary_resets_counter(self):
        m=ContactMonitor(3)
        m.update("transfer","");m.update("transfer","")
        m.update("lower","")
        self.assertFalse(m.update("transfer",""))
        self.assertEqual(m.bad_streak,1)
    def test_invalid_threshold_rejected(self):
        for n in (-1,2,100):
            with self.assertRaises(ValueError): ContactMonitor(n)

if __name__=="__main__": unittest.main()
