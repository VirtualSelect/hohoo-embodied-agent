import unittest
from gate import Gate

def packet(t,seq=None,**kwargs):
    return {"seq":t if seq is None else seq,"capture_tick":t,"contacts":"left_pad|right_pad","cube_z":.18,"grasp_error":.01,**kwargs}

def held(policy="revalidate",**options):
    g=Gate(policy,**options)
    g.update(1,"transfer",[packet(1)])
    g.update(31,"transfer")
    assert g.state=="hold"
    return g

class RecoveryTests(unittest.TestCase):
    def test_thresholds_and_policy(self):
        for kwargs in ({"policy":"oops"},{"policy":"revalidate","confirm":0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):Gate(**kwargs)
    def test_clock(self):
        g=Gate("revalidate");g.update(1,"approach")
        for tick in (1,0,True):
            with self.subTest(tick=tick),self.assertRaises(ValueError):g.update(tick,"approach")
    def test_invalid_packet(self):
        for patch in ({"seq":True},{"capture_tick":2},{"seq":-1},{"cube_z":float("nan")},{"grasp_error":-1},{"contacts":3}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                Gate("revalidate").update(1,"transfer",[packet(1,**patch)])
    def test_exact_age(self):
        g=Gate("revalidate");g.update(1,"transfer",[packet(1)]);g.update(30,"transfer")
        self.assertEqual(g.state,"running")
        g.update(31,"transfer");self.assertEqual(g.state,"hold")
    def test_nontransfer_age_does_not_stop(self):
        g=Gate("revalidate");g.update(100,"lift");self.assertEqual(g.state,"running")
    def test_contact_span(self):
        g=Gate("revalidate")
        for t in (1,11):g.update(t,"transfer",[packet(t,contacts="")])
        self.assertEqual(g.state,"running")
        g.update(21,"transfer",[packet(21,contacts="")]);self.assertEqual(g.state,"hold")
    def test_latched_does_not_resume(self):
        g=held("latched")
        for t in range(41,102,10):g.update(t,"hold",[packet(t)])
        self.assertEqual(g.state,"hold")
    def test_naive_receipt_accepts_stale_duplicate(self):
        g=held("receipt");g.update(41,"hold",[packet(1)])
        self.assertEqual(g.state,"running");self.assertEqual(g.events[-1]["age_ticks"],40)
    def test_revalidation_rejects_old_receipt(self):
        g=held();g.update(41,"hold",[packet(1)])
        self.assertEqual(g.state,"hold");self.assertIsNone(g.confirm_start)
    def test_exact_confirmation_boundary(self):
        g=held()
        for t in range(41,91,10):g.update(t,"hold",[packet(t)])
        self.assertEqual(g.state,"hold")
        g.update(91,"hold",[packet(91)]);self.assertEqual(g.state,"running")
        self.assertEqual(g.events[-1]["window_end"]-g.events[-1]["window_start"],50)
    def test_capture_at_hold_does_not_count(self):
        g=held();g.update(32,"hold",[packet(31)])
        self.assertIsNone(g.confirm_start)
    def test_deadline_precedes_same_tick_recovery(self):
        g=held(deadline=60)
        for t in range(41,92,10):g.update(t,"hold",[packet(t)])
        self.assertEqual(g.state,"aborted")
    def test_bad_height_distance_or_contact_resets_window(self):
        for patch in ({"cube_z":.12},{"grasp_error":.05},{"contacts":"left_pad"}):
            with self.subTest(patch=patch):
                g=held();g.update(41,"hold",[packet(41)]);g.update(51,"hold",[packet(51,**patch)])
                self.assertIsNone(g.confirm_start)
    def test_missing_sample_restarts_window(self):
        g=held();g.update(41,"hold",[packet(41)]);g.update(61,"hold",[packet(61)])
        self.assertEqual(g.confirm_start,61)
    def test_reordering_cannot_replace_latest(self):
        g=held();g.update(41,"hold",[packet(41)])
        g.update(51,"hold",[packet(51),packet(21)])
        self.assertEqual(g.latest["capture_tick"],51);self.assertEqual(g.ignored,1)
    def test_sequence_and_capture_must_both_advance(self):
        g=Gate("revalidate");g.update(10,"transfer",[packet(10,seq=10)])
        g.update(12,"transfer",[packet(11,seq=9),packet(9,seq=11)])
        self.assertEqual(g.latest["capture_tick"],10);self.assertEqual(g.ignored,2)
    def test_abort_is_terminal(self):
        g=held(deadline=1);g.update(32,"hold")
        g.update(33,"hold",[packet(33)])
        self.assertEqual(g.state,"aborted")
    def test_silence_cannot_complete_window(self):
        g=held();g.update(41,"hold",[packet(41)]);g.update(91,"hold")
        self.assertEqual(g.state,"hold")
        g.update(101,"hold");self.assertIsNone(g.confirm_start)
if __name__=="__main__":unittest.main()
