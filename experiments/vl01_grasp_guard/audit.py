"""Independent CSV audit: no imports from the controller or its guard."""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root=Path(sys.argv[1])
repo=Path(__file__).resolve().parents[2]
manifest=json.loads((root/"manifest.json").read_text())
for path,expected in manifest["sourceSha256"].items():
    raw=(repo/path).read_bytes(); lf=raw.replace(b"\r\n",b"\n")
    assert expected in {hashlib.sha256(v).hexdigest() for v in (raw,lf,lf.replace(b"\n",b"\r\n"))},path
summary=json.loads((root/"summary.json").read_text())
assert len(summary)==18
all_rows={}
audit=[]
for result in summary:
    name=result["episode"]
    with (root/name/"trajectory.csv").open(encoding="utf8") as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        for k in r:
            if k not in ("phase","contacts"): r[k]=float(r[k])
    all_rows[name]=rows
    assert all(math.isfinite(r[k]) for r in rows for k in ("cube_z","hand_x","hand_y","time"))
    window=[r for r in rows if 3.8-1e-9 <= r["time"] < 4]
    expect=len(window)==10 and all(r["cube_z"]>.1 and {"left_pad","right_pad"}<=set(r["contacts"].split("|")) for r in window)
    assert result["gate"]["accepted"]==expect
    assert not result["warnings"]
    events=json.loads((root/name/"events.json").read_text())
    transfer=any(e["phase"]=="transfer" for e in events)
    assert result["transfer_executed"]==transfer
    if result["mode"]=="guarded" and not expect:
        assert not transfer
        assert events[-1]["phase"]=="hold_after_reject"
        hold=[r for r in rows if r["phase"]=="hold_after_reject"]
        assert all(abs(r["target_x"]-result["offset_m"])<1e-12 and r["target_y"]==0 and r["target_z"]==.18 for r in hold)
        assert not result["success"]
    end=[r for r in rows if r["time"]>=result["simulation_seconds"]-.5]
    success=result["max_cube_z_m"]>.1 and all(abs(r["cube_x"]-.24)<.045 and abs(r["cube_y"]-.12)<.045 and abs(r["cube_z"]-.026)<.006 and r["cube_speed"]<.02 and not r["finger_contact"] for r in end)
    assert success==result["success"]
    distance=sum(math.hypot(b["hand_x"]-a["hand_x"],b["hand_y"]-a["hand_y"]) for a,b in zip(rows,rows[1:]) if b["time"]>=4-1e-9)
    assert abs(distance-result["post_gate_hand_xy_distance_m"])<1e-10
    audit.append({"episode":name,"rows":len(rows),"success":success,"gateAccepted":expect,"transfer":transfer,"distance_m":distance,"csvSha256":hashlib.sha256((root/name/"trajectory.csv").read_bytes()).hexdigest()})
for repeat in range(1,4):
    for bias in ("000","025","050"):
        baseline=all_rows[f"baseline-{bias}mm-run-{repeat}"]
        guarded=all_rows[f"guarded-{bias}mm-run-{repeat}"]
        assert [r for r in baseline if r["time"]<4]==[r for r in guarded if r["time"]<4]
        if bias=="000": assert baseline==guarded
        # Fresh baseline must reproduce the previous experiment exactly, using all recorded fields.
        old=repo/"evidence/vl01-20260928-v2"/f"bias-{bias}mm-run-{repeat}"/"trajectory.csv"
        assert (root/f"baseline-{bias}mm-run-{repeat}"/"trajectory.csv").read_bytes()==old.read_bytes()
(root/"audit.json").write_text(json.dumps({"episodes":audit,"prefixPairsIdentical":9,"baselineMatchesPrevious":9,"successfulPairsIdentical":3},indent=2)+"\n",encoding="utf8")
fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True,layout="constrained")
for mode,color in [("baseline","#8b6954"),("guarded","#3e7161")]:
    rs=all_rows[f"{mode}-025mm-run-1"]
    axes[0].plot([r["time"] for r in rs],[r["cube_z"]*1000 for r in rs],label=mode,color=color)
    origin=next(r for r in rs if r["time"]>3.98)
    axes[1].plot([r["time"] for r in rs],[math.hypot(r["hand_x"]-origin["hand_x"],r["hand_y"]-origin["hand_y"])*1000 for r in rs],label=mode,color=color)
for ax in axes:
    ax.axvline(4,color="#777777",linestyle="--",linewidth=1)
    ax.grid(alpha=.2)
    ax.legend()
axes[0].set_ylabel("Cube centre height (mm)")
axes[1].set_ylabel("Hand XY distance from gate (mm)")
axes[1].set_xlabel("Simulation time (s)")
axes[0].set_title("25 mm pickup bias: same failed lift, different next action")
fig.savefig(root/"guard-comparison.png",dpi=160)
print(json.dumps({"episodesAudited":len(audit),"guardedStops":sum(not r["transfer"] for r in audit),"baselineMatchesPrevious":9,"successfulPairsIdentical":3}))
