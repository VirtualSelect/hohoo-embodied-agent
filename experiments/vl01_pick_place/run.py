"""VL01: real MuJoCo contacts, fixed script, provenance and replayable state.
Only initialization/replay sets qpos; the controller changes actuator targets.
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def provenance():
    root = HERE.parents[1]
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "mujoco": mujoco.__version__, "numpy": np.__version__,
        "gitCommit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "sourceSha256": {name: digest(HERE / name) for name in ["run.py", "scene.xml", "protocol.json"]},
        "kind": "MuJoCo simulation; not real robot evidence",
    }

def schedule(offset):
    # Grip center uses world coordinates (metres), +z upward. Bias applies only to pickup.
    return [
        ("approach", 1.0, [offset, 0, .16, 0]),
        ("descend", 1.0, [offset, 0, .024, 0]),
        ("close", .8, [offset, 0, .024, .033]),
        ("lift", 1.2, [offset, 0, .18, .033]),
        ("transfer", 1.5, [.24, .12, .18, .033]),
        ("lower", 1.0, [.24, .12, .04, .033]),
        ("release", .7, [.24, .12, .04, 0]),
        ("retreat", 1.0, [.24, .12, .20, 0]),
        ("settle", 1.0, [.24, .12, .20, 0]),
    ]

def contacts(model, data):
    result = []
    for c in data.contact:
        a, b = model.geom(c.geom1).name, model.geom(c.geom2).name
        if "cube_geom" in (a, b):
            result.append(b if a == "cube_geom" else a)
    return sorted(set(result))

def accepted(final_window, max_cube_z):
    c = PROTOCOL["success"]
    if not final_window:
        return False
    return bool(max_cube_z > c["cube_lift_height_m"] and all(
        abs(r["cube_x"] - c["bin_center_xy_m"][0]) < c["max_abs_xy_error_m"]
        and abs(r["cube_y"] - c["bin_center_xy_m"][1]) < c["max_abs_xy_error_m"]
        and abs(r["cube_z"] - c["cube_rest_z_m"]) < c["max_abs_z_error_m"]
        and r["cube_speed"] < c["max_linear_speed_m_s"]
        and not r["finger_contact"]
        for r in final_window))

def simulate(offset, output, render=False):
    model = mujoco.MjModel.from_xml_path(str(HERE / "scene.xml"))
    data = mujoco.MjData(model)
    if abs(model.opt.timestep - PROTOCOL["timestep_s"]) > 1e-12:
        raise ValueError("timestep/protocol mismatch")
    mujoco.mj_forward(model, data)
    rows, states, events = [], [], []
    renderer = mujoco.Renderer(model, height=640, width=960) if render else None
    writer = None
    if render:
        import imageio.v2 as imageio
        writer = imageio.get_writer(str(output / "episode.mp4"), fps=25, codec="libx264", quality=7)
    previous = np.array([0., 0., .16, 0.])
    step = 0
    max_z = -math.inf
    try:
        for phase, seconds, goal in schedule(offset):
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
                if step % PROTOCOL["record_every_steps"] == 0:
                    touching = contacts(model, data)
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
    finally:
        if writer:
            writer.close()
        if renderer:
            renderer.close()
    warnings = {str(mujoco.mjtWarning(i)): int(w.number) for i, w in enumerate(data.warning) if w.number}
    window = [r for r in rows if r["time"] >= data.time - PROTOCOL["success"]["settle_window_s"]]
    success = accepted(window, max_z) and not warnings
    summary = {
        "offset_m": offset, "success": success,
        "max_cube_z_m": max_z,
        "final_cube_xyz_m": cube.tolist(),
        "final_xy_error_m": float(np.linalg.norm(cube[:2] - np.array([.24, .12]))),
        "lifted": max_z > PROTOCOL["success"]["cube_lift_height_m"],
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
    parser.add_argument("--out", type=Path, required=True, help="new output directory; refuses overwrite")
    parser.add_argument("--render", action="store_true", help="record videos and phase screenshots for repeat 1")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "manifest.json").write_text(json.dumps(provenance(), indent=2), encoding="utf-8")
    (args.out / "protocol.json").write_text(json.dumps(PROTOCOL, indent=2), encoding="utf-8")
    results = []
    for offset in PROTOCOL["offsets_m"]:
        for repeat in range(1, PROTOCOL["repeats"] + 1):
            episode = args.out / ("bias-%03dmm-run-%d" % (round(offset * 1000), repeat))
            episode.mkdir()
            result = simulate(offset, episode, args.render and repeat == 1)
            result["episode"] = episode.name
            results.append(result)
            print(json.dumps(result), flush=True)
    (args.out / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
