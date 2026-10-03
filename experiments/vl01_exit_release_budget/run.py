"""E8/E9/E10: common physical scene, frozen interventions, complete state logs."""
import argparse,csv,gzip,hashlib,json,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import mujoco
from contracts import load,BudgetGate,ReleaseVerifier

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];BASE=HERE.parent/'vl01_pick_place'
base=load('e8_base',BASE/'run.py')
PhaseMonitor=load('e8_monitor',HERE.parent/'vl01_phase_contracts/monitor.py').PhaseMonitor
P=json.loads((HERE/'protocol.json').read_text());DT=P['dt_s']

def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def segments(schedule,start=0,previous=None):
    previous=np.array([0.,0.,.16,0.]) if previous is None else previous.copy();result=[]
    for phase,duration,goal in schedule:
        goal=np.array(goal,float);result.append((start,start+duration,phase,previous,goal));start+=duration;previous=goal
    return result
def target_at(t,path):
    for start,end,phase,prev,goal in path:
        if t<end-1e-10:
            a=np.clip((t+DT-start)/(end-start),0,1);return prev+(goal-prev)*a*a*(3-2*a),phase
    return path[-1][4].copy(),'settle'
def between(t,a,b):return a-1e-10<=t<b-1e-10
def gap(condition,t):
    if condition in ('single-gap','lower-silence'):return between(t,*P['faults'][condition])
    if condition=='permanent-gap':return t>=4.3-1e-10
    if condition=='repeated-gap':return between(t,4.3,6.94) and (round(t/DT)-2150)%220<70
    return False

def simulate(study,condition,policy,out):
    model=mujoco.MjModel.from_xml_path(str(BASE/'scene.xml'));data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    assert abs(model.opt.timestep-DT)<1e-12
    monitor=PhaseMonitor('phase-aware') if study=='E8' else BudgetGate(None if policy=='unlimited' else 2,200 if policy=='budget-two-cooldown' else 0) if study=='E10' else None
    verifier=ReleaseVerifier();path=segments(base.schedule(0));held=None;stop_tick=None;max_z=0.;controls=[];states=[];events=[]
    for step in range(round(P['horizon_s']/DT)):
        tick,t=step+1,step*DT;target,phase=target_at(t,path);scheduled=phase
        if study=='E8' and monitor.stopped:
            target=held.copy();phase='exit'
            if policy!='hold':target[3]=0
            if policy=='open-retreat':
                a=np.clip(((tick-stop_tick)*DT-.2)/.6,0,1);target[2]+= .1*a*a*(3-2*a)
        if study=='E10' and monitor.state!='running':target=held.copy();phase=monitor.state
        grip=float(target[3]);fault=False
        if study=='E8' and condition.endswith('drop') or study=='E8' and condition in ('lower-drop-early','lower-drop-late'):
            if between(t,*P['faults'][condition]):grip=0.;fault=True
        if study=='E9':
            if condition in ('stuck-closed','false-good-report') and t>=6.5-1e-10:grip=.033;fault=True
            if condition=='delayed-open' and between(t,6.5,7.0):grip=.033;fault=True
        data.xfrc_applied[:]=0
        if study=='E9' and condition=='post-release-push' and between(t,8.0,8.08):data.xfrc_applied[model.body('cube').id,0]=1.;fault=True
        data.ctrl[:]=[*target[:2],target[2]-.16,grip,grip]
        mujoco.mj_step(model,data);mujoco.mj_forward(model,data)
        assert np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
        cube=data.body('cube').xpos.copy();hand=data.site('grip_center').xpos.copy();contacts='|'.join(base.contacts(model,data));speed=float(np.linalg.norm(data.qvel[:3]));max_z=max(max_z,float(cube[2]))
        physical=dict(seq=step//10,capture_tick=tick,contacts=contacts,cube_z=float(cube[2]),grasp_error=float(np.linalg.norm(cube-hand)),x=float(cube[0]),y=float(cube[1]),z=float(cube[2]),speed=speed)
        packet=dict(physical) if step%10==0 and not gap(condition,t) else None
        if study=='E9' and condition=='false-good-report' and tick==3301:packet={**physical,'contacts':'bin_floor','x':.24,'y':.12,'z':.026,'speed':0.}
        received=[] if packet is None else [packet]
        if study=='E8':
            before=monitor.stopped;monitor.update(tick,phase,received)
            if monitor.stopped and not before:held=target.copy();stop_tick=tick
        if study=='E10':
            before=len(monitor.events);monitor.update(tick,phase,received)
            for event in monitor.events[before:]:
                if event['type']=='hold':held=target.copy()
                elif event['type']=='resume':
                    prev=np.array([*hand,target[3]]);path=segments([('transfer',.5,[.24,.12,.18,.033])]+base.schedule(0)[5:],tick*DT,prev)
        verifier.update(tick,t>=6.5,max_z>.1,packet)
        state=('stopped' if monitor.stopped else 'running') if study=='E8' else monitor.state if study=='E10' else 'observing'
        row=dict(tick=tick,time=float(data.time),phase=phase,scheduled_phase=scheduled,state_after=state,
                 target_x=float(target[0]),target_y=float(target[1]),target_z=float(target[2]),target_grip=float(target[3]),applied_grip=grip,
                 cube_x=float(cube[0]),cube_y=float(cube[1]),cube_z=float(cube[2]),hand_x=float(hand[0]),hand_y=float(hand[1]),hand_z=float(hand[2]),
                 cube_speed=speed,contacts=contacts,finger_contact=int(bool({'left_pad','right_pad'}&set(contacts.split('|')))),
                 received=json.dumps(received,separators=(',',':')),single=verifier.single,window=verifier.window,
                 force_x=float(data.xfrc_applied[model.body('cube').id,0]))
        controls.append(row)
        if step%10==0:states.append(dict(tick=tick,qpos=data.qpos.tolist(),qvel=data.qvel.tolist(),ctrl=data.ctrl.tolist()))
    events=[] if monitor is None else monitor.events
    warnings={str(mujoco.mjtWarning(i)):int(w.number) for i,w in enumerate(data.warning) if w.number}
    tail=[r for r in controls if r['time']>=P['horizon_s']-.5]
    result=dict(study=study,condition=condition,policy=policy,placement=bool(base.accepted(tail,max_z) and not warnings),warnings=warnings,
                first_stop=next((e['tick'] for e in events if e['type'] in ('stop','hold')),None),state=state,resumes=sum(e['type']=='resume' for e in events),
                single_completion=verifier.single if study=='E9' else None,window_completion=verifier.window if study=='E9' else None,
                final_cube_z=float(cube[2]),final_contacts=contacts,max_cube_z=max_z,events=events)
    with gzip.open(out/'control.csv.gz','wt',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(controls[0]),lineterminator='\n');w.writeheader();w.writerows(controls)
    with gzip.open(out/'states.jsonl.gz','wt',encoding='utf8',newline='\n') as f:
        f.write(''.join(json.dumps(s,allow_nan=False)+'\n' for s in states))
    save(out/'summary.json',result);return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    sources=list(HERE.glob('*.py'))+[HERE/'protocol.json',BASE/'run.py',BASE/'protocol.json',BASE/'scene.xml',HERE.parent/'vl01_phase_contracts/monitor.py',HERE.parent/'vl01_recovery_gate/gate.py']
    save(a.out/'manifest.json',dict(at=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),numpy=np.__version__,mujoco=mujoco.__version__,protocol=P,
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in sources}))
    rows=[];hashes={}
    for study,spec in P['studies'].items():
        for condition in spec['conditions']:
            for policy in spec['policies']:
                out=a.out/f'{study}--{condition}--{policy}';out.mkdir();r=simulate(study,condition,policy,out);rows.append(r)
                for name in ('control.csv.gz','states.jsonl.gz','summary.json'):hashes[(out/name).relative_to(a.out).as_posix()]=digest(out/name)
                print(json.dumps(r),flush=True)
    save(a.out/'summary.json',rows);save(a.out/'sha256.json',hashes)
if __name__=='__main__':main()
