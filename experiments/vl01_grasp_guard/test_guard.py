import copy
import unittest
from run import evaluate

def samples():
    return [{"time":3.802+i*.02,"cube_z":.16,"contacts":"left_pad|right_pad"} for i in range(10)]

class GuardTest(unittest.TestCase):
    def test_held_object(self):
        self.assertTrue(evaluate(samples(),4)["accepted"])
    def test_single_contact_is_not_grasp(self):
        rows=samples()
        rows[-1]["contacts"]="left_pad"
        self.assertFalse(evaluate(rows,4)["accepted"])
    def test_height_boundary_is_strict(self):
        rows=samples()
        rows[5]["cube_z"]=.1
        self.assertFalse(evaluate(rows,4)["accepted"])
    def test_old_or_short_history_is_rejected(self):
        self.assertFalse(evaluate(samples(),4.1)["accepted"])
        self.assertFalse(evaluate(samples()[1:],4)["accepted"])
        self.assertFalse(evaluate([],4)["accepted"])
    def test_nan_cannot_pass(self):
        rows=samples()
        rows[1]["cube_z"]=float("nan")
        self.assertFalse(evaluate(rows,4)["accepted"])
    def test_out_of_order_or_duplicate_samples(self):
        rows=samples()
        rows[4]["time"]=rows[3]["time"]
        self.assertFalse(evaluate(rows,4)["accepted"])
        rows=samples()
        rows[4],rows[5]=rows[5],rows[4]
        self.assertFalse(evaluate(rows,4)["accepted"])
    def test_transient_contact_does_not_pass(self):
        rows=samples()
        for r in rows[:-1]: r["contacts"]=""
        self.assertFalse(evaluate(rows,4)["accepted"])
    def test_future_evidence_ignored(self):
        rows=samples()
        rows[-1]["time"]=4.01
        self.assertFalse(evaluate(rows,4)["accepted"])

if __name__ == "__main__":
    unittest.main()
