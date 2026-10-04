"""Recompute physical acceptance and event predicates from archived packets."""
import argparse,csv,gzip,hashlib,itertools,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def read(p):
 with gzip.open(p,'rt',encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def audit(out):
 m=json.loads((out/'manifest.json').read_text('utf8'));P=m['protocol'];results=json.loads((out/'summary.json').read_text('utf8'));hashes=json.loads((out/'sha256.json').read_text('utf8'));allrows={}
 for p,h in m['sources'].items():assert hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,p
 for p,h in hashes.items():assert hashlib.sha256((out/p).read_bytes()).hexdigest()==h,p
 assert len(results)==18 and len(hashes)==54 and {(s['condition'],s['policy']) for s in results}==set(itertools.product(P['conditions'],P['policies']))
 c=json.loads((ROOT/'experiments/vl01_pick_place/protocol.json').read_text('utf8'))['success']
 for s in results:
  key=s['condition']+'--'+s['policy'];d=out/key;rows=read(d/'control.csv.gz');allrows[key]=rows;assert len(rows)==6000 and s==json.loads((d/'summary.json').read_text('utf8'))
  packets={}
  for i,r in enumerate(rows):
   tick=i+1;t=i*.002;assert int(r['tick'])==tick and abs(float(r['time'])-tick*.002)<1e-8
   bounds=P['faults'].get(s['condition']);fault=bounds is not None and bounds[0]-1e-10<=t<bounds[1]-1e-10
   received=json.loads(r['received']);assert bool(received)==(i%10==0 and not(fault and s['condition']!='lower-drop'))
   assert int(r['actuator_fault'])==int(fault and s['condition']=='lower-drop')
   if received:
    p=received[0];packets[tick]=p;assert p['seq']==i//10 and p['capture_tick']==tick and p['contacts']==r['contacts']
    assert p['cube_z']==float(r['cube_z'])
    error=np.linalg.norm([float(r['cube_'+a])-float(r['hand_'+a]) for a in 'xyz']);assert abs(error-p['grasp_error'])<1e-12
  maxz=max(float(r['cube_z']) for r in rows);tail=[r for r in rows if float(r['time'])>=11.5]
  placed=maxz>c['cube_lift_height_m'] and all(abs(float(r['cube_x'])-c['bin_center_xy_m'][0])<c['max_abs_xy_error_m'] and abs(float(r['cube_y'])-c['bin_center_xy_m'][1])<c['max_abs_xy_error_m'] and abs(float(r['cube_z'])-c['cube_rest_z_m'])<c['max_abs_z_error_m'] and float(r['cube_speed'])<c['max_linear_speed_m_s'] and not int(r['finger_contact']) for r in tail)
  assert bool(placed)==s['placement'] and not s['warnings'] and maxz==s['max_cube_z']
  with gzip.open(d/'states.jsonl.gz','rt') as f:states=[json.loads(line) for line in f]
  assert len(states)==600
  for state in states:
   r=rows[state['tick']-1];assert np.isfinite(state['qpos']+state['qvel']+state['ctrl']).all()
   np.testing.assert_allclose(state['qpos'][:3],[float(r['cube_'+a]) for a in 'xyz'],atol=1e-12,rtol=0)
   np.testing.assert_allclose(state['ctrl'],[float(r['target_x']),float(r['target_y']),float(r['target_z'])-.16,float(r['target_grip']),float(r['target_grip'])],atol=1e-12,rtol=0)
  hold=None;resumes=0
  for e in s['events']:
   tick=e['tick'];phase=e['interrupted_phase'];assert phase in ('transfer','lower')
   if e['type']=='hold':
    assert hold is None;hold=tick;assert rows[tick-1]['scheduled_phase']==phase
    if e['reason']=='stale':assert tick-max(t for t in packets if t<=tick)>=30
   elif e['type']=='resume':
    assert hold is not None and 200<=tick-hold<400 and resumes<2
    window=[p for t,p in packets.items() if e['window_start']<=t<=e['window_end']];assert len(window)>=6
    assert e['window_start']>hold and e['window_end']-e['window_start']>=50 and tick-e['window_end']<30
    for a,b in zip(window,window[1:]):assert b['capture_tick']-a['capture_tick']==10
    for p in window:assert {'left_pad','right_pad'}<=set(p['contacts'].split('|')) and p['grasp_error']<.05 and (p['cube_z']>.12 if phase=='transfer' or s['policy']=='reuse-transfer' else True)
    assert rows[tick]['scheduled_phase']==phase;resumes+=1;hold=None
   else:
    assert hold is not None and (tick-hold>=400 if e['reason']=='revalidation_deadline' else resumes>=2)
    assert all(r['state_after']=='aborted' for r in rows[tick-1:])
  assert resumes==s['resumes']
 # Policies must share physical controls and truth until their first decision diverges.
 pairs=0
 for cond in P['conditions']:
  for a,b in itertools.combinations(P['policies'],2):
   aa=allrows[cond+'--'+a];bb=allrows[cond+'--'+b]
   first=next((i for i,(x,y) in enumerate(zip(aa,bb)) if x['state_after']!=y['state_after']),5999)
   fields=['target_'+v for v in ('x','y','z','grip')]+['cube_'+v for v in 'xyz']+['contacts']
   assert all(all(x[k]==y[k] for k in fields) for x,y in zip(aa[:first+1],bb[:first+1]));pairs+=1
 return dict(valid=True,rollouts=18,physics_rows=108000,states=10800,raw_files=54,prefix_pairs=pairs,placement=sum(s['placement'] for s in results))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('out',type=Path);out=p.parse_args().out;r=audit(out);(out/'audit.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf8');print(r)
