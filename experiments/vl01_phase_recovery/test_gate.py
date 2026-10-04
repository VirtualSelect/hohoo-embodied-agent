import unittest
from phase_gate import PhaseGate,recovery_schedule
def p(t,z=.16,contact='left_pad|right_pad'):return dict(seq=t,capture_tick=t,contacts=contact,cube_z=z,grasp_error=.02)
class Contracts(unittest.TestCase):
 def test_low_lower(self):
  for policy,expected in [('phase-aware','running'),('reuse-transfer','hold'),('transfer-only','running')]:
   g=PhaseGate(policy)
   for t in (1,11,21):g.update(t,'lower',[p(t,.08)])
   self.assertEqual(g.state,expected)
 def test_transfer_low(self):
  g=PhaseGate('phase-aware')
  for t in (1,11,21):g.update(t,'transfer',[p(t,.08)])
  self.assertEqual(g.state,'hold')
 def test_frozen_phase(self):
  g=PhaseGate('phase-aware');g.update(1,'lower',[p(1,.08)]);g.update(31,'lower',[])
  for t in range(41,232,10):g.update(t,'hold',[p(t,.08)])
  self.assertEqual(g.state,'running');self.assertEqual(g.events[-1]['interrupted_phase'],'lower');self.assertEqual(g.resumes,1)
 def test_deadline(self):
  g=PhaseGate('phase-aware');g.update(1,'lower',[p(1)]);g.update(31,'lower',[]);g.update(431,'release',[])
  self.assertEqual(g.state,'aborted');self.assertEqual(g.events[-1]['interrupted_phase'],'lower')
 def test_release_inactive(self):
  g=PhaseGate('phase-aware');g.update(100,'release',[]);self.assertEqual(g.state,'running')
 def test_bad_contact(self):
  g=PhaseGate('phase-aware')
  for t in (1,11,21):g.update(t,'lower',[p(t,.08,'bin_floor')])
  self.assertEqual(g.state,'hold')
 def test_schedule(self):
  stages=[(str(i),1,[0]*4) for i in range(9)]
  r=recovery_schedule('lower',stages);self.assertEqual(r[0][0],'lower');self.assertEqual(r[1:],stages[6:])
  with self.assertRaises(ValueError):recovery_schedule('release',stages)
 def test_budget(self):
  g=PhaseGate('phase-aware',cap=0);g.update(1,'lower',[p(1)]);g.update(31,'lower',[])
  for t in range(41,102,10):g.update(t,'hold',[p(t)])
  self.assertEqual(g.state,'aborted');self.assertEqual(g.events[-1]['reason'],'budget')
if __name__=='__main__':unittest.main()
