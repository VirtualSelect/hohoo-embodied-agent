"""Article figure from independently audited metrics; no simulated values."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

p = argparse.ArgumentParser()
p.add_argument("evidence", type=Path)
a = p.parse_args()
m = json.loads((a.evidence / "metrics.json").read_text(encoding="utf8"))
rows = [r for r in m["path_pairs"] if r.get("jump_half_is_primary_test")]
assert len(rows) == 4
by_id = {e["episode"]: e for e in m["episodes"]}
labels, before, after = [], [], []
for r in rows:
    condition, gate = r["condition"], r["gate_mode"]
    labels.append(condition + " / " + gate)
    before.append(by_id[condition + "-" + gate + "-wallclock"]["first_resume"]["J_m"] * 1000)
    after.append(by_id[condition + "-" + gate + "-replan"]["first_resume"]["J_m"] * 1000)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
fig.set_facecolor("#faf8f2")
for ax, vals, title, color, maximum in zip(axes, [before, after], ["Original clock path", "Replanned path"], ["#b57d66", "#467763"], [115, .32]):
    ax.set_facecolor("#faf8f2")
    ax.barh(range(4), vals, color=color, height=.5)
    for i, value in enumerate(vals):
        ax.text(value + maximum * .025, i, f"{value:.3f}", va="center")
    ax.set_xlim(0, maximum)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel("First post-resume XYZ target jump (mm)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=.15)
axes[0].set_yticks(range(4), labels)
axes[0].invert_yaxis()
fig.suptitle("E6 / same gate, different path", x=.035, ha="left", fontsize=16, fontweight="bold")
fig.text(.035, .015, "Different horizontal scales. Four fixed pairs, one rollout per cell; not a success-rate estimate.", fontsize=10)
fig.tight_layout(rect=(0,.065,1,.95))
fig.savefig(a.evidence / "article-jump-comparison.png", dpi=150)
plt.close(fig)
