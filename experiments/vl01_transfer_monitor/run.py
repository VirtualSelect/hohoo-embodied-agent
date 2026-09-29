"""E3: once-only gating versus sampled contact monitors during transfer."""
import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("grasp_gate", HERE.parent / "vl01_grasp_guard" / "run.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
base = guard.base
BASE = guard.BASE
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))


class ContactMonitor:
    """A latched decision on observations; never alters physical contact data."""
    def __init__(self, required):
        if required not in (0, 1, 3):
            raise ValueError("unsupported monitor threshold")
        self.required = required
        self.bad_streak = 0
        self.alarm = False

    def update(self, phase, contacts):
        if self.alarm:
            return True
        if phase not in PROTOCOL["monitor_phases"]:
            self.bad_streak = 0
            return False
        both = {"left_pad", "right_pad"} <= set(contacts.split("|"))
        self.bad_streak = 0 if both else self.bad_streak + 1
        self.alarm = bool(self.required and self.bad_streak >= self.required)
        return self.alarm


def simulate(condition, mode, output):
    if condition not in PROTOCOL["conditions"] or mode not in PROTOCOL["modes"]:
        raise ValueError("unknown condition or mode")
    model = mujoco.MjModel.from_xml_path(str(BASE / "scene.xml"))
    data = mujoco.MjData(model)
    dt = model.opt.timestep
    if abs(dt - base.PROTOCOL["timestep_s"]) > 1e-12:
        raise ValueError("timestep/protocol mismatch")
    cadence = base.PROTOCOL["record_every_steps"]
    if abs(dt * cadence - PROTOCOL["sample_period_s"]) > 1e-12:
        raise ValueError("sample cadence mismatch")
    fault_step = round(PROTOCOL["fault_time_s"] / dt)
    open_steps = round(PROTOCOL["forced_open_duration_s"] / dt)
    mujoco.mj_forward(model, data)
    monitor = ContactMonitor(PROTOCOL["modes"][mode])
    rows, states, events = [], [], []
    step, max_z = 0, -math.inf
    alarm_time = first_bad = first_physical_loss = None
    frozen = None
    gate = None

    def advance(target, phase):
        nonlocal step, max_z, alarm_time, first_bad, first_physical_loss, frozen
        forced = condition == "forced-open" and fault_step <= step < fault_step + open_steps
        effective_grip = 0.0 if forced else float(target[3])
        data.ctrl[:] = [target[0], target[1], target[2] - .16, effective_grip, effective_grip]
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise RuntimeError("non-finite physics state")
        cube = data.body("cube").xpos.copy()
        hand = data.site("grip_center").xpos.copy()
        max_z = max(max_z, float(cube[2]))
        if step % cadence == 0:
            physical = "|".join(base.contacts(model, data))
            missing = condition == "observation-gap" and step == fault_step
            observed = "" if missing else physical
            active = phase in PROTOCOL["monitor_phases"]
            if active and not {"left_pad", "right_pad"} <= set(physical.split("|")) and first_physical_loss is None:
                first_physical_loss = float(data.time)
            if active and not {"left_pad", "right_pad"} <= set(observed.split("|")) and first_bad is None:
                first_bad = float(data.time)
            alarm = monitor.update(phase, observed)
            if alarm and alarm_time is None:
                alarm_time = float(data.time)
                frozen = target.copy()
                events.append({"type": "alarm", "time": alarm_time, "bad_streak": monitor.bad_streak,
                               "hold_target": frozen.tolist(), "cause": "bilateral_contact_missing"})
            adr = model.jnt_dofadr[model.body("cube").jntadr[0]]
            rows.append({
                "time": float(data.time), "phase": phase,
                "target_x": float(target[0]), "target_y": float(target[1]), "target_z": float(target[2]),
                "nominal_grip_target": float(target[3]), "grip_target": effective_grip,
                "cube_x": float(cube[0]), "cube_y": float(cube[1]), "cube_z": float(cube[2]),
                "hand_x": float(hand[0]), "hand_y": float(hand[1]), "hand_z": float(hand[2]),
                "cube_speed": float(np.linalg.norm(data.qvel[adr:adr+3])),
                "finger_contact": int(bool({"left_pad", "right_pad"} & set(physical.split("|")))),
                "contacts": physical, "observed_contacts": observed,
                "fault_open": int(forced), "injected_gap": int(missing),
                "bad_streak": monitor.bad_streak, "alarm": int(alarm),
            })
            states.append({"time": float(data.time), "phase": phase,
                           "qpos": data.qpos.copy().tolist(), "qvel": data.qvel.copy().tolist(),
                           "ctrl": data.ctrl.copy().tolist()})
        step += 1

    previous = np.array([0., 0., .16, 0.])
    for phase, seconds, goal in base.schedule(0):
        if phase == "transfer":
            gate = guard.evaluate(rows, float(data.time))
            if not gate["accepted"]:
                raise RuntimeError("pre-transfer grasp not confirmed; comparison invalid")
            events.append({"type": "gate", "time": float(data.time), **gate})
        goal = np.array(goal, dtype=float)
        nsteps = round(seconds / dt)
        events.append({"type": "phase", "phase": phase, "time": float(data.time)})
        for local_step in range(nsteps):
            a = (local_step + 1) / nsteps
            blend = a * a * (3 - 2 * a)
            target = previous + (goal - previous) * blend
            advance(target, phase)
            if alarm_time is not None:
                break
        if alarm_time is not None:
            events.append({"type": "phase", "phase": "hold_after_loss", "time": float(data.time)})
            for _ in range(round(PROTOCOL["hold_s"] / dt)):
                advance(frozen, "hold_after_loss")
            break
        previous = goal
    warnings = {str(mujoco.mjtWarning(i)): int(w.number) for i, w in enumerate(data.warning) if w.number}
    final = [r for r in rows if r["time"] >= data.time - base.PROTOCOL["success"]["settle_window_s"]]
    path_after_first_bad = None if first_bad is None else sum(
        math.hypot(b["hand_x"]-a["hand_x"], b["hand_y"]-a["hand_y"])
        for a,b in zip(rows, rows[1:]) if a["time"] >= first_bad - 1e-9)
    result = {
        "condition": condition, "mode": mode,
        "success": bool(base.accepted(final, max_z) and not warnings and alarm_time is None),
        "gate": gate, "first_bad_sample_s": first_bad, "first_physical_loss_sample_s": first_physical_loss,
        "alarm_time_s": alarm_time,
        "detection_delay_from_first_bad_ms": None if alarm_time is None else (alarm_time-first_bad)*1000,
        "hand_xy_path_after_first_bad_m": path_after_first_bad,
        "max_cube_z_m": max_z, "final_cube_xyz_m": data.body("cube").xpos.tolist(),
        "final_xy_error_m": float(np.linalg.norm(data.body("cube").xpos[:2] - np.array([.24,.12]))),
        "recorded_rows": len(rows), "simulation_seconds": float(data.time), "warnings": warnings,
    }
    with (output / "trajectory.csv").open("w", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for name, value in [("summary.json",result),("events.json",events)]:
        (output/name).write_text(json.dumps(value, indent=2)+"\n", encoding="utf8")
    (output/"states.jsonl").write_text("\n".join(json.dumps(s) for s in states)+"\n", encoding="utf8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    manifest = base.provenance()
    paths = [HERE/"run.py", HERE/"protocol.json", HERE/"test_monitor.py", HERE/"audit.py",
             HERE.parent/"vl01_grasp_guard"/"run.py", HERE.parent/"vl01_grasp_guard"/"protocol.json",
             BASE/"run.py", BASE/"scene.xml", BASE/"protocol.json"]
    manifest["sourceSha256"] = {v.relative_to(HERE.parents[1]).as_posix(): base.digest(v) for v in paths}
    manifest["protocol"] = PROTOCOL
    (a.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
    results = []
    for condition in PROTOCOL["conditions"]:
        for repeat in range(1, PROTOCOL["repeats"]+1):
            for mode in PROTOCOL["modes"]:
                episode = a.out / f"{condition}-{mode}-run-{repeat}"
                episode.mkdir()
                result = simulate(condition,mode,episode)
                result["episode"] = episode.name
                results.append(result)
                print(json.dumps(result),flush=True)
    (a.out/"summary.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")


if __name__ == "__main__":
    main()
