"""E4: closed-loop sampling cadence and observation freshness matrix."""
import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path
import mujoco
import numpy as np
from monitor import Monitor

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("grasp_gate", HERE.parent/"vl01_grasp_guard"/"run.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
base, BASE = guard.base, guard.BASE
P = json.loads((HERE/"protocol.json").read_text(encoding="utf8"))

def write_json(path, value):
    with path.open("w", encoding="utf8", newline="\n") as f:
        f.write(json.dumps(value, indent=2)+"\n")

def simulate(period, condition, policy, out):
    model = mujoco.MjModel.from_xml_path(str(BASE/"scene.xml"))
    data = mujoco.MjData(model)
    assert model.opt.timestep == P["dt_s"]
    dt = P["dt_s"]
    cadence = round(period/1000/dt)
    assert abs(cadence*dt-period/1000) < 1e-12
    fault = round(P["fault_start_s"]/dt)
    open_end = fault + round(P["open_duration_s"]/dt)
    empty_end = fault + round(P["empty_duration_s"]/dt)
    mujoco.mj_forward(model, data)
    monitor = Monitor(policy, round(P["bad_duration_ms"]/1000/dt), round(P["max_age_ms"]/1000/dt))
    rows, states, trace, events = [], [], [], []
    step, max_z, last_good, frozen, alarm_tick, gate = 0, -math.inf, None, None, None, None

    def advance(target, phase):
        nonlocal step, max_z, last_good, frozen, alarm_tick
        forced = condition in ("forced-open", "replay-good", "silence") and fault <= step < open_end
        grip = 0.0 if forced else float(target[3])
        data.ctrl[:] = [target[0], target[1], target[2]-.16, grip, grip]
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise RuntimeError("non-finite physics")
        now = step+1
        physical = "|".join(base.contacts(model, data))
        packet = None
        due = step % cadence == 0
        if due:
            captured = {"seq": step//cadence, "capture_tick": now, "contacts": physical}
            if condition == "empty-40ms" and fault <= step < empty_end:
                captured["contacts"] = ""
            if condition in ("replay-good", "silence") and step >= fault:
                packet = dict(last_good) if condition == "replay-good" else None
            else:
                packet = captured
                last_good = dict(captured)
        fresh = monitor.update(now, phase, packet)
        if monitor.alarm and alarm_tick is None:
            alarm_tick, frozen = now, target.copy()
            events.append({"type": "alarm", "tick": now, "time": now*dt, "cause": monitor.cause, "hold_target": frozen.tolist()})
        cube = data.body("cube").xpos.copy()
        hand = data.site("grip_center").xpos.copy()
        max_z = max(max_z, float(cube[2]))
        adr = model.jnt_dofadr[model.body("cube").jntadr[0]]
        row = {
            "time": float(data.time), "phase": phase,
            "target_x": float(target[0]), "target_y": float(target[1]), "target_z": float(target[2]),
            "nominal_grip_target": float(target[3]), "grip_target": grip,
            "cube_x": float(cube[0]), "cube_y": float(cube[1]), "cube_z": float(cube[2]),
            "hand_x": float(hand[0]), "hand_y": float(hand[1]), "hand_z": float(hand[2]),
            "cube_speed": float(np.linalg.norm(data.qvel[adr:adr+3])),
            "finger_contact": int(bool({"left_pad","right_pad"} & set(physical.split("|")))),
            "contacts": physical,
        }
        if phase in ("transfer", "hold_after_alarm"):
            trace.append({
                "tick": now, **row, "due": int(due), "forced_open": int(forced),
                "received_seq": None if packet is None else packet["seq"],
                "received_capture_tick": None if packet is None else packet["capture_tick"],
                "received_contacts": "" if packet is None else packet["contacts"],
                "accepted_unique": int(fresh),
                "latest_seq": None if monitor.latest is None else monitor.latest["seq"],
                "latest_capture_tick": None if monitor.latest is None else monitor.latest["capture_tick"],
                "age_ticks": None if monitor.latest is None else now-monitor.latest["capture_tick"],
                "bad_streak": monitor.streak, "bad_since_tick": monitor.bad_since,
                "alarm": int(monitor.alarm), "cause": monitor.cause,
            })
        if step % base.PROTOCOL["record_every_steps"] == 0:
            rows.append(row)
            states.append({"time": float(data.time), "phase": phase, "qpos": data.qpos.tolist(), "qvel": data.qvel.tolist(), "ctrl": data.ctrl.tolist()})
        step += 1

    previous = np.array([0.,0.,.16,0.])
    for phase, seconds, goal in base.schedule(0):
        if phase == "transfer":
            gate = guard.evaluate(rows, float(data.time))
            if not gate["accepted"]:
                raise RuntimeError("pre-transfer gate failed; invalid comparison")
        goal = np.array(goal, dtype=float)
        events.append({"type": "phase", "phase": phase, "tick": step})
        n = round(seconds/P["dt_s"])
        for local in range(n):
            a = (local+1)/n
            target = previous+(goal-previous)*(a*a*(3-2*a))
            advance(target,phase)
            if alarm_tick is not None:
                break
        if alarm_tick is not None:
            for _ in range(round(P["hold_s"]/dt)):
                advance(frozen,"hold_after_alarm")
            break
        previous = goal
    warnings = {str(mujoco.mjtWarning(i)): int(w.number) for i,w in enumerate(data.warning) if w.number}
    window = [r for r in rows if r["time"] >= data.time-base.PROTOCOL["success"]["settle_window_s"]]
    result = {"period_ms": period, "condition": condition, "policy": policy, "gate": gate,
              "alarm_tick": alarm_tick, "alarm_time_s": None if alarm_tick is None else alarm_tick*dt,
              "cause": monitor.cause, "success": bool(alarm_tick is None and base.accepted(window,max_z) and not warnings),
              "simulation_seconds": float(data.time), "warnings": warnings}
    for filename, records in [("trajectory.csv",rows),("control.csv",trace)]:
        with (out/filename).open("w",encoding="utf8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
    with (out/"states.jsonl").open("w",encoding="utf8",newline="\n") as f:
        for s in states:
            f.write(json.dumps(s)+"\n")
    write_json(out/"events.json",events)
    write_json(out/"summary.json",result)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    manifest=base.provenance()
    files=list(HERE.glob("*.py"))+[HERE/"protocol.json",HERE.parent/"vl01_grasp_guard"/"run.py",HERE.parent/"vl01_grasp_guard"/"protocol.json",BASE/"run.py",BASE/"protocol.json",BASE/"scene.xml"]
    manifest["sourceSha256"]={f.relative_to(HERE.parents[1]).as_posix():base.digest(f) for f in files}
    manifest["protocol"]=P
    write_json(a.out/"manifest.json",manifest)
    results=[]
    for period in P["periods_ms"]:
        for condition in P["conditions"]:
            for policy in P["policies"]:
                episode=f"{period}ms-{condition}-{policy}"
                out=a.out/episode
                out.mkdir()
                r=simulate(period,condition,policy,out)
                r["episode"]=episode
                results.append(r)
                print(json.dumps(r),flush=True)
    write_json(a.out/"summary.json",results)

if __name__=="__main__":
    main()
