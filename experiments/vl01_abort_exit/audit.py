"""Recompute outcomes, fault schedules and counterfactual prefix identity from logs."""
import argparse,csv,gzip,hashlib,itertools,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def read_rows(path):
    with gzip.open(path,'rt',encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def audit(out):
    m=json.loads((out/'manifest.json').read_text());sums=json.loads((out/'summary.json').read_text());hashes=json.loads((out/'sha256.json').read_text());allrows={}
    for p,h in m['sources'].items():assert hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,p
    for p,h in hashes.items():assert hashlib.sha256((out/p).read_bytes()).hexdigest()==h,p
    assert len(sums)==12 and len(hashes)==36
    assert {(s['condition'],s['policy']) for s in sums}==set(itertools.product(m['protocol']['conditions'],m['protocol']['policies']))
    c=json.loads((ROOT/'experiments/vl01_pick_place/protocol.json').read_text())['success']
    for s in sums:
        key=s['condition']+'--'+s['policy'];d=out/key;assert s==json.loads((d/'summary.json').read_text());rows=read_rows(d/'control.csv.gz');assert len(rows)==6000;allrows[key]=rows
        with gzip.open(d/'states.jsonl.gz','rt') as f:states=[json.loads(x) for x in f]
        assert len(states)==600
        for v in states:
            row=rows[v['tick']-1];assert np.isfinite(v['qpos']+v['qvel']+v['ctrl']).all()
            np.testing.assert_allclose(v['qpos'][:3],[float(row['cube_'+a]) for a in 'xyz'],rtol=0,atol=1e-12)
            np.testing.assert_allclose(v['ctrl'],[float(row['target_x']),float(row['target_y']),float(row['target_z'])-.16,float(row['target_grip']),float(row['target_grip'])],rtol=0,atol=1e-12)
        for i,r in enumerate(rows):
            tick=i+1;assert int(r['tick'])==tick and abs(float(r['time'])-tick*.002)<1e-8
            gap=(2150<=i<3470 and (i-2150)%220<70) if s['condition']=='repeated-gap' else i>=2150 if s['condition']=='permanent-gap' else 2800<=i<2920 if s['condition']=='lower-silence' else False
            packets=json.loads(r['received']);assert bool(packets)==(i%10==0 and not gap)
            if packets:
                p=packets[0];assert p['capture_tick']==tick and p['seq']==i//10 and p['contacts']==r['contacts']
                for axis in 'xyz':assert p[axis]==float(r['cube_'+axis])
            if s['abort_tick'] is not None and tick>s['abort_tick']:
                held=rows[s['abort_tick']-1];dt=(tick-s['abort_tick'])*.002;a=max(0,min(1,(dt-.2)/.6))
                z=float(held['target_z'])+(.1*a*a*(3-2*a) if s['policy']=='open-retreat' else 0)
                assert abs(float(r['target_z'])-z)<1e-12 and r['state_after']=='aborted'
                assert float(r['target_grip'])==(float(held['target_grip']) if s['policy']=='hold' else 0)
                for axis in 'xy':assert r['target_'+axis]==held['target_'+axis]
        maxz=max(float(r['cube_z']) for r in rows);tail=[r for r in rows if float(r['time'])>=11.5]
        placed=maxz>c['cube_lift_height_m'] and all(abs(float(r['cube_x'])-c['bin_center_xy_m'][0])<c['max_abs_xy_error_m'] and abs(float(r['cube_y'])-c['bin_center_xy_m'][1])<c['max_abs_xy_error_m'] and abs(float(r['cube_z'])-c['cube_rest_z_m'])<c['max_abs_z_error_m'] and float(r['cube_speed'])<c['max_linear_speed_m_s'] and not int(r['finger_contact']) for r in tail)
        assert placed==s['placement'] and not s['warnings'] and maxz==s['max_cube_z']
        assert float(rows[-1]['cube_z'])==s['final_cube_z'] and rows[-1]['contacts']==s['final_contacts']
        # Absolute schedule: last pre-gap packet tick2141, stale at2171.
        if s['condition']=='permanent-gap':assert [(e['type'],e['tick']) for e in s['events']]==[('hold',2171),('abort',2571)] and s['resumes']==0
        elif s['condition']=='repeated-gap':
            assert [e['type'] for e in s['events']]==['hold','resume','hold','resume','hold','abort']
            assert s['resumes']==2 and s['events'][-1]['reason']=='budget'
            for e in s['events']:
                if e['type']=='resume':assert e['window_end']-e['window_start']>=50 and e['age_ticks']<30
        else:assert s['events']==[] and s['abort_tick'] is None
    pairs=0
    for condition in m['protocol']['conditions']:
        for a,b in itertools.combinations(m['protocol']['policies'],2):
            one=next(s for s in sums if s['condition']==condition and s['policy']==a);limit=one['abort_tick'] or 6000
            assert allrows[condition+'--'+a][:limit]==allrows[condition+'--'+b][:limit];pairs+=1
    return dict(valid=True,rollouts=12,raw_files=36,prefix_pairs=pairs,physics_rows=72000,states=7200,placement=sum(s['placement'] for s in sums))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);out=p.parse_args().out;r=audit(out);(out/'audit.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
