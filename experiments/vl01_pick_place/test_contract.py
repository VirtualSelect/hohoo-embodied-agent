import unittest
import mujoco
from run import HERE, accepted, schedule

class ContractTests(unittest.TestCase):
    def test_scene_is_dynamic_not_welded_cube(self):
        model = mujoco.MjModel.from_xml_path(str(HERE / "scene.xml"))
        self.assertEqual(model.neq, 0)
        self.assertEqual(model.nu, 5)
        self.assertEqual(model.jnt_type[model.body("cube").jntadr[0]], mujoco.mjtJoint.mjJNT_FREE)
    def test_lift_alone_is_not_success(self):
        r = dict(cube_x=0., cube_y=0., cube_z=.18, cube_speed=0., finger_contact=1)
        self.assertFalse(accepted([r], .18))
    def test_inside_without_lift_is_not_success(self):
        r = dict(cube_x=.24, cube_y=.12, cube_z=.026, cube_speed=0., finger_contact=0)
        self.assertFalse(accepted([r], .026))
        self.assertTrue(accepted([r], .18))
        r["finger_contact"] = 1
        self.assertFalse(accepted([r], .18))
    def test_entire_settle_window_required(self):
        good = dict(cube_x=.24, cube_y=.12, cube_z=.026, cube_speed=0., finger_contact=0)
        bad = dict(good, cube_speed=.1)
        self.assertFalse(accepted([bad, good], .18))
        self.assertFalse(accepted([], .18))
    def test_bias_does_not_move_place_target(self):
        self.assertNotEqual(schedule(0)[0], schedule(.05)[0])
        self.assertEqual(schedule(0)[4:], schedule(.05)[4:])

if __name__ == "__main__":
    unittest.main()
