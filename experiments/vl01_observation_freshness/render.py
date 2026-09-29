"""Publication plots from immutable E4 logs; does not rerun physics."""
import csv
import hashlib
import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
root=Path(sys.argv[1])
report=json.loads((root/"audit.json").read_text())
results=report["episodes"]
fig,ax=plt.subplots(figsize=(8,4.5),layout="constrained")
for policy,label,color in [("count3","3 unique bad samples","#40745a"),("elapsed40","40 ms span of bad evidence","#8570a4")]:
    data=[r for r in results if r["condition"]=="forced-open" and r["policy"]==policy]
    ax.plot([r["period_ms"] for r in data],[r["alarm_from_fault_ms"] for r in data],marker="o",label=label,color=color)
ax.set(xlabel="Observation period / ms",ylabel="Alarm time minus fault onset / ms",xticks=[10,20,50],title="Measured runs with a fixed sampling phase")
ax.grid(alpha=.2);ax.legend();fig.savefig(root/"sampling-delay.png",dpi=180);plt.close(fig)
rows=list(csv.DictReader((root/"20ms-replay-good-elapsed40/control.csv").open()))
rows=[r for r in rows if 4.7<=float(r["time"])<=5.12]
packets=[r for r in rows if r["received_seq"]]
both={"left_pad","right_pad"}
alarm=next(r["alarm_s"] for r in results if r["episode"]=="20ms-replay-good-fresh60")
fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True,layout="constrained")
axes[0].step([float(r["time"]) for r in rows],[int(both<=set(r["contacts"].split("|"))) for r in rows],where="post",color="#ad684d",label="Physical bilateral contact")
axes[0].scatter([float(r["time"]) for r in packets],[int(both<=set(r["received_contacts"].split("|"))) for r in packets],s=20,color="#40745a",label="Delivered packet says contact")
axes[0].set(yticks=[0,1],ylabel="Contact present",title="Messages keep arriving; their evidence is getting older")
axes[0].legend(loc="lower left")
axes[1].plot([float(r["time"]) for r in rows],[float(r["age_ticks"])*2 for r in rows],color="#8570a4",label="Age of latest unique capture")
axes[1].axhline(60,color="#ad684d",linestyle="--",label="60 ms age limit")
for ax in axes:
    ax.axvline(alarm,color="#40745a",linestyle=":",label=f"Age alarm at {alarm:.3f} s" if ax==axes[1] else None)
    ax.axvspan(4.8,5.04,alpha=.08,color="#ad684d");ax.grid(alpha=.15)
axes[1].set(xlabel="Simulation time / s",ylabel="Age / ms",xlim=(4.7,5.12));axes[1].legend()
fig.savefig(root/"freshness-timeline.png",dpi=180);plt.close(fig)
metadata={"kind":"Measured log plots, not scene recordings","rendererSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"evidenceCommit":json.loads((root/"manifest.json").read_text())["gitCommit"],"auditSha256":hashlib.sha256((root/"audit.json").read_bytes()).hexdigest(),"files":{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ["sampling-delay.png","freshness-timeline.png"]}}
with (root/"media.json").open("w",encoding="utf8",newline="\n") as f:f.write(json.dumps(metadata,indent=2)+"\n")
