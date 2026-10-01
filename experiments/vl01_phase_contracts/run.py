"""E7: fixed-schedule physical rollouts; no new online service or model call."""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import mujoco
import numpy as np
from monitor import PhaseMonitor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE.parent / "vl01_pick_place"
spec = importlib.util.spec_from_file_location("pick_place_e7_base", BASE / "run.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
P = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
DT = P["dt_s"]
RAW = ("control.csv", "trajectory.csv", "states.jsonl", "events.json", "summary.json")


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def sha(path, normalize=False):
    value = path.read_bytes()
    if normalize:
        value = value.replace(b"\r\n", b"\n")
    return hashlib.sha256(value).hexdigest()


def scheduled(t):
    start = 0.
    previous = np.array([0., 0., .16, 0.])
    for phase, duration, end in base.schedule(0):
        goal = np.array(end, dtype=float)
        if t < start + duration - 1e-10:
            a = min(1., max(0., (t + DT - start) / duration))
            return previous + (goal - previous) * a * a * (3 - 2 * a), phase
        start += duration
        previous = goal
    return previous, "settle"


def simulate(condition, policy, out):
    model = mujoco.MjModel.from_xml_path(str(BASE / "scene.xml"))
    assert abs(model.opt.timestep - DT) < 1e-12
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    monitor = PhaseMonitor(policy, P["max_age_ticks"], P["bad_span_ticks"],
                           P["min_transfer_height_m"], P["max_grasp_error_m"])
    held, last_packet = None, None
    controls, rows, states = [], [], []
    for step in range(round(P["horizon_s"] / DT)):
        tick, t = step + 1, step * DT
        goal, scheduled_phase = scheduled(t)
        was_stopped = monitor.stopped
        target = held.copy() if was_stopped else goal
        phase = "hold" if was_stopped else scheduled_phase
        start = condition["start_s"]
        active = start is not None and start - 1e-10 <= t < start + condition["duration_s"] - 1e-10
        opened = active and condition["kind"] == "open"
        grip = 0. if opened else float(target[3])
        data.ctrl[:] = [*target[:2], target[2] - .16, grip, grip]
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise RuntimeError("nonfinite physics")
        physical = "|".join(base.contacts(model, data))
        cube = data.body("cube").xpos.copy()
        hand = data.site("grip_center").xpos.copy()
        error = float(np.linalg.norm(cube - hand))
        received = []
        if step % P["capture_every_ticks"] == 0:
            packet = {"seq": step // P["capture_every_ticks"], "capture_tick": tick,
                      "contacts": physical, "cube_z": float(cube[2]), "grasp_error": error}
            if not active or condition["kind"] not in ("silence", "replay", "empty"):
                received = [packet]
            elif condition["kind"] == "replay":
                if last_packet is None:
                    raise RuntimeError("missing replay baseline")
                received = [dict(last_packet)]
            elif condition["kind"] == "empty":
                received = [{**packet, "contacts": ""}]
            if not active:
                last_packet = dict(packet)
        monitor.update(tick, phase, received)
        if monitor.stopped and not was_stopped:
            held = target.copy()
        adr = model.jnt_dofadr[model.body("cube").jntadr[0]]
        row = {"tick": tick, "time": float(data.time), "phase": phase,
               "scheduled_phase": scheduled_phase, "fault_active": int(active),
               "target_x": float(target[0]), "target_y": float(target[1]), "target_z": float(target[2]),
               "target_grip": float(target[3]), "applied_grip": grip,
               "cube_x": float(cube[0]), "cube_y": float(cube[1]), "cube_z": float(cube[2]),
               "hand_x": float(hand[0]), "hand_y": float(hand[1]), "hand_z": float(hand[2]),
               "grasp_error": error, "cube_speed": float(np.linalg.norm(data.qvel[adr:adr+3])),
               "contacts": physical,
               "finger_contact": int(bool({"left_pad", "right_pad"} & set(physical.split("|"))))}
        controls.append({**row, "stopped_after": int(monitor.stopped),
                         "received": json.dumps(received, separators=(",", ":")),
                         "latest_seq": None if monitor.latest is None else monitor.latest["seq"],
                         "age_ticks": None if monitor.latest is None else tick - monitor.latest["capture_tick"],
                         "bad_since": monitor.bad_since})
        if step % P["capture_every_ticks"] == 0:
            rows.append(row)
            states.append({"tick": tick, "qpos": data.qpos.tolist(), "qvel": data.qvel.tolist(), "ctrl": data.ctrl.tolist()})
    warnings = {str(mujoco.mjtWarning(i)): int(w.number) for i, w in enumerate(data.warning) if w.number}
    tail = [r for r in rows if r["time"] >= P["horizon_s"] - P["placement"]["settle_window_s"]]
    result = {"condition": condition["id"], "policy": policy, "stopped": monitor.stopped,
              "first_stop": monitor.events[0] if monitor.events else None,
              "placement": bool(base.accepted(tail, max(r["cube_z"] for r in controls)) and not warnings),
              "entered_release": any(r["phase"] == "release" for r in controls),
              "max_cube_z_m": max(r["cube_z"] for r in controls), "ignored_packets": monitor.ignored,
              "warnings": warnings, "simulated_seconds": float(data.time)}
    for filename, values in (("control.csv", controls), ("trajectory.csv", rows)):
        with (out / filename).open("w", encoding="utf8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(values)
    (out / "states.jsonl").write_text("".join(json.dumps(s, allow_nan=False)+"\n" for s in states), encoding="utf8", newline="\n")
    save(out / "events.json", monitor.events)
    save(out / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    files = list(HERE.glob("*.py")) + [HERE / "protocol.json", BASE / "run.py", BASE / "protocol.json", BASE / "scene.xml"]
    manifest = {"startedAt": datetime.now(timezone.utc).isoformat(), "kind": "MuJoCo simulation; not physical robot evidence",
                "python": platform.python_version(), "platform": platform.platform(), "mujoco": mujoco.__version__, "numpy": np.__version__,
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "dirtyBeforeOutput": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
                "protocol": P, "sourceSha256": {f.relative_to(ROOT).as_posix(): sha(f) for f in files},
                "sourceLfSha256": {f.relative_to(ROOT).as_posix(): sha(f, True) for f in files}}
    args.out.mkdir(parents=True, exist_ok=False)
    save(args.out / "manifest.json", manifest)
    results, hashes = [], {}
    for condition in P["conditions"]:
        for policy in P["policies"]:
            directory = args.out / (condition["id"] + "--" + policy)
            directory.mkdir()
            result = simulate(condition, policy, directory)
            results.append(result)
            for name in RAW:
                f = directory / name
                hashes[f.relative_to(args.out).as_posix()] = sha(f)
            print(json.dumps(result), flush=True)
    save(args.out / "summary.json", results)
    save(args.out / "raw-sha256.json", hashes)


if __name__ == "__main__":
    main()
