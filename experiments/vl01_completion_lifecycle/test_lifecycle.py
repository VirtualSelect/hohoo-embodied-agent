import unittest
from lifecycle import Completion
def good(t):return dict(capture_tick=t,x=.24,y=.12,z=.026,speed=0.,contacts='bin_floor')
class Tests(unittest.TestCase):
    def ready(self):
        c=Completion()
        for t in range(1,132,10):c.update(t,True,True,good(t))
        self.assertEqual(c.state,'VALID');return c
    def test_qualification(self):
        c=Completion();c.update(0,False,True,good(0));self.assertEqual(c.state,'NOT_READY')
        for t in range(1,122,10):c.update(t,True,True,good(t))
        self.assertEqual(c.state,'VERIFYING');c.update(131,True,True,good(131));self.assertEqual(c.completed_at,131)
    def test_bad_revokes_without_erasing_history(self):
        c=self.ready();c.update(141,True,True,{**good(141),'x':.5})
        self.assertEqual((c.state,c.completed_at),('INVALID',131))
    def test_age_boundary(self):
        c=self.ready();c.update(160,True,True,None);self.assertEqual(c.state,'VALID')
        c.update(161,True,True,None);self.assertEqual(c.state,'UNKNOWN')
    def test_stale_replay_cannot_refresh(self):
        c=self.ready();c.update(161,True,True,good(131));self.assertEqual((c.state,c.last),('UNKNOWN',131))
    def test_new_capture_at_deadline_requalifies(self):
        c=self.ready();c.update(161,True,True,good(161));self.assertEqual(c.state,'VERIFYING')
    def test_revalidation_needs_full_window(self):
        c=self.ready();c.update(141,True,True,{**good(141),'speed':1})
        for t in range(151,272,10):c.update(t,True,True,good(t))
        self.assertEqual(c.state,'VERIFYING');c.update(281,True,True,good(281))
        self.assertEqual((c.state,c.completed_at),('VALID',131))
    def test_sequence_and_malformed(self):
        c=self.ready();c.update(141,True,True,{**good(141),'z':float('nan')});self.assertEqual(c.state,'UNKNOWN')
        c.update(151,True,True,good(120));self.assertEqual(c.state,'UNKNOWN')
        c.update(161,True,True,good(162));self.assertEqual(c.state,'UNKNOWN')
        with self.assertRaises(ValueError):c.update(100,True,True,None)
    def test_unknown_is_not_false_placement(self):
        c=self.ready();c.update(161,True,True,None);self.assertEqual(c.events[-1]['reason'],'no-fresh-evidence')
    def test_contact_and_speed_boundaries(self):
        for key,val in [('contacts','bin_floor|left_pad'),('speed',-.1),('speed',.02),('x',.3)]:
            c=self.ready();c.update(141,True,True,{**good(141),key:val});self.assertEqual(c.state,'INVALID')
if __name__=='__main__':unittest.main()
