import argparse,csv,gzip,hashlib,itertools,json,pathlib,platform,subprocess,sys
from collections import deque
import mujoco
import numpy as np
from estimator import VelocityEstimator
H=pathlib.Path(__file__).resolve().parent;ROOT=H.parents[1]
P=json.loads((H/'protocol.json').read_text())

def episode(config, destination):
    m=mujoco.MjModel.from_xml_path(str(H/'scene.xml'))
    wall=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,'wall');m.geom_contype[wall]=0;m.geom_conaffinity[wall]=0;m.geom_rgba[wall,3]=0
    d=mujoco.MjData(m);mujoco.mj_forward(m,d)
    assert abs(m.opt.timestep-P['timestep'])<1e-12
    dt=P['timestep'];control=round(P['control_period']/dt);latency=round(config['delay']/dt)
    rng=np.random.default_rng(config['seed']);queue=deque();observed=None;capture=-1.;estimated=np.zeros(2);captured_v=np.zeros(2)
    estimator=VelocityEstimator(config['mode'] if config['mode']!='oracle' else 'difference',P['ema_tau_s'])
    force=np.zeros(2);raw_force=np.zeros(2);trajectory=[];velocity_errors=[]
    with gzip.open(destination,'wt',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['t','x','y','vx','vy','fx','fy','raw_fx','raw_fy','control_tick','capture_t','observed_x','observed_y','estimated_vx','estimated_vy','captured_vx','captured_vy','saturated','contact'])
        for tick in range(round(P['duration']/dt)):
            decision=tick*dt
            if tick%control==0:
                queue.append((tick+latency,decision,d.qpos[:2].copy()+rng.normal(0,config['noise'],2),d.qvel[:2].copy()))
                while queue and queue[0][0]<=tick:
                    _,capture,observed,captured_v=queue.popleft()
                    estimated=captured_v.copy() if config['mode']=='oracle' else estimator.update(capture,observed)
                    velocity_errors.append(float(np.sum((estimated-captured_v)**2)))
                raw_force=P['kp']*(np.array(P['goal'])-observed)-P['kd']*estimated if observed is not None else np.zeros(2)
                force=np.clip(raw_force,-P['force_axis_limit_N'],P['force_axis_limit_N'])
            d.ctrl[:]=force;mujoco.mj_step(m,d)
            row=[(tick+1)*dt,*d.qpos[:2],*d.qvel[:2],*force,*raw_force,int(tick%control==0),capture,*(observed if observed is not None else [0,0]),*estimated,*captured_v,int(np.any(np.abs(raw_force)>P['force_axis_limit_N'])),int(d.ncon>0)]
            writer.writerow(row);trajectory.append(row)
    a=np.array(trajectory);errors=np.linalg.norm(a[:,1:3]-P['goal'],axis=1);speed=np.linalg.norm(a[:,3:5],axis=1)
    tail=a[:,0]>P['duration']-P['success']['last_seconds']+1e-9
    return dict(**config,success=bool(np.all((errors[tail]<P['success']['distance_m'])&(speed[tail]<P['success']['speed_m_s']))),final_error_m=float(errors[-1]),tail_rms_m=float(np.sqrt(np.mean(errors[tail]**2))),peak_overshoot_m=float(max(0,a[:,1].max()-P['goal'][0])),velocity_estimation_rmse_m_s=float(np.sqrt(np.mean(velocity_errors))),saturated_steps=int(a[:,17].sum()),contact_steps=int(a[:,18].sum()),rows=len(a),trace=destination.name)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=pathlib.Path,default=ROOT/'evidence'/'planar-velocity-20261009');args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,(delay,noise,mode,seed) in enumerate(itertools.product(P['delays'],P['position_noise_std_m'],P['estimators'],P['seeds'])):
        rows.append(episode(dict(delay=delay,noise=noise,mode=mode,seed=seed),args.out/f'{i:02d}.csv.gz'))
    (args.out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    sources={p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in H.iterdir() if p.suffix in ('.py','.xml','.json')}
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.out.iterdir()) if p.name!='manifest.json'}
    manifest=dict(protocol=P,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),python=sys.version,platform=platform.platform(),mujoco=mujoco.__version__,numpy=np.__version__,sources=sources,files=files)
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(episodes=len(rows),rows=sum(r['rows'] for r in rows),success=sum(r['success'] for r in rows))))
if __name__=='__main__':main()
