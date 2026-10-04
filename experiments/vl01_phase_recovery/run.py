import argparse,csv,gzip,hashlib,importlib.util,json,platform,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import mujoco
from phase_gate import PhaseGate,recovery_schedule
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OLD=HERE.parent/'vl01_exit_release_budget'
sys.path.insert(0,str(OLD))
spec=importlib.util.spec_from_file_location('e13_reference',OLD/'run.py');ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
P=json.loads((HERE/'protocol.json').read_text('utf8'));DT=P['dt_s']
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf8')
def simulate(condition,policy,out):
    model=mujoco.MjModel.from_xml_path(str(ref.BASE/'scene.xml'));data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    assert abs(model.opt.timestep-DT)<1e-12
    gate=PhaseGate(policy,P['budget'],P['cooldown_ticks']);path=ref.segments(ref.base.schedule(0));held=None;abort_tick=None;max_z=0.;rows=[];states=[]
    for step in range(round(P['horizon_s']/DT)):
        tick=step+1;t=step*DT;target,phase=ref.target_at(t,path);scheduled=phase
        if gate.state=='hold':target=held.copy();phase='hold'
        elif gate.state=='aborted':target=held.copy();phase='aborted'
        fault=condition=='lower-drop' and ref.between(t,*P['faults'][condition])
        if fault:target=target.copy();target[3]=0.
        data.ctrl[:]=[*target[:2],target[2]-.16,target[3],target[3]]
        mujoco.mj_step(model,data);mujoco.mj_forward(model,data)
        assert np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
        cube=data.body('cube').xpos.copy();hand=data.site('grip_center').xpos.copy();contacts='|'.join(ref.base.contacts(model,data));speed=float(np.linalg.norm(data.qvel[:3]));max_z=max(max_z,float(cube[2]))
        packet=dict(seq=step//10,capture_tick=tick,contacts=contacts,cube_z=float(cube[2]),grasp_error=float(np.linalg.norm(cube-hand)),x=float(cube[0]),y=float(cube[1]),z=float(cube[2]),speed=speed) if step%10==0 and not (condition in P['faults'] and condition!='lower-drop' and ref.between(t,*P['faults'][condition])) else None
        received=[] if packet is None else [packet];before=len(gate.events);gate.update(tick,phase,received)
        for e in gate.events[before:]:
            if e['type']=='hold':held=target.copy()
            elif e['type']=='abort':abort_tick=tick
            elif e['type']=='resume':path=ref.segments(recovery_schedule(gate.context,ref.base.schedule(0)),tick*DT,np.array([*hand,target[3]]))
        rows.append(dict(tick=tick,time=float(data.time),phase=phase,scheduled_phase=scheduled,state_after=gate.state,interrupted_phase=gate.context,actuator_fault=int(fault),
            target_x=float(target[0]),target_y=float(target[1]),target_z=float(target[2]),target_grip=float(target[3]),
            cube_x=float(cube[0]),cube_y=float(cube[1]),cube_z=float(cube[2]),hand_x=float(hand[0]),hand_y=float(hand[1]),hand_z=float(hand[2]),cube_speed=speed,
            contacts=contacts,finger_contact=int(bool({'left_pad','right_pad'}&set(contacts.split('|')))),received=json.dumps(received,separators=(',',':'))))
        if step%10==0:states.append(dict(tick=tick,qpos=data.qpos.tolist(),qvel=data.qvel.tolist(),ctrl=data.ctrl.tolist()))
    warnings={str(mujoco.mjtWarning(i)):int(w.number) for i,w in enumerate(data.warning) if w.number}
    tail=[r for r in rows if r['time']>=P['horizon_s']-.5]
    result=dict(condition=condition,policy=policy,placement=bool(ref.base.accepted(tail,max_z) and not warnings),warnings=warnings,abort_tick=abort_tick,
        state=gate.state,resumes=gate.resumes,final_cube_z=float(cube[2]),final_contacts=contacts,max_cube_z=max_z,events=gate.events)
    with gzip.open(out/'control.csv.gz','wt',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    with gzip.open(out/'states.jsonl.gz','wt',encoding='utf8',newline='\n') as f:f.write(''.join(json.dumps(s,allow_nan=False)+'\n' for s in states))
    save(out/'summary.json',result);return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);out=p.parse_args().out;out.mkdir(parents=True,exist_ok=False)
    sources=list(HERE.glob('*.py'))+[HERE/'protocol.json',OLD/'run.py',OLD/'contracts.py',OLD/'protocol.json',ref.BASE/'run.py',ref.BASE/'protocol.json',ref.BASE/'scene.xml',HERE.parent/'vl01_phase_contracts/monitor.py',HERE.parent/'vl01_recovery_gate/gate.py']
    save(out/'manifest.json',dict(at=datetime.now(timezone.utc).isoformat(),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),python=platform.python_version(),numpy=np.__version__,mujoco=mujoco.__version__,
        protocol=P,sources={s.relative_to(ROOT).as_posix():hashlib.sha256(s.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for s in sources}))
    results=[];hashes={}
    for condition in P['conditions']:
        for policy in P['policies']:
            d=out/(condition+'--'+policy);d.mkdir();r=simulate(condition,policy,d);results.append(r);print(json.dumps(r),flush=True)
            for name in ('control.csv.gz','states.jsonl.gz','summary.json'):hashes[(d/name).relative_to(out).as_posix()]=hashlib.sha256((d/name).read_bytes()).hexdigest()
    save(out/'summary.json',results);save(out/'sha256.json',hashes)
if __name__=='__main__':main()
