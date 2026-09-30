"""Independent artifact audit: no Gate import and no controller replay."""
import csv, hashlib, json, math, sys
from pathlib import Path
import numpy as np
OUT=Path(sys.argv[1]); ROOT=Path(__file__).resolve().parents[2]
read=lambda p:json.loads(p.read_text(encoding="utf8"))
table=lambda p:list(csv.DictReader(p.open(encoding="utf8",newline="")))
manifest=read(OUT/"manifest.json"); p=manifest["protocol"]; results=read(OUT/"summary.json")
assert len(results)==len(p["conditions"])*len(p["policies"])==18
assert len({(r["condition"],r["policy"]) for r in results})==18
for f,digest in manifest["sourceSha256"].items():
    assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==digest,f
success_config=read(ROOT/"experiments/vl01_pick_place/protocol.json")["success"]
def good(pkt):
    return {"left_pad","right_pad"}<=set(pkt["contacts"].split("|")) and pkt["cube_z"]>.12 and pkt["grasp_error"]<.05
hashes={};states={};prefixes=0;max_prefix_error=0.;resume_checks=0
for r in results:
    folder=OUT/r["episode"]
    controls=table(folder/"control.csv"); traj=table(folder/"trajectory.csv"); events=read(folder/"events.json")
    saved=[json.loads(line) for line in (folder/"states.jsonl").read_text().splitlines()]
    states[r["episode"]]=saved
    assert len(controls)==5400 and len(saved)==len(traj)==540
    assert r["initial_gate"]["accepted"] and not r["warnings"]
    last=None;ignored=0;accepted=[]
    for i,row in enumerate(controls):
        now=int(row["tick"]);assert now==i+1
        for pkt in json.loads(row["received"]):
            assert 0<=pkt["capture_tick"]<=now
            if last is None or pkt["seq"]>last["seq"] and pkt["capture_tick"]>last["capture_tick"]:
                last=pkt;accepted.append((now,pkt))
            else:ignored+=1
        assert row["capture_tick"]==("" if last is None else str(last["capture_tick"]))
        assert row["age_ticks"]==("" if last is None else str(now-last["capture_tick"]))
    assert r["ignored_packets"]==ignored
    holds=[e for e in events if e["type"]=="hold"]
    resumes=[e for e in events if e["type"]=="resume"]
    assert r["holds"]==len(holds) and r["resumes"]==len(resumes)
    assert r["unsupported_resumes"]==sum(e["age_ticks"]>=30 or not e["good"] for e in resumes)
    for e in resumes:
        if r["policy"]!="revalidate":continue
        resume_checks+=1
        hold=max(x["tick"] for x in holds if x["tick"]<e["tick"])
        assert e["window_start"]>hold and e["window_end"]-e["window_start"]>=50
        window=[pkt for recv,pkt in accepted if recv<=e["tick"] and e["window_start"]<=pkt["capture_tick"]<=e["window_end"]]
        assert len(window)>=6 and all(good(pkt) for pkt in window)
        assert all(0<b["capture_tick"]-a["capture_tick"]<=10 for a,b in zip(window,window[1:]))
        assert e["tick"]-window[-1]["capture_tick"]<30 and e["tick"]-hold<300
    for event in (e for e in events if e["type"]=="abort"):
        hold=max(e["tick"] for e in holds if e["tick"]<=event["tick"])
        assert event["tick"]-hold==300
    final=[row for row in traj if float(row["time"])>=r["simulation_seconds"]-success_config["settle_window_s"]]
    success=(max(float(row["cube_z"]) for row in traj)>success_config["cube_lift_height_m"]
        and all(abs(float(row["cube_x"])-success_config["bin_center_xy_m"][0])<success_config["max_abs_xy_error_m"]
        and abs(float(row["cube_y"])-success_config["bin_center_xy_m"][1])<success_config["max_abs_xy_error_m"]
        and abs(float(row["cube_z"])-success_config["cube_rest_z_m"])<success_config["max_abs_z_error_m"]
        and float(row["cube_speed"])<success_config["max_linear_speed_m_s"] and row["finger_contact"]=="0" for row in final))
    assert success==r["success"]
    for f in folder.iterdir():
        hashes[f.relative_to(OUT).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
for cond in p["conditions"]:
    a=next(r for r in results if r["condition"]==cond and r["policy"]=="latched")
    for policy in ("receipt","revalidate"):
        b=next(r for r in results if r["condition"]==cond and r["policy"]==policy)
        stop=min(x for x in [a["first_hold_tick"] or 5400,b["first_hold_tick"] or 5400])
        aa=[r for r in states[a["episode"]] if r["tick"]<=stop]
        bb=[r for r in states[b["episode"]] if r["tick"]<=stop]
        assert len(aa)==len(bb)
        for left,right in zip(aa,bb):
            for k in ("qpos","qvel","ctrl"):
                error=float(np.max(np.abs(np.array(left[k])-right[k])))
                max_prefix_error=max(max_prefix_error,error);assert error<1e-10
        prefixes+=1
report={"episodes":len(results),"matched_policy_prefixes":prefixes,"max_prefix_abs_error":max_prefix_error,
        "verified_resume_windows":resume_checks,"rawFileSha256":hashes,
        "kind":"independent CSV/state audit, not independent randomized trials"}
(OUT/"audit.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k!="rawFileSha256"},indent=2))
