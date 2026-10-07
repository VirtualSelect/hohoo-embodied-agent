"""Three paired teaching studies; MuJoCo integrates every state, no teleportation."""
import argparse,csv,hashlib,itertools,json,platform,subprocess
from pathlib import Path
import mujoco
import numpy as np
H=Path(__file__).resolve().parent; ROOT=H.parents[1]
P=json.loads((H/'protocol.json').read_text())
def sha(p): return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def configs():
 for mass,kd in itertools.product([1,2],[0,18,36]):
  yield dict(family='gain',mass=mass,kd=kd,route='direct',wall=0,delay=0,noise=0,mode='hold',seed=7)
 for wall,route in itertools.product([.04,.09],['direct','corner','clearance']):
  yield dict(family='path',mass=1,kd=18,route=route,wall=wall,delay=0,noise=0,mode='hold',seed=7)
 for delay,noise,mode,seed in itertools.product([0,.08],[0,.01],['hold','predict'],P['seeds']):
  yield dict(family='observation',mass=1,kd=18,route='direct',wall=0,delay=delay,noise=noise,mode=mode,seed=seed)
def model_for(c):
 model=mujoco.MjModel.from_xml_path(str(H/'scene.xml'))
 model.body_mass[model.body('mover').id]=c['mass']
 model.body_inertia[model.body('mover').id]*=c['mass']
 wall=model.geom('wall').id
 if not c['wall']: model.geom_contype[wall]=0;model.geom_conaffinity[wall]=0;model.geom_rgba[wall,3]=0
 else: model.geom_size[wall,1]=c['wall']
 data=mujoco.MjData(model);mujoco.mj_setConst(model,data);mujoco.mj_forward(model,data)
 return model,data
def metrics(rows):
 x=np.array([[r['x'],r['y']] for r in rows]);v=np.array([[r['vx'],r['vy']] for r in rows]);t=np.array([r['t'] for r in rows])
 err=np.linalg.norm(x-np.array(P['goal']),axis=1);speed=np.linalg.norm(v,axis=1);tail=t>=P['duration']-P['success']['last_seconds']-1e-9
 ok=(err<P['success']['distance_m'])&(speed<P['success']['speed_m_s'])
 return dict(success=bool(ok[tail].all()),final_error_m=float(err[-1]),peak_overshoot_m=float(max(0,x[:,0].max()-.6)),rms_tail_error_m=float(np.sqrt(np.mean(err[tail]**2))),contact_steps=sum(r['contact']>0 for r in rows),saturated_steps=sum(r['saturated']>0 for r in rows),path_m=float(np.linalg.norm(np.diff(x,axis=0),axis=1).sum()))
def episode(c):
 m,d=model_for(c);rng=np.random.default_rng(c['seed']);rows=[];queue=[];sample=None;target=np.array(P['goal'],float)
 height=c['wall'] if c['route']=='corner' else c['wall']+.1
 waypoints=([np.array([.16,height]),np.array([.44,height]),target] if c['route']!='direct' else [target]);wp=0;measurement=np.zeros(2);force=np.zeros(2);sat=False
 for tick in range(round(P['duration']/P['dt'])):
  if tick%10==0:
   queue.append((tick,tick+round(c['delay']/P['dt']),d.qpos.copy()+rng.normal(0,c['noise'],2),d.qvel.copy()))
   while queue and queue[0][1]<=tick:sample=queue.pop(0)
   if sample is not None:
    capture,_,pos,vel=sample;measurement=pos.copy()
    if c['mode']=='predict':measurement+=vel*(tick-capture)*P['dt']
    if wp<len(waypoints)-1 and np.linalg.norm(measurement-waypoints[wp])<.015:wp+=1
    force=80*(waypoints[wp]-measurement)-c['kd']*vel
    sat=bool((np.abs(force)>5).any());force=np.clip(force,-5,5)
   else: force=np.zeros(2);sat=False
  d.ctrl[:]=force;mujoco.mj_step(m,d)
  rows.append(dict(t=float(d.time),x=float(d.qpos[0]),y=float(d.qpos[1]),vx=float(d.qvel[0]),vy=float(d.qvel[1]),fx=float(force[0]),fy=float(force[1]),observed_x=float(measurement[0]),observed_y=float(measurement[1]),capture_t=-1 if sample is None else sample[0]*P['dt'],waypoint=wp,contact=int(d.ncon),saturated=int(sat)))
 return rows
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);out=p.parse_args().out;out.mkdir(parents=True,exist_ok=False);results=[]
 for i,c in enumerate(configs()):
  rows=episode(c);name=f'{i:02d}-{c["family"]}.csv'
  with (out/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
  results.append(dict(id=i,file=name,config=c,**metrics(rows)))
 (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
 manifest=dict(python=platform.python_version(),mujoco=mujoco.__version__,numpy=np.__version__,platform=platform.platform(),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),protocol=P,sources={p.relative_to(ROOT).as_posix():sha(p) for p in H.iterdir() if p.suffix in ('.py','.json','.xml')},files={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
