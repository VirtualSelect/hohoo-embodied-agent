"""Run after physics with E7_EVIDENCE set. Mutations are temporary copies only."""
import csv
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from audit import audit, digest, episode, read

EVIDENCE = os.environ.get("E7_EVIDENCE")


@unittest.skipUnless(EVIDENCE, "Set E7_EVIDENCE to an actual completed run")
class AuditTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(EVIDENCE)
        self.p = read(self.root/"manifest.json")["protocol"]
        self.temp = tempfile.TemporaryDirectory()
        self.cell = Path(self.temp.name)/"cell"
        shutil.copytree(self.root/"clean--phase-aware", self.cell)

    def tearDown(self):
        self.temp.cleanup()

    def verify_cell(self):
        return episode(self.cell, self.p["conditions"][0], "phase-aware", self.p)

    def change_row(self, name, index, field, value):
        path = self.cell/name
        with path.open(encoding="utf8", newline="") as f:
            rows = list(csv.DictReader(f))
        rows[index][field] = value
        with path.open("w", encoding="utf8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_actual_run(self):
        self.assertTrue(audit(self.root)["artifact_valid"])

    def test_changed_event(self):
        (self.cell/"events.json").write_text('[{"tick": 1}]', encoding="utf8")
        with self.assertRaisesRegex(ValueError, "events"):
            self.verify_cell()

    def test_changed_target(self):
        self.change_row("control.csv", 2900, "target_z", ".25")
        with self.assertRaisesRegex(ValueError, "target"):
            self.verify_cell()

    def test_changed_packet(self):
        self.change_row("control.csv", 2800, "received", "[]")
        with self.assertRaisesRegex(ValueError, "packet"):
            self.verify_cell()

    def test_changed_decision(self):
        self.change_row("control.csv", 2800, "stopped_after", "1")
        with self.assertRaisesRegex(ValueError, "stop decision"):
            self.verify_cell()

    def test_changed_placement(self):
        path = self.cell/"summary.json"
        summary = read(path)
        summary["placement"] = not summary["placement"]
        path.write_text(json.dumps(summary), encoding="utf8")
        with self.assertRaisesRegex(ValueError, "placement"):
            self.verify_cell()

    def test_changed_state(self):
        path = self.cell/"states.jsonl"
        states = [json.loads(x) for x in path.read_text(encoding="utf8").splitlines()]
        states[0]["qpos"][0] += .1
        path.write_text("\n".join(json.dumps(s) for s in states), encoding="utf8")
        with self.assertRaisesRegex(ValueError, "cube qpos"):
            self.verify_cell()

    def test_fingerprint_detects_change(self):
        before = digest(self.cell/"events.json")
        with (self.cell/"events.json").open("a", encoding="utf8") as f:
            f.write(" ")
        self.assertNotEqual(before, digest(self.cell/"events.json"))


if __name__ == "__main__":
    unittest.main()
