"""Read saved trajectories; independently replay estimator/control and acceptance."""
import csv,gzip,hashlib,json,math,pathlib,sys
import numpy as np
H=pathlib.Path(__file__).resolve().parent;ROOT=H.parents[1]
D=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'evidence'/'planar-velocity-20261009'
M=json.loads((D/'manifest.json').read_text());P=M['protocol'];results=json.loads((D/'results.json').read_text())
for name,sha in M['sources'].items():assert hashlib.sha256((H/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==sha,name
for name,sha in M['files'].items():assert hashlib.sha256((D/name).read_bytes()).hexdigest()==sha,name
assert len(results)==54 and len({(r['delay'],r['noise'],r['mode'],r['seed']) for r in results})==54
for result in results:
    with gzip.open(D/result['trace'],'rt') as f:a=np.array([[float(v) for v in row] for row in list(csv.reader(f))[1:]])
    assert len(a)==result['rows']==2000
    np.testing.assert_allclose(a[:,0],np.arange(1,2001)*P['timestep'],atol=1e-12)
    err=np.linalg.norm(a[:,1:3]-P['goal'],axis=1);speed=np.linalg.norm(a[:,3:5],axis=1);tail=a[:,0]>3.7+1e-9
    assert bool(np.all((err[tail]<.015)&(speed[tail]<.04)))==result['success']
    for actual,key in [(err[-1],'final_error_m'),(np.sqrt(np.mean(err[tail]**2)),'tail_rms_m'),(max(0,a[:,1].max()-.6),'peak_overshoot_m')]:assert np.isclose(actual,result[key],atol=1e-12),key
    last=None;velocity=np.zeros(2);errors=[]
    for row in a[a[:,9]==1]:
        decision=row[0]-P['timestep'];capture=row[10];position=row[11:13]
        assert capture<=decision+1e-9
        if capture>=0:
            assert abs(decision-capture-result['delay'])<1e-9
            if result['mode']=='oracle':velocity=row[15:17]
            elif last is not None:
                delta=capture-last[0];assert delta>0
                raw=(position-last[1])/delta;alpha=1 if result['mode']=='difference' else 1-math.exp(-delta/P['ema_tau_s'])
                velocity=velocity*(1-alpha)+raw*alpha
            last=(capture,position.copy());errors.append(np.sum((velocity-row[15:17])**2))
            raw_force=P['kp']*(P['goal']-position)-P['kd']*velocity
        else:raw_force=np.zeros(2)
        np.testing.assert_allclose(row[13:15],velocity,atol=1e-11)
        np.testing.assert_allclose(row[7:9],raw_force,atol=1e-10)
    np.testing.assert_allclose(a[:,5:7],np.clip(a[:,7:9],-5,5),atol=1e-12)
    assert int(np.any(abs(a[:,7:9])>5,axis=1).sum())==result['saturated_steps']
    assert int(a[:,18].sum())==result['contact_steps']==0
    assert np.isclose(np.sqrt(np.mean(errors)),result['velocity_estimation_rmse_m_s'],atol=1e-11)
print('PASS: 54 episodes / 108000 steps, physical acceptance, causal sample age, velocity estimator, force and hashes')
