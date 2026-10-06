import unittest
from completion import Qualified
def packet(t,x=.24):return dict(capture_tick=t,contacts='bin_floor',x=x,y=.12,z=.026,speed=0.)
class Contracts(unittest.TestCase):
 def feed(self,c,start=1,end=141,**kw):
  for t in range(start,end+1,10):c.observe(t,True,True,packet(t),False)
 def test_requires_release(self):
  c=Qualified()
  for t in range(1,201,10):c.observe(t,False,True,packet(t),False)
  self.assertIsNone(c.completed_at);self.assertEqual(c.state,'NOT_READY')
 def test_abort_sticky(self):
  c=Qualified();c.observe(1,False,True,None,True);self.feed(c);self.assertEqual(c.state,'ABORTED');self.assertIsNone(c.completed_at)
 def test_history_survives_abort(self):
  c=Qualified();self.feed(c);at=c.completed_at;c.observe(150,True,True,None,True);self.assertEqual(c.completed_at,at);self.assertEqual(c.state,'ABORTED')
 def test_missing_revokes(self):
  c=Qualified();self.feed(c);c.observe(171,True,True,None,False);self.assertEqual(c.state,'UNKNOWN');self.feed(c,181,321);self.assertEqual(c.state,'VALID')
 def test_bad_packet_revokes(self):
  c=Qualified();self.feed(c);c.observe(151,True,True,packet(151,.5),False);self.assertEqual(c.state,'INVALID')
 def test_replay_cannot_refresh(self):
  c=Qualified();self.feed(c)
  for t in range(151,201,10):c.observe(t,True,True,packet(141),False)
  self.assertEqual(c.state,'UNKNOWN')
 def test_reject_clock_backwards(self):
  c=Qualified();c.observe(3,False,False,None,True)
  with self.assertRaises(ValueError):c.observe(2,False,False,None,False)
 def test_pre_release_capture_does_not_count(self):
  c=Qualified();c.observe(100,True,True,packet(91),False)
  for t in range(111,232,10):c.observe(t,True,True,packet(t-10),False)
  self.assertIsNone(c.completed_at)
  self.assertEqual(c.start,101)
  c.observe(241,True,True,packet(231),False)
  self.assertEqual(c.completed_at,241)
 def test_each_release_starts_a_new_window(self):
  c=Qualified();self.feed(c)
  c.observe(150,False,True,None,False)
  c.observe(160,True,True,packet(151),False)
  self.assertIsNone(c.start)
  self.assertEqual(c.release_tick,160)
if __name__=='__main__':unittest.main()
