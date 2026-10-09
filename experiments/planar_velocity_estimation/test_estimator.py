import unittest
import numpy as np
from estimator import VelocityEstimator
class EstimatorTests(unittest.TestCase):
    def test_constant_velocity_irregular_samples(self):
        e=VelocityEstimator('difference');np.testing.assert_array_equal(e.update(0,[0,0]),[0,0])
        np.testing.assert_allclose(e.update(.02,[.04,-.02]),[2,-1])
        np.testing.assert_allclose(e.update(.07,[.14,-.07]),[2,-1])
    def test_ema_has_startup_lag(self):
        e=VelocityEstimator('ema',.06);e.update(0,[0,0]);v=e.update(.02,[.04,0])
        self.assertGreater(v[0],0);self.assertLess(v[0],2)
    def test_reject_out_of_order_without_corrupting_state(self):
        e=VelocityEstimator('difference');e.update(1,[0,0])
        for t in [1,.5]:
            with self.assertRaises(ValueError):e.update(t,[8,8])
        np.testing.assert_allclose(e.update(2,[1,2]),[1,2])
    def test_invalid(self):
        e=VelocityEstimator('ema')
        for t,p in [(float('nan'),[0,0]),(0,[1]),(0,[0,float('inf')])]:
            with self.assertRaises(ValueError):e.update(t,p)
if __name__=='__main__':unittest.main()
