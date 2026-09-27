"""Generate a figure and independently audit the saved CSVs. Never calls the simulator."""
import argparse
import csv
import json
import hashlib
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from run import PROTOCOL, accepted, digest, HERE

def main():
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    a = p.parse_args()
    recorded_protocol = json.loads((a.run / "protocol.json").read_text(encoding="utf-8"))
    if recorded_protocol != PROTOCOL:
        raise ValueError("Protocol differs from the recording; check out its recorded commit before auditing.")
    manifest = json.loads((a.run / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sourceSha256"].items():
        raw = (HERE / name).read_bytes()
        lf = raw.replace(b"\r\n", b"\n")
        # Git may change text line endings on checkout; reject any other source change.
        candidates = (raw, lf, lf.replace(b"\n", b"\r\n"))
        if expected not in {hashlib.sha256(value).hexdigest() for value in candidates}:
            raise ValueError("Source differs from recording: " + name)
    summaries = json.loads((a.run / "summary.json").read_text())
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.8), sharex=True, layout="constrained")
    colors = ["#397560", "#586d9e", "#a86d44"]
    audit = []
    for s in summaries:
        with (a.run / s["episode"] / "trajectory.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            for key in row:
                if key not in ("phase", "contacts"):
                    row[key] = float(row[key])
        assert len(rows) == s["recorded_rows"]
        assert all(b["time"] > x["time"] for x, b in zip(rows, rows[1:]))
        window = [r for r in rows if r["time"] >= s["simulation_seconds"] - PROTOCOL["success"]["settle_window_s"]]
        # The exact max is computed at 500Hz during rollout; CSV figure is sampled at 50Hz.
        derived = accepted(window, max(r["cube_z"] for r in rows)) and not s["warnings"]
        assert derived == s["success"], s["episode"]
        audit.append({"episode": s["episode"], "successFromSampledTrajectory": derived, "rows": len(rows)})
        if s["episode"].endswith("run-1"):
            i = PROTOCOL["offsets_m"].index(s["offset_m"])
            time = [r["time"] for r in rows]
            axes[0].plot(time, [r["cube_z"] * 1000 for r in rows], color=colors[i], label=f'Pickup bias {s["offset_m"]*1000:.0f} mm', lw=2)
            axes[1].plot(time, [np.hypot(r["cube_x"]-.24, r["cube_y"]-.12)*1000 for r in rows], color=colors[i], lw=2)
    axes[0].axhline(100, color="#999999", ls="--", lw=1, label="Lift criterion")
    axes[0].set_ylabel("Cube center height (mm)")
    axes[1].set_ylabel("XY distance to bin center (mm)")
    axes[1].set_xlabel("Simulation time (s)")
    axes[0].legend(frameon=False, ncol=2)
    for ax in axes:
        ax.grid(axis="y", alpha=.2); ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("VL01 · Recorded MuJoCo trajectories\nOne deterministic rollout shown per condition", fontsize=14)
    fig.savefig(a.run / "trajectories.png", dpi=150)
    fig.savefig(a.run / "trajectories.svg")
    plt.close(fig)
    (a.run / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"{len(audit)} saved trajectories audited; figure generated from CSV only.")

if __name__ == "__main__":
    main()
