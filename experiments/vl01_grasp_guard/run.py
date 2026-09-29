"""E2: a sampled observation gate before transfer. Original VL01 remains unchanged."""
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

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "vl01_pick_place"
spec = importlib.util.spec_from_file_location("pick_place_baseline", BASE / "run.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))

def evaluate(rows, now):
    window = [r for r in rows if now-PROTOCOL["window_s"]-1e-9 <= r["time"] <= now]
    complete = (len(window) >= PROTOCOL["min_samples"]
                and window[-1]["time"]-window[0]["time"] >= PROTOCOL["minimum_span_s"]-1e-9
                and now-window[-1]["time"] <= PROTOCOL["max_sample_age_s"]
                and all(0 < b["time"]-a["time"] <= .0200001 for a,b in zip(window,window[1:])))
    finite = bool(window) and all(math.isfinite(r["cube_z"]) for r in window)
    high = finite and all(r["cube_z"] > PROTOCOL["min_cube_z_m"] for r in window)
    both = bool(window) and all({"left_pad","right_pad"} <= set(r["contacts"].split("|")) for r in window)
    reasons = [name for ok,name in [(complete,"incomplete_window"),(high,"height_not_confirmed"),(both,"bilateral_contact_not_confirmed")] if not ok]
    return {"accepted": not reasons, "reasons": reasons, "samples": len(window),
            "window_start": window[0]["time"] if window else None,
            "window_end": window[-1]["time"] if window else None,
            "min_cube_z_m": min(r["cube_z"] for r in window) if finite else None,
            "both_pad_samples": sum({"left_pad","right_pad"} <= set(r["contacts"].split("|")) for r in window)}

def simulate(offset, output, mode, render=False):
    model = mujoco.MjModel.from_xml_path(str(BASE / "scene.xml"))
    data = mujoco.MjData(model)
    if abs(model.opt.timestep - base.PROTOCOL["timestep_s"]) > 1e-12:
        raise ValueError("timestep/protocol mismatch")
    mujoco.mj_forward(model, data)
    rows, states, events = [], [], []
    gate = None
    renderer = mujoco.Renderer(model, height=640, width=960) if render else None
    writer = None
    if render:
        import imageio.v2 as imageio
        writer = imageio.get_writer(str(output / "episode.mp4"), fps=25, codec="libx264", quality=7)
    previous = np.array([0., 0., .16, 0.])
    step = 0
    max_z = -math.inf
    try:
        for phase, seconds, goal in base.schedule(offset):
            rejected = False
            if phase == "transfer":
                gate = evaluate(rows, float(data.time))
                gate["applied"] = mode == "guarded"
                gate["decisionTime"] = float(data.time)
                if mode == "guarded" and not gate["accepted"]:
                    phase, seconds, goal = "hold_after_reject", PROTOCOL["hold_s"], previous
                    rejected = True
            goal = np.array(goal, dtype=float)
            nsteps = round(seconds / model.opt.timestep)
            events.append({"phase": phase, "startTime": float(data.time), "target": goal.tolist()})
            for local_step in range(nsteps):
                a = (local_step + 1) / nsteps
                blend = a * a * (3 - 2 * a)
                target = previous + (goal - previous) * blend
                data.ctrl[:] = [target[0], target[1], target[2] - .16, target[3], target[3]]
                mujoco.mj_step(model, data)
                # Refresh derived positions/contacts to align with the post-step qpos snapshot.
                mujoco.mj_forward(model, data)
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                    raise RuntimeError("non-finite simulation state")
                cube = data.body("cube").xpos.copy()
                hand = data.site("grip_center").xpos.copy()
                max_z = max(max_z, float(cube[2]))
                if step % base.PROTOCOL["record_every_steps"] == 0:
                    touching = base.contacts(model, data)
                    adr = model.jnt_dofadr[model.body("cube").jntadr[0]]
                    row = {
                        "time": float(data.time), "phase": phase,
                        "target_x": float(target[0]), "target_y": float(target[1]), "target_z": float(target[2]),
                        "grip_target": float(target[3]),
                        "cube_x": float(cube[0]), "cube_y": float(cube[1]), "cube_z": float(cube[2]),
                        "hand_x": float(hand[0]), "hand_y": float(hand[1]), "hand_z": float(hand[2]),
                        "cube_speed": float(np.linalg.norm(data.qvel[adr:adr+3])),
                        "finger_contact": int("left_pad" in touching or "right_pad" in touching),
                        "contacts": "|".join(touching),
                    }
                    rows.append(row)
                    states.append({"time": float(data.time), "phase": phase,
                                   "qpos": data.qpos.copy().tolist(), "qvel": data.qvel.copy().tolist(),
                                   "ctrl": data.ctrl.copy().tolist()})
                if renderer and step % 20 == 0:
                    renderer.update_scene(data, camera="overview")
                    pixels = renderer.render().copy()
                    writer.append_data(pixels)
                    if local_step >= nsteps - 20:
                        from PIL import Image
                        Image.fromarray(pixels).save(output / (phase + ".png"))
                step += 1
            previous = goal
            if rejected:
                break
    finally:
        if writer:
            writer.close()
        if renderer:
            renderer.close()
    warnings = {str(mujoco.mjtWarning(i)): int(w.number) for i, w in enumerate(data.warning) if w.number}
    window = [r for r in rows if r["time"] >= data.time - base.PROTOCOL["success"]["settle_window_s"]]
    success = base.accepted(window, max_z) and not warnings
    summary = {
        "offset_m": offset, "mode": mode, "success": success,
        "transfer_executed": any(e["phase"] == "transfer" for e in events),
        "post_gate_hand_xy_distance_m": sum(math.hypot(b["hand_x"]-a["hand_x"], b["hand_y"]-a["hand_y"]) for a,b in zip(rows,rows[1:]) if b["time"] >= gate["decisionTime"]),
        "gate": gate,
        "max_cube_z_m": max_z,
        "final_cube_xyz_m": cube.tolist(),
        "final_xy_error_m": float(np.linalg.norm(cube[:2] - np.array([.24, .12]))),
        "lifted": max_z > base.PROTOCOL["success"]["cube_lift_height_m"],
        "failure": None if success else ("not_lifted" if max_z <= .10 else "not_settled_in_bin"),
        "recorded_rows": len(rows), "simulation_seconds": float(data.time), "warnings": warnings,
    }
    with (output / "trajectory.csv").open("w", encoding="utf-8", newline="") as f:
        writer_csv = csv.DictWriter(f, fieldnames=list(rows[0])); writer_csv.writeheader(); writer_csv.writerows(rows)
    (output / "states.jsonl").write_text("\n".join(json.dumps(s) for s in states) + "\n", encoding="utf-8")
    (output / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = base.provenance()
    manifest["sourceSha256"] = {str(p.relative_to(HERE.parents[1])).replace("\\","/"): base.digest(p) for p in [HERE/"run.py", HERE/"protocol.json", BASE/"run.py", BASE/"scene.xml", BASE/"protocol.json"]}
    manifest["protocol"] = PROTOCOL
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
    results=[]
    for offset in PROTOCOL["offsets_m"]:
        for repeat in range(1,PROTOCOL["repeats"]+1):
            for mode in PROTOCOL["modes"]:
                episode = args.out / ("%s-%03dmm-run-%d" % (mode,round(offset*1000),repeat))
                episode.mkdir()
                result=simulate(offset,episode,mode,args.render and repeat==1)
                result["episode"]=episode.name
                results.append(result)
                print(json.dumps(result),flush=True)
    (args.out/"summary.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")

if __name__ == "__main__":
    main()
