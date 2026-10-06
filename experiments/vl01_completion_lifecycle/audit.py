"""Independent recorded-evidence checks; does not import a controller or MuJoCo."""
import argparse,csv,gzip,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def inside(x,y,z,speed,contacts):
    names=set(contacts.split('|'))
    return all((abs(x-.24)<.045,abs(y-.12)<.045,abs(z-.026)<.006,0<=speed<.02,'bin_floor' in names,not names&{'left_pad','right_pad'}))
def audit(out):
    read=lambda n:json.loads((out/n).read_text('utf8'))
    manifest=read('manifest.json');p=manifest['protocol'];summaries=read('summary.json');hashes=read('sha256.json')
    expected={f'{c}/{n}' for c in p['conditions'] for n in ('control.csv.gz','states.jsonl.gz','summary.json')}
    assert set(hashes)==expected and len(summaries)==len(p['conditions'])
    assert {s['condition'] for s in summaries}==set(p['conditions'])
    for n,h in hashes.items():assert hashlib.sha256((out/n).read_bytes()).hexdigest()==h,n
    for n,h in manifest['sources'].items():assert hashlib.sha256((ROOT/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==h,n
    physics={};verified=[]
    for s in summaries:
        c=s['condition'];assert read(c+'/summary.json')==s
        with gzip.open(out/c/'control.csv.gz','rt',encoding='utf8') as f:rows=list(csv.DictReader(f))
        with gzip.open(out/c/'states.jsonl.gz','rt',encoding='utf8') as f:states=[json.loads(x) for x in f]
        assert len(rows)==6000 and len(states)==600
        for j,st in enumerate(states):
            assert st['tick']==1+j*10 and len(st['qpos'])==12 and len(st['qvel'])==11
            assert all(math.isfinite(v) for k in ('qpos','qvel','ctrl') for v in st[k])
            r=rows[st['tick']-1]
            for i,k in enumerate(('cube_x','cube_y','cube_z')):assert abs(st['qpos'][i]-float(r[k]))<1e-12
        history=[];last=None;first=None;state='NOT_READY';events=[];high=0.;was_valid=False
        def set_state(new,t,reason):
            nonlocal state
            if new!=state:events.append(dict(tick=t,from_state=state,to_state=new,reason=reason));state=new
        for i,r in enumerate(rows):
            t=i+1;assert int(r['tick'])==t and abs(float(r['time'])-t*.002)<1e-9
            high=max(high,float(r['cube_z']));packet=json.loads(r['received'])
            released=(t-1)*.002>=6.5;lifted=high>.1
            if not released or not lifted:history=[];set_state('NOT_READY',t,'prerequisite')
            else:
                fresh_new=packet is not None and (last is None or packet['capture_tick']>last) and 0<=t-packet['capture_tick']<30
                if not fresh_new and (last is None or t-last>=30):history=[];set_state('UNKNOWN',t,'no-fresh-evidence')
                if packet is not None:
                    capture=packet['capture_tick'];assert 0<=capture<=t
                    if last is None or capture>last:
                        if last is None or capture-last>10:history=[]
                        last=capture
                        if t-capture>=30:history=[];set_state('UNKNOWN',t,'stale')
                        elif not inside(packet['x'],packet['y'],packet['z'],packet['speed'],packet['contacts']):
                            history=[];set_state('INVALID',t,'fresh-violation')
                        else:
                            history.append(capture)
                            if history[-1]-history[0]>=125:
                                set_state('VALID',t,'sustained-evidence')
                                if first is None:first=t
                            else:set_state('VERIFYING',t,'collecting-evidence')
            assert r['state']==state,(c,t,r['state'],state)
            assert r['completed_at']==('' if first is None else str(first))
            if first is not None:assert int(r['latched'])==first
            expected_force=1. if c in ('push','false-good-after-push') and 4000<=i<4040 else 0.
            assert float(r['force_x'])==expected_force
            # Check the received synthetic intervention independently of the observer.
            if i%10!=0:assert packet is None
            elif c=='boundary-gap' and t in (4001,4011):assert packet is None
            elif c=='silence' and 4000<=i<4200:assert packet is None
            elif c=='stale-replay' and 4000<=i<4200:assert packet['capture_tick']==3991
            else:
                assert packet['capture_tick']==t
                for key,col in [('x','cube_x'),('y','cube_y'),('z','cube_z'),('speed','cube_speed')]:
                    actual=float(r[col]);value=packet[key]
                    if c=='false-bad' and t==4001 and key=='x':assert value==.4
                    elif c=='false-good-after-push' and t==4101:assert value=={'x':.24,'y':.12,'z':.026,'speed':0}[key]
                    else:assert abs(value-actual)<1e-12
        assert events==s['events'] and first==s['completed_at']==s['latched'] and state==s['final_state']
        placed=high>.1 and not s['warnings'] and all(abs(float(r['cube_x'])-.24)<.045 and abs(float(r['cube_y'])-.12)<.045 and abs(float(r['cube_z'])-.026)<.006 and float(r['cube_speed'])<.02 and not int(r['finger_contact']) for r in rows if float(r['time'])>=11.5)
        assert placed==s['final_placement']
        physics[c]=states;verified.append(dict(condition=c,first=first,final=state,placement=placed))
    # Observation-only interventions must not change the actual trajectory.
    for c in ('silence','stale-replay','false-bad','boundary-gap'):assert physics[c]==physics['clean'],c
    assert physics['push']==physics['false-good-after-push']
    return dict(valid=True,episodes=len(summaries),raw_files=len(hashes),same_physics_pairs=5,checks=verified)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();result=audit(a.out)
    (a.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n');print(json.dumps(result))
