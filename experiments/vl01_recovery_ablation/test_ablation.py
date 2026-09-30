"""Focused factorial/path contract tests; no experiment rollouts."""
import unittest
import numpy as np
from run import P, DT, Gate, base, segments, target_at, resumed_path, variant_valid
from test_gate import held, packet

class AblationTests(unittest.TestCase):
    def test_exact_factorial_and_reference(self):
        pairs={(v['gate_mode'],v['path_mode']) for v in P['variants']}
        self.assertEqual(pairs,{('receipt','wallclock'),('receipt','replan'),('revalidate','wallclock'),('revalidate','replan'),('latched','wallclock')})
        self.assertEqual(len(P['conditions'])*len(pairs),30)
    def test_invalid_modes(self):
        for a,b in [('latched','replan'),('x','replan'),('receipt','x')]:
            self.assertFalse(variant_valid(a,b))
        with self.assertRaises(ValueError):resumed_path('x',[],np.zeros(3),.033,1)
    def test_wallclock_keeps_original_schedule(self):
        old=segments(base.schedule(0)); new,start=resumed_path('wallclock',old,np.zeros(3),.033,2600)
        self.assertIs(new,old);self.assertIsNone(start)
        self.assertEqual(target_at(5.5,new)[1],'lower')
    def test_replan_measured_start(self):
        hand=np.array([.1,.05,.18]);new,start=resumed_path('replan',[],hand,.033,2600)
        np.testing.assert_array_equal(new[0][3][:3],hand)
        self.assertEqual(new[0][0],5.2)
        self.assertAlmostEqual(new[0][1]-new[0][0],1.5)
        np.testing.assert_array_equal(new[0][4],[.24,.12,.18,.033])
    def test_first_target_near_measured_pose(self):
        hand=np.array([.1,.05,.18]);new,_=resumed_path('replan',[],hand,.033,2600)
        target,phase=target_at(5.2,new)
        self.assertEqual(phase,'transfer');self.assertLess(np.linalg.norm(target[:3]-hand),.001)
    def test_replan_owns_start_copy(self):
        hand=np.array([.1,.05,.18]);new,_=resumed_path('replan',[],hand,.033,2600)
        hand[:]=0;self.assertEqual(new[0][3][0],.1)
    def test_replan_preserves_remaining_phases(self):
        new,_=resumed_path('replan',[],np.array([.1,.05,.18]),.033,2600)
        self.assertEqual([r[2] for r in new],['transfer','lower','release','retreat','settle'])
    def test_repeated_recovery_resets_from_new_measurement(self):
        path,_=resumed_path('replan',[],np.array([.1,.05,.18]),.033,2600)
        path,_=resumed_path('replan',path,np.array([.11,.05,.18]),.033,2610)
        self.assertEqual(path[0][0],2610*DT);self.assertEqual(path[0][3][0],.11)
    def test_path_mode_cannot_change_first_gate_resume(self):
        for policy in ('receipt','revalidate'):
            timings=[]
            for path_mode in ('wallclock','replan'):
                g=held(policy)
                for tick in range(41,102,10):
                    g.update(tick,'hold',[packet(tick)])
                    if g.events[-1]['type']=='resume':break
                timings.append(g.events[-1]['tick'])
            self.assertEqual(timings[0],timings[1])
    def test_latched_never_requests_replan(self):
        g=held('latched')
        for tick in range(41,332,10):g.update(tick,'hold',[packet(tick)])
        self.assertEqual(g.state,'aborted')
        self.assertFalse(any(e['type']=='resume' for e in g.events))
    def test_deadline_precedes_resume_in_both_path_modes(self):
        for mode in ('wallclock','replan'):
            g=held('revalidate',deadline=60)
            for tick in range(41,92,10):g.update(tick,'hold',[packet(tick)])
            self.assertEqual(g.state,'aborted')
    def test_frozen_deterministic_protocol(self):
        self.assertIsNone(P['seed']);self.assertEqual(P['repeats'],1)
        self.assertEqual(P['dt_s'],.002);self.assertEqual(P['horizon_s'],10.8)

if __name__=='__main__':unittest.main()
