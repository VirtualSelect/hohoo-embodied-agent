"""Independent reconstruction from recorded packets, decisions and physics.
No imports from the monitor or experiment runner.
"""
import csv
import hashlib
import itertools
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
p=manifest["protocol"]
dt=p["dt_s"]
assert not manifest["dirty"], "run must start from frozen clean code"
for name,expected in manifest["sourceSha256"].items():
    raw=(repo/name).read_bytes(); lf=raw.replace(b"\r\n",b"\n")
    assert expected in {hashlib.sha256(v).hexdigest() for v in (raw,lf,lf.replace(b"\n",b"\r\n"))},name
summary=json.loads((root/"summary.json").read_text())
expected={f"{ms}ms-{c}-{policy}" for ms in p["periods_ms"] for c in p["conditions"] for policy in p["policies"]}
assert len(summary)==len(expected)==45
assert {s["episode"] for s in summary}==expected
strings={"phase","contacts","received_contacts","cause"}
def read_csv(file):
    rows=list(csv.DictReader(file.open(encoding="utf8")))
    for row in rows:
        for k,v in row.items():
            if k not in strings:
                row[k]=float(v) if v!="" else None
                assert row[k] is None or math.isfinite(row[k])
    return rows
both={"left_pad","right_pad"}
all_states,all_traces,results={},{},[]
for s in summary:
    name=s["episode"]; folder=root/name
    trace=read_csv(folder/"control.csv")
    rows=read_csv(folder/"trajectory.csv")
    states=[json.loads(v) for v in (folder/"states.jsonl").read_text().splitlines()]
    all_states[name],all_traces[name]=states,trace
    assert len(rows)==len(states)
    assert not s["warnings"] and s["gate"]["accepted"]
    gate=[r for r in rows if 3.8-1e-9<=r["time"]<4]
    assert len(gate)==10 and all(r["cube_z"]>.1 and both<=set(r["contacts"].split("|")) for r in gate)
    for a,b in zip(rows,rows[1:]): assert abs(b["time"]-a["time"]-.02)<1e-9
    for r,state in zip(rows,states):
        assert r["time"]==state["time"] and r["phase"]==state["phase"]
        assert state["ctrl"]==[r["target_x"],r["target_y"],r["target_z"]-.16,r["grip_target"],r["grip_target"]]
    trace_by_tick={int(r["tick"]):r for r in trace}
    assert trace[0]["tick"]==2001
    assert all(b["tick"]==a["tick"]+1 for a,b in zip(trace,trace[1:]))
    for r in rows:
        tick=round(r["time"]/dt)
        if tick in trace_by_tick:
            assert all(trace_by_tick[tick][k]==v for k,v in r.items())
    cadence=round(s["period_ms"]/1000/dt)
    fault=round(p["fault_start_s"]/dt)
    frozen_capture=((fault-1)//cadence)*cadence+1
    latest=None; streak=0; bad_since=None; decision=None; cause=""; first_bad=None; last_receipt=None
    first_loss=next((r["tick"] for r in trace if r["phase"]=="transfer" and not both<=set(r["contacts"].split("|"))),None)
    for r in trace:
        now=int(r["tick"]); pre=now-1
        assert abs(r["time"]-now*dt)<1e-8
        due=pre%cadence==0
        assert r["due"]==int(due)
        forced=s["condition"] in ("forced-open","replay-good","silence") and fault<=pre<fault+round(p["open_duration_s"]/dt)
        assert r["forced_open"]==int(forced)
        assert r["grip_target"]==(0 if forced else r["nominal_grip_target"])
        expected_packet=None
        if due and not (s["condition"]=="silence" and pre>=fault):
            capture=frozen_capture if s["condition"]=="replay-good" and pre>=fault else now
            contacts=trace_by_tick[capture]["contacts"]
            if s["condition"]=="empty-40ms" and fault<=pre<fault+round(p["empty_duration_s"]/dt): contacts=""
            expected_packet=(int((capture-1)//cadence),capture,contacts)
        packet=None if r["received_seq"] is None else (int(r["received_seq"]),int(r["received_capture_tick"]),r["received_contacts"])
        assert packet==expected_packet,(name,now,"injection")
        unique=packet is not None and (latest is None or packet[0]>latest[0] and packet[1]>latest[1])
        if packet is not None: last_receipt=now
        if unique: latest=packet
        assert r["accepted_unique"]==int(unique)
        assert r["latest_seq"]==latest[0] and r["latest_capture_tick"]==latest[1]
        assert r["age_ticks"]==now-latest[1]
        if decision is None:
            if r["phase"]!="transfer": streak,bad_since=0,None
            elif s["policy"]=="fresh60" and now-latest[1]>=round(p["max_age_ms"]/1000/dt):
                decision,cause=now,"stale"
            elif unique:
                if both<=set(latest[2].split("|")): streak,bad_since=0,None
                else:
                    if first_bad is None: first_bad=now
                    streak+=1
                    if bad_since is None: bad_since=latest[1]
                    trigger=streak>=3 if s["policy"]=="count3" else latest[1]-bad_since>=round(p["bad_duration_ms"]/1000/dt)
                    if trigger: decision,cause=now,"contact"
        assert (r["alarm"],r["cause"],r["bad_streak"],r["bad_since_tick"])==(int(decision is not None),cause,streak,bad_since),(name,now)
    assert s["alarm_tick"]==decision and s["cause"]==cause
    events=json.loads((folder/"events.json").read_text())
    alarms=[e for e in events if e["type"]=="alarm"]
    assert len(alarms)==int(decision is not None)
    if decision is not None:
        assert alarms[0]["tick"]==decision and alarms[0]["cause"]==cause
        assert abs(s["simulation_seconds"]-decision*dt-p["hold_s"])<1e-8
        hold=alarms[0]["hold_target"]
        assert all(r["phase"]=="hold_after_alarm" and [r["target_x"],r["target_y"],r["target_z"],r["nominal_grip_target"]]==hold for r in trace if r["tick"]>decision)
    else: assert abs(s["simulation_seconds"]-9.2)<1e-8
    final=[r for r in rows if r["time"]>=s["simulation_seconds"]-.5]
    ok=decision is None and bool(final) and max(r["cube_z"] for r in rows)>.1 and all(abs(r["cube_x"]-.24)<.045 and abs(r["cube_y"]-.12)<.045 and abs(r["cube_z"]-.026)<.006 and r["cube_speed"]<.02 and not r["finger_contact"] for r in final)
    assert ok==s["success"]
    alarm_row=trace_by_tick.get(decision)
    results.append({"episode":name,"period_ms":s["period_ms"],"condition":s["condition"],"policy":s["policy"],
                    "success":ok,"alarm_s":None if decision is None else decision*dt,"cause":cause,
                    "alarm_from_fault_ms":None if decision is None else (decision-fault)*dt*1000,
                    "first_bad_s":None if first_bad is None else first_bad*dt,
                    "physical_loss_s":None if first_loss is None else first_loss*dt,
                    "capture_at_alarm_s":None if alarm_row is None else alarm_row["latest_capture_tick"]*dt,
                    "age_at_alarm_ms":None if alarm_row is None else alarm_row["age_ticks"]*dt*1000,
                    "sha256":{f:hashlib.sha256((folder/f).read_bytes()).hexdigest() for f in ["control.csv","trajectory.csv","states.jsonl","events.json"]}})
prefixes=0
for ms in p["periods_ms"]:
    for condition in p["conditions"]:
        for a,b in itertools.combinations(p["policies"],2):
            na,nb=f"{ms}ms-{condition}-{a}",f"{ms}ms-{condition}-{b}"
            stop=min([r["alarm_s"] for r in results if r["episode"] in (na,nb) and r["alarm_s"] is not None] or [float("inf")])
            sa=[v for v in all_states[na] if v["time"]<=stop+1e-9]
            sb=[v for v in all_states[nb] if v["time"]<=stop+1e-9]
            assert sa==sb,(na,nb,"physical state prefix")
            prefixes+=1
old=repo/"evidence/transfer-monitor-20260929/clean-once-run-1/states.jsonl"
baseline=[json.loads(v) for v in old.read_text().splitlines()]
clean=0
for ms in p["periods_ms"]:
    for policy in p["policies"]:
        assert all_states[f"{ms}ms-clean-{policy}"]==baseline
        clean+=1

fig,ax=plt.subplots(figsize=(8,4.5),layout="constrained")
for policy,label,color in [("count3","3 unique bad samples","#40745a"),("elapsed40","40 ms span of bad evidence","#8570a4")]:
    data=[r for r in results if r["condition"]=="forced-open" and r["policy"]==policy]
    ax.plot([r["period_ms"] for r in data],[r["alarm_from_fault_ms"] for r in data],marker="o",label=label,color=color)
ax.set(xlabel="Observation period / ms",ylabel="Alarm time minus fault onset / ms",xticks=p["periods_ms"],title="Measured forced-opening runs (one fixed sample phase)")
ax.grid(alpha=.2);ax.legend()
fig.savefig(root/"sampling-delay.png",dpi=180);plt.close(fig)
t=all_traces["20ms-replay-good-elapsed40"]
g=all_traces["20ms-replay-good-fresh60"]
fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True,layout="constrained")
clip=[r for r in t if 4.7<=r["time"]<=5.12]
axes[0].step([r["time"] for r in clip],[int(both<=set(r["contacts"].split("|"))) for r in clip],where="post",label="Physical bilateral contact",color="#ad684d")
packets=[r for r in clip if r["received_seq"] is not None]
axes[0].scatter([r["time"] for r in packets],[int(both<=set(r["received_contacts"].split("|"))) for r in packets],label="Delivered packet says contact",color="#40745a",s=20)
axes[0].set(yticks=[0,1],ylabel="Contact present",title="Same good packet keeps arriving while the cube loses contact")
axes[0].legend(loc="lower left")
axes[1].plot([r["time"] for r in clip],[r["age_ticks"]*dt*1000 for r in clip],color="#8570a4",label="Age of latest unique capture")
axes[1].axhline(p["max_age_ms"],color="#ad684d",linestyle="--",label="60 ms age limit")
alarm=next(r["alarm_s"] for r in results if r["episode"]=="20ms-replay-good-fresh60")
for ax in axes:
    ax.axvline(alarm,color="#40745a",linestyle=":",label="Age alarm at "+str(alarm)+" s" if ax==axes[1] else None)
    ax.axvspan(4.8,5.04,alpha=.08,color="#ad684d");ax.grid(alpha=.15)
axes[1].set(xlabel="Simulation time / s",ylabel="Age / ms",xlim=(4.7,5.12));axes[1].legend()
fig.savefig(root/"freshness-timeline.png",dpi=180);plt.close(fig)
report={"rollouts":45,"paired_state_prefixes":prefixes,"clean_baselines":clean,"randomized":False,"episodes":results}
with (root/"audit.json").open("w",encoding="utf8",newline="\n") as f: f.write(json.dumps(report,indent=2)+"\n")
print(json.dumps({"rollouts":45,"paired_state_prefixes":prefixes,"clean_baselines":clean,"audit":"passed"}))
