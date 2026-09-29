"""Independent audit of CSV/state evidence; imports neither runner nor monitor."""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1])
repo = Path(__file__).resolve().parents[2]
manifest = json.loads((root/"manifest.json").read_text())
p = manifest["protocol"]
for name, expected in manifest["sourceSha256"].items():
    raw = (repo/name).read_bytes()
    lf = raw.replace(b"\r\n",b"\n")
    assert expected in {hashlib.sha256(x).hexdigest() for x in (raw,lf,lf.replace(b"\n",b"\r\n"))}, name
results = json.loads((root/"summary.json").read_text())
assert len(results) == 27
expected_names = {f"{c}-{m}-run-{r}" for c in p["conditions"] for m in p["modes"] for r in range(1,4)}
assert {s["episode"] for s in results} == expected_names
rows_by_name, states_by_name, audits = {}, {}, []
both = {"left_pad","right_pad"}
for s in results:
    name = s["episode"]
    with (root/name/"trajectory.csv").open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for k in row:
            if k not in ("phase","contacts","observed_contacts"):
                row[k] = float(row[k])
                assert math.isfinite(row[k])
    states = [json.loads(line) for line in (root/name/"states.jsonl").read_text().splitlines()]
    rows_by_name[name], states_by_name[name] = rows, states
    assert len(rows) == len(states) == s["recorded_rows"]
    assert all(abs((b["time"]-a["time"])-.02)<1e-10 for a,b in zip(rows,rows[1:]))
    window = [r for r in rows if 3.8-1e-9 <= r["time"] < 4]
    assert len(window)==10 and all(r["cube_z"]>.1 and both<=set(r["contacts"].split("|")) for r in window)
    assert s["gate"]["accepted"] and not s["warnings"]
    first_bad = physical_loss = decision = None
    streak, latched = 0, False
    for r,state in zip(rows,states):
        t = r["time"]
        # Samples are post-step; fault interval is defined on pre-step simulation time.
        pre_step = round((t-.002)/.002)*.002
        forced = s["condition"]=="forced-open" and 4.8-1e-9 <= pre_step < 5.04-1e-9
        gap = s["condition"]=="observation-gap" and abs(pre_step-4.8)<1e-9
        assert r["fault_open"]==int(forced) and r["injected_gap"]==int(gap)
        observed = "" if gap else r["contacts"]
        assert observed==r["observed_contacts"]
        assert state["time"]==t and state["phase"]==r["phase"]
        assert state["ctrl"]==[r["target_x"],r["target_y"],r["target_z"]-.16,r["grip_target"],r["grip_target"]]
        assert r["grip_target"]==(0 if forced else r["nominal_grip_target"])
        if r["phase"]=="transfer":
            if not both<=set(observed.split("|")) and first_bad is None: first_bad=t
            if not both<=set(r["contacts"].split("|")) and physical_loss is None: physical_loss=t
        if not latched:
            streak = streak+1 if r["phase"]=="transfer" and not both<=set(observed.split("|")) else 0
            if p["modes"][s["mode"]] and streak>=p["modes"][s["mode"]]:
                latched=True
                decision=t
        assert r["alarm"]==int(latched) and r["bad_streak"]==streak
    assert s["first_bad_sample_s"]==first_bad
    assert s["first_physical_loss_sample_s"]==physical_loss
    assert s["alarm_time_s"]==decision
    events=json.loads((root/name/"events.json").read_text())
    alarms=[e for e in events if e["type"]=="alarm"]
    assert len(alarms)==int(decision is not None)
    if decision is not None:
        assert abs(s["simulation_seconds"]-decision-.6)<1e-10
        assert abs(s["detection_delay_from_first_bad_ms"]-(decision-first_bad)*1000)<1e-9
        target=alarms[0]["hold_target"]
        assert all([r["target_x"],r["target_y"],r["target_z"],r["nominal_grip_target"]]==target for r in rows if r["time"]>decision)
        assert all(r["phase"]=="hold_after_loss" for r in rows if r["time"]>decision)
    else:
        assert abs(s["simulation_seconds"]-9.2)<1e-10
    final=[r for r in rows if r["time"]>=s["simulation_seconds"]-.5]
    ok=decision is None and max(r["cube_z"] for r in rows)>.1 and bool(final) and all(
        abs(r["cube_x"]-.24)<.045 and abs(r["cube_y"]-.12)<.045 and abs(r["cube_z"]-.026)<.006
        and r["cube_speed"]<.02 and not r["finger_contact"] for r in final)
    assert ok==s["success"]
    path=None if first_bad is None else sum(math.hypot(b["hand_x"]-a["hand_x"],b["hand_y"]-a["hand_y"]) for a,b in zip(rows,rows[1:]) if a["time"]>=first_bad-1e-9)
    assert path==s["hand_xy_path_after_first_bad_m"]
    audits.append({"episode":name,"success":ok,"firstBadSample_s":first_bad,"physicalLossSample_s":physical_loss,
                   "alarm_s":decision,"pathAfterFirstBad_mm":None if path is None else path*1000,
                   "csvSha256":hashlib.sha256((root/name/"trajectory.csv").read_bytes()).hexdigest()})

prefix_checks=0
for c in p["conditions"]:
    for repeat in range(1,4):
        reference=states_by_name[f"{c}-once-run-{repeat}"]
        for mode in ("immediate","debounced"):
            name=f"{c}-{mode}-run-{repeat}"
            s=next(s for s in results if s["episode"]==name)
            until=s["alarm_time_s"] if s["alarm_time_s"] is not None else math.inf
            assert [r for r in reference if r["time"]<=until]==[r for r in states_by_name[name] if r["time"]<=until]
            prefix_checks+=1
for c in p["conditions"]:
    for mode in p["modes"]:
        first=states_by_name[f"{c}-{mode}-run-1"]
        for repeat in (2,3): assert first==states_by_name[f"{c}-{mode}-run-{repeat}"]
for repeat in range(1,4):
    old=repo/"evidence/grasp-guard-20260929"/f"guarded-000mm-run-{repeat}"/"states.jsonl"
    baseline=[json.loads(x) for x in old.read_text().splitlines()]
    for mode in p["modes"]: assert baseline==states_by_name[f"clean-{mode}-run-{repeat}"]
    for mode in ("once","debounced"): assert baseline==states_by_name[f"observation-gap-{mode}-run-{repeat}"]

report={"episodes":audits,"pairedPrefixesIdentical":prefix_checks,"deterministicRepeatComparisons":18,
        "cleanTrajectoriesMatchPrevious":9,"gapTolerantTrajectoriesMatchClean":6}
(root/"audit.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
fig,axes=plt.subplots(3,1,figsize=(9,8),sharex=True,layout="constrained")
for mode,color in [("once","#9a6350"),("immediate","#487ba0"),("debounced","#427558")]:
    rows=rows_by_name[f"forced-open-{mode}-run-1"]
    xs=[r["time"] for r in rows]
    start=next(r for r in rows if r["time"]>=4.8)
    axes[0].plot(xs,[r["cube_z"]*1000 for r in rows],label=mode,color=color)
    axes[1].plot(xs,[math.hypot(r["hand_x"]-start["hand_x"],r["hand_y"]-start["hand_y"])*1000 for r in rows],label=mode,color=color)
    axes[2].step(xs,[r["bad_streak"] for r in rows],where="post",color=color,label=mode)
for ax in axes:
    ax.axvspan(4.8,5.04,color="#aeab87",alpha=.15)
    ax.axvline(4.8,color="#777777",linestyle="--",linewidth=1)
    ax.grid(alpha=.2); ax.legend(loc="upper left")
axes[0].set_ylabel("Cube centre height (mm)")
axes[1].set_ylabel("Hand XY displacement (mm)")
axes[2].set_ylabel("Consecutive bad samples")
axes[2].set_xlabel("Simulation time (s)")
axes[2].set_xlim(4.6,6.0)
axes[0].set_title("Forced-open fault: cancelling transfer does not catch the cube")
fig.savefig(root/"monitor-comparison.png",dpi=160)
print(json.dumps({k:v for k,v in report.items() if k!="episodes"}))
print(json.dumps([s for s in results if s["episode"].endswith("run-1")],indent=2))
