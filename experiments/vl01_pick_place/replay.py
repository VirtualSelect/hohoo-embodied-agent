"""Replay saved measured qpos, not a new rollout and not a learned policy."""
import argparse
import json
from pathlib import Path
import mujoco
import imageio.v2 as imageio
from run import HERE

def main():
    p = argparse.ArgumentParser()
    p.add_argument("states", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("output exists")
    model = mujoco.MjModel.from_xml_path(str(HERE / "scene.xml"))
    data = mujoco.MjData(model)
    with mujoco.Renderer(model, height=640, width=960) as renderer:
        with imageio.get_writer(str(a.out), fps=50, codec="libx264") as writer:
            for line in a.states.read_text(encoding="utf-8").splitlines():
                s = json.loads(line)
                data.qpos[:] = s["qpos"]; data.qvel[:] = s["qvel"]; data.time = s["time"]
                mujoco.mj_forward(model, data)
                renderer.update_scene(data, camera="overview")
                writer.append_data(renderer.render())
    print(a.out)

if __name__ == "__main__":
    main()
