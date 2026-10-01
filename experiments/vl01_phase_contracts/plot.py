"""Small static figures from actual E7 logs; no illustrative measurements."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"transfer-only": "#4b7788", "reuse-transfer": "#b47856", "phase-aware": "#54816c"}


def load(root, condition, policy):
    with (root/(condition+"--"+policy)/"control.csv").open(encoding="utf8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results = json.loads((args.root/"audit.json").read_text(encoding="utf8"))
    assert results["artifact_valid"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "#faf9f5", "axes.facecolor": "#faf9f5"})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    for ax, condition, title in zip(axes, ("clean", "lower-drop-early"), ("Normal lowering", "Gripper opens at 5.6 s")):
        for policy, color in COLORS.items():
            rows = load(args.root, condition, policy)
            ax.plot([float(r["time"]) for r in rows], [float(r["cube_z"]) for r in rows], color=color, label=policy, lw=2)
            outcome = next(m for m in results["metrics"] if m["condition"] == condition and m["policy"] == policy)
            if outcome["first_stop"]:
                tick = outcome["first_stop"]["tick"]
                ax.scatter(tick*.002, float(rows[tick-1]["cube_z"]), marker="x", color=color, s=70, zorder=4)
        ax.axhline(.12, ls="--", color="#aaa197", lw=1, label="transfer height threshold")
        ax.axvspan(5.5, 6.5, alpha=.07, color="#7b6991")
        ax.set(xlim=(5.3, 7.3), ylim=(0, .21), title=title, xlabel="Simulation time (s)", ylabel="Cube center height (m)")
        ax.grid(axis="y", alpha=.15)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, frameon=False)
    fig.suptitle("E7 / A stage-specific condition changes the stop decision\nCross = first latched stop; shaded = commanded lower phase", fontsize=13)
    fig.savefig(args.out/"lowering-contracts.png", dpi=130)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), constrained_layout=True)
    for ax, condition in zip(axes, ("lower-silence", "lower-replay")):
        for policy, color in COLORS.items():
            rows = load(args.root, condition, policy)
            ax.plot([float(r["time"]) for r in rows], [float(r["age_ticks"])*2 for r in rows], color=color, label=policy, lw=1.6)
        outcome = next(m for m in results["metrics"] if m["condition"] == condition and m["policy"] == "phase-aware")
        if outcome["first_stop"]:
            ax.axvline(outcome["first_stop"]["tick"]*.002, color=COLORS["phase-aware"], ls=":", label="phase-aware stop")
        ax.axhline(60, ls="--", color="#aaa197", label="60 ms age limit")
        ax.axvspan(5.6, 5.84, color="#b47856", alpha=.1)
        ax.set(xlim=(5.5, 6.), title=condition, xlabel="Simulation time (s)", ylabel="Latest accepted capture age (ms)")
        ax.grid(axis="y", alpha=.15)
    fig.suptitle("E7 / Delivery is not freshness: stale replay does not reset capture age", fontsize=13)
    axes[1].legend(frameon=False, fontsize=9)
    fig.savefig(args.out/"capture-age.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
