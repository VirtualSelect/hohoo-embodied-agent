"""Frozen E5 matrix. Targets drive actuators; qpos is never teleported."""
import argparse, csv, heapq, importlib.util, json, math
from pathlib import Path
import mujoco
import numpy as np
from gate import Gate

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("gate_baseline",HERE.parent/"vl01_grasp_guard"/"run.py")
guard=importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
base,BASE=guard.base,guard.BASE
P=json.loads((HERE/"protocol.json").read_text())
DT=P["dt_s"]
def save(p,v):
    p.write_text(json.dumps(v,indent=2)+"\n",encoding="utf8",newline="\n")

def segments(schedule,start=0,previous=None):
    previous=np.array([0.,0.,.16,0.]) if previous is None else previous.copy()
    result=[]
    for phase,seconds,goal in schedule:
        goal=np.array(goal,float)
        result.append((start,start+seconds,phase,previous,goal))
        start+=seconds; previous=goal
    return result

def target_at(t,path):
    for start,end,phase,prev,goal in path:
        if t < end-1e-10:
            a=min(1.,max(0.,(t+DT-start)/(end-start)))
            return prev+(goal-prev)*(a*a*(3-2*a)),phase
    return path[-1][4].copy(),"settle"

def simulate(condition,policy,out):
    model=mujoco.MjModel.from_xml_path(str(BASE/"scene.xml"))
    data=mujoco.MjData(model); mujoco.mj_forward(model,data)
    assert abs(model.opt.timestep-DT)<1e-12
    cadence=round(P["period_ms"]/1000/DT)
    gate=Gate(policy,cadence,round(P["max_age_ms"]/1000/DT),round(P["bad_span_ms"]/1000/DT),
              round(P["confirm_span_ms"]/1000/DT),round(P["max_hold_ms"]/1000/DT))
    path=segments(base.schedule(0))
    queue=[]; last_good=None; held=None; max_z=-math.inf; initial_gate=None
    rows=[]; states=[]; controls=[]; replans=[]
    for step in range(round(P["horizon_s"]/DT)):
        t=step*DT; now=step+1
        target,phase=target_at(t,path)
        if phase=="transfer" and initial_gate is None:
            initial_gate=guard.evaluate(rows,float(data.time))
            if not initial_gate["accepted"]:
                raise RuntimeError("pre-transfer gate failed")
        if gate.state!="running":
            target=held.copy(); phase="hold" if gate.state=="hold" else "aborted"
        forced=condition=="gap-and-drop" and P["fault_start_s"]<=t<P["open_end_s"]
        grip=0. if forced else float(target[3])
        data.ctrl[:]=[target[0],target[1],target[2]-.16,grip,grip]
        mujoco.mj_step(model,data); mujoco.mj_forward(model,data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise RuntimeError("nonfinite state")
        physical="|".join(base.contacts(model,data))
        cube=data.body("cube").xpos.copy(); hand=data.site("grip_center").xpos.copy()
        max_z=max(max_z,float(cube[2]))
        actual={"seq":step//cadence,"capture_tick":now,"contacts":physical,
                "cube_z":float(cube[2]),"grasp_error":float(np.linalg.norm(cube-hand))}
        if step%cadence==0:
            gap=condition in ("gap","stale-replay","gap-and-drop") and P["fault_start_s"]<=t<P["gap_end_s"]
            replay=condition=="stale-replay" and P["gap_end_s"]<=t<P["replay_end_s"]
            if not gap:
                p=dict(last_good) if replay else actual
                delay=20 if condition=="delay-40ms" else 40 if condition=="reordered" and t>=P["fault_start_s"] and actual["seq"]%3==0 else 0
                heapq.heappush(queue,(now+delay,actual["seq"],dict(p)))
            if t<P["fault_start_s"]:
                last_good=dict(actual)
        received=[]
        while queue and queue[0][0]<=now:
            received.append(heapq.heappop(queue)[2])
        before=len(gate.events)
        gate.update(now,phase,received)
        for event in gate.events[before:]:
            if event["type"]=="hold":
                held=target.copy()
            elif event["type"]=="resume" and policy=="revalidate":
                previous=np.array([*hand,float(target[3])])
                rest=[("transfer",P["replan_transfer_s"],[.24,.12,.18,.033])]+base.schedule(0)[5:]
                path=segments(rest,now*DT,previous)
                replans.append({"tick":now,"measured_start":previous.tolist(),"old_target":target.tolist()})
        adr=model.jnt_dofadr[model.body("cube").jntadr[0]]
        row={"tick":now,"time":float(data.time),"phase":phase,
             "target_x":float(target[0]),"target_y":float(target[1]),"target_z":float(target[2]),
             "grip_target":grip,"cube_x":float(cube[0]),"cube_y":float(cube[1]),"cube_z":float(cube[2]),
             "hand_x":float(hand[0]),"hand_y":float(hand[1]),"hand_z":float(hand[2]),
             "cube_speed":float(np.linalg.norm(data.qvel[adr:adr+3])),
             "finger_contact":int(bool({"left_pad","right_pad"} & set(physical.split("|")))),"contacts":physical}
        controls.append({"tick":now,"phase":phase,"state":gate.state,
            "received":json.dumps(received,separators=(",",":")),
            "latest_seq":None if gate.latest is None else gate.latest["seq"],
            "capture_tick":None if gate.latest is None else gate.latest["capture_tick"],
            "age_ticks":None if gate.latest is None else now-gate.latest["capture_tick"],
            "good":None if gate.latest is None else int(gate.good(gate.latest)),
            "window_start":gate.confirm_start,"window_end":gate.confirm_last,
            "target_x":float(target[0]),"target_y":float(target[1]),"target_z":float(target[2]),
            "cube_z":float(cube[2]),"physical_contacts":physical})
        if step%base.PROTOCOL["record_every_steps"]==0:
            rows.append(row)
            states.append({"tick":now,"qpos":data.qpos.tolist(),"qvel":data.qvel.tolist(),"ctrl":data.ctrl.tolist()})
    warnings={str(mujoco.mjtWarning(i)):int(w.number) for i,w in enumerate(data.warning) if w.number}
    window=[r for r in rows if r["time"]>=data.time-base.PROTOCOL["success"]["settle_window_s"]]
    resumes=[e for e in gate.events if e["type"]=="resume"]
    result={"condition":condition,"policy":policy,"success":bool(base.accepted(window,max_z) and not warnings),
            "state":gate.state,"holds":sum(e["type"]=="hold" for e in gate.events),"resumes":len(resumes),
            "unsupported_resumes":sum(e["age_ticks"]>=30 or not e["good"] for e in resumes),
            "ignored_packets":gate.ignored,"first_hold_tick":next((e["tick"] for e in gate.events if e["type"]=="hold"),None),
            "first_resume_tick":next((e["tick"] for e in resumes),None),
            "simulation_seconds":float(data.time),"warnings":warnings,"initial_gate":initial_gate}
    for f,records in (("trajectory.csv",rows),("control.csv",controls)):
        with (out/f).open("w",encoding="utf8",newline="") as stream:
            w=csv.DictWriter(stream,fieldnames=list(records[0]),lineterminator="\n"); w.writeheader(); w.writerows(records)
    with (out/"states.jsonl").open("w",encoding="utf8",newline="\n") as stream:
        for r in states: stream.write(json.dumps(r)+"\n")
    save(out/"events.json",gate.events); save(out/"replans.json",replans); save(out/"summary.json",result)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    manifest=base.provenance()
    files=list(HERE.glob("*.py"))+[HERE/"protocol.json",HERE.parent/"vl01_grasp_guard"/"run.py",HERE.parent/"vl01_grasp_guard"/"protocol.json",BASE/"run.py",BASE/"protocol.json",BASE/"scene.xml"]
    manifest["sourceSha256"]={f.relative_to(HERE.parents[1]).as_posix():base.digest(f) for f in files}
    manifest["protocol"]=P;save(a.out/"manifest.json",manifest)
    results=[]
    for condition in P["conditions"]:
        for policy in P["policies"]:
            out=a.out/(condition+"-"+policy);out.mkdir()
            r=simulate(condition,policy,out);r["episode"]=out.name;results.append(r)
            print(json.dumps(r),flush=True)
    save(a.out/"summary.json",results)
if __name__=="__main__":main()
