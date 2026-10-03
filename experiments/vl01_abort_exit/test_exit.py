import unittest
import numpy as np
from exit_policy import exit_target
class Tests(unittest.TestCase):
 def test_hold(self):np.testing.assert_array_equal(exit_target([.1,.2,.18,.033],100,'hold'),[.1,.2,.18,.033])
 def test_open(self):np.testing.assert_array_equal(exit_target([.1,.2,.18,.033],0,'open'),[.1,.2,.18,0])
 def test_wait(self):self.assertEqual(exit_target([0,0,.18,.033],.2,'open-retreat')[2],.18)
 def test_middle(self):self.assertAlmostEqual(exit_target([0,0,.18,.033],.5,'open-retreat')[2],.23)
 def test_end(self):self.assertAlmostEqual(exit_target([0,0,.18,.033],2,'open-retreat')[2],.28)
 def test_copy(self):
  a=np.array([0.,0.,.18,.033]);exit_target(a,2,'open-retreat');self.assertEqual(a[3],.033)
 def test_invalid(self):
  with self.assertRaises(ValueError):exit_target([0,0,0,0],0,'unknown')
  with self.assertRaises(ValueError):exit_target([0,0,0,0],-1,'hold')
if __name__=='__main__':unittest.main()
