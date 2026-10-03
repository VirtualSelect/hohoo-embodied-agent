import unittest
from contracts import ReleaseVerifier,BudgetGate

def good(t):return dict(seq=t,capture_tick=t,contacts='left_pad|right_pad',cube_z=.18,grasp_error=.007)
def released(t):return dict(capture_tick=t,contacts='bin_floor',x=.24,y=.12,z=.026,speed=0.)
class Contracts(unittest.TestCase):
    def test_release_requires_span(self):
        v=ReleaseVerifier()
        for t in range(1,132,10):v.update(t,True,True,released(t))
        self.assertEqual((v.single,v.window),(1,131))
    def test_bad_breaks_window(self):
        v=ReleaseVerifier()
        for t in range(1,122,10):v.update(t,True,True,released(t))
        v.update(131,True,True,{**released(131),'contacts':'left_pad'})
        v.update(141,True,True,released(141));self.assertIsNone(v.window)
    def test_no_command_no_lift(self):
        for flags in ((False,True),(True,False)):
            v=ReleaseVerifier();v.update(1,*flags,released(1));self.assertIsNone(v.single)
    def test_duplicate_and_age(self):
        v=ReleaseVerifier();v.update(1,True,True,released(1));v.update(131,True,True,released(1));self.assertIsNone(v.window)
    def test_support_required(self):
        v=ReleaseVerifier();v.update(1,True,True,{**released(1),'contacts':''});self.assertIsNone(v.single)
    def test_gap_breaks_window(self):
        v=ReleaseVerifier();v.update(1,True,True,released(1));v.update(141,True,True,released(141));self.assertIsNone(v.window)
    def test_boundary_speed(self):
        v=ReleaseVerifier();v.update(1,True,True,{**released(1),'speed':.02});self.assertIsNone(v.single)
    def test_stale_guard_before_cooldown(self):
        g=BudgetGate(2,200);g.state='hold';g.hold_tick=1
        for t in range(11,402,10):g.update(t,'hold',[good(t)])
        self.assertEqual(g.resumes,1);self.assertEqual(g.events[0]['tick'],201)
    def test_budget_aborts(self):
        g=BudgetGate(0);g.state='hold';g.hold_tick=1
        for t in range(11,72,10):g.update(t,'hold',[good(t)])
        self.assertEqual(g.state,'aborted');self.assertEqual(g.events[-1]['reason'],'budget')
    def test_deadline_precedence(self):
        g=BudgetGate(2,1000);g.state='hold';g.hold_tick=1
        for t in range(11,402,10):g.update(t,'hold',[good(t)])
        self.assertEqual(g.state,'aborted');self.assertEqual(g.events[-1]['reason'],'revalidation_deadline')
    def test_old_replay_no_resume(self):
        g=BudgetGate(2);g.update(1,'transfer',[good(1)]);g.update(31,'transfer',[])
        for t in range(41,392,10):g.update(t,'hold',[good(1)])
        self.assertEqual(g.resumes,0)
    def test_invalid_budget(self):
        for cap,cool in ((-1,0),(1,-1),(1.5,0)):
            with self.assertRaises(ValueError):BudgetGate(cap,cool)
if __name__=='__main__':unittest.main()
