import argparse,csv,gzip,hashlib,importlib.util,json,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import mujoco
from lifecycle import Completion

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PREV=HERE.parent/'vl01_exit_release_budget'
sys.path.insert(0,str(PREV))
spec=importlib.util.spec_from_file_location('previous_series',PREV/'run.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
sys.path.pop(0)
P=json.loads((HERE/'protocol.json').read_text('utf8'));DT=P['dt_s']
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def simulate(condition,out):
    model=mujoco.MjModel.from_xml_path(str(previous.BASE/'scene.xml'));data=mujoco.MjData(model)
    assert abs(model.opt.timestep-DT)<1e-12
    mujoco.mj_forward(model,data)
    current=Completion(P['span_ticks'],P['capture_every_ticks'],P['age_ticks'])
    old=previous.ReleaseVerifier();path=previous.segments(previous.base.schedule(0))
    rows=[];states=[];max_z=0.;replay=None
    for step in range(round(P['horizon_s']/DT)):
        tick=step+1;t=step*DT;target,phase=previous.target_at(t,path)
        data.ctrl[:]=[target[0],target[1],target[2]-.16,target[3],target[3]]
        data.xfrc_applied[:]=0
        if condition in ('push','false-good-after-push') and previous.between(t,8,8.08):
            data.xfrc_applied[model.body('cube').id,0]=1.
        mujoco.mj_step(model,data);mujoco.mj_forward(model,data)
        assert np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
        cube=data.body('cube').xpos;hand=data.site('grip_center').xpos
        adr=model.jnt_dofadr[model.body('cube').jntadr[0]]
        speed=float(np.linalg.norm(data.qvel[adr:adr+3]));max_z=max(max_z,float(cube[2]))
        contacts='|'.join(previous.base.contacts(model,data))
        physical=dict(capture_tick=tick,x=float(cube[0]),y=float(cube[1]),z=float(cube[2]),speed=speed,contacts=contacts)
        packet=dict(physical) if step%P['capture_every_ticks']==0 else None
        if packet and t<8:replay=dict(packet)
        if packet and previous.between(t,8,8.4):
            if condition=='silence':packet=None
            elif condition=='stale-replay':packet=dict(replay)
        if condition=='boundary-gap' and tick in P['boundary_drop_ticks']:packet=None
        if condition=='false-bad' and tick==P['false_bad_tick']:packet={**physical,'x':.4}
        if condition=='false-good-after-push' and tick==P['false_good_tick']:
            packet={**physical,'x':.24,'y':.12,'z':.026,'speed':0.,'contacts':'bin_floor'}
        current.update(tick,t>=6.5,max_z>.1,packet);old.update(tick,t>=6.5,max_z>.1,packet)
        rows.append(dict(tick=tick,time=float(data.time),phase=phase,cube_x=float(cube[0]),cube_y=float(cube[1]),cube_z=float(cube[2]),cube_speed=speed,
            finger_contact=int(bool({'left_pad','right_pad'}&set(contacts.split('|')))),contacts=contacts,
            received=json.dumps(packet,separators=(',',':')),state=current.state,completed_at=current.completed_at,
            latched=old.window,force_x=float(data.xfrc_applied[model.body('cube').id,0])))
        if step%10==0:states.append(dict(tick=tick,qpos=data.qpos.tolist(),qvel=data.qvel.tolist(),ctrl=data.ctrl.tolist()))
    warnings={str(i):int(w.number) for i,w in enumerate(data.warning) if w.number}
    result=dict(condition=condition,completed_at=current.completed_at,latched=old.window,final_state=current.state,
        final_placement=bool(previous.base.accepted([r for r in rows if r['time']>=11.5],max_z) and not warnings),
        warnings=warnings,events=current.events)
    with gzip.open(out/'control.csv.gz','wt',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    with gzip.open(out/'states.jsonl.gz','wt',encoding='utf8',newline='\n') as f:
        f.write(''.join(json.dumps(x)+'\n' for x in states))
    save(out/'summary.json',result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    sources=list(HERE.glob('*.py'))+[HERE/'protocol.json',PREV/'run.py',PREV/'contracts.py',PREV/'protocol.json',
        previous.BASE/'run.py',previous.BASE/'protocol.json',previous.BASE/'scene.xml',
        HERE.parent/'vl01_phase_contracts/monitor.py',HERE.parent/'vl01_recovery_gate/gate.py']
    save(a.out/'manifest.json',dict(at=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),mujoco=mujoco.__version__,numpy=np.__version__,protocol=P,
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        dirtyBeforeRun=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        sources={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for x in sources}))
    results=[];hashes={}
    for condition in P['conditions']:
        out=a.out/condition;out.mkdir();result=simulate(condition,out);results.append(result)
        for name in ('control.csv.gz','states.jsonl.gz','summary.json'):hashes[(out/name).relative_to(a.out).as_posix()]=sha(out/name)
        print(json.dumps(result),flush=True)
    save(a.out/'summary.json',results);save(a.out/'sha256.json',hashes)
if __name__=='__main__':main()
