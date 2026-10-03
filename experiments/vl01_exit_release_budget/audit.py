"""Independent arithmetic/record audit: no MuJoCo or controller imports."""
import csv,gzip,hashlib,itertools,json,math,sys
from pathlib import Path

def require(ok,message):
    if not ok:raise ValueError(message)
def read(p):return json.loads(p.read_text(encoding='utf8'))
def close(a,b):return abs(float(a)-float(b))<1e-9
def support(row):
    names=set(row['contacts'].split('|'))
    return (abs(float(row['cube_x'])-.24)<.045 and abs(float(row['cube_y'])-.12)<.045
        and abs(float(row['cube_z'])-.026)<.006 and float(row['cube_speed'])<.02
        and not {'left_pad','right_pad'}&names)
def release_good(p):
    return (abs(p['x']-.24)<.045 and abs(p['y']-.12)<.045 and abs(p['z']-.026)<.006
            and p['speed']<.02 and 'bin_floor' in p['contacts'].split('|')
            and not {'left_pad','right_pad'}&set(p['contacts'].split('|')))
def audit(root):
    root=Path(root);m=read(root/'manifest.json');p=m['protocol'];repo=Path(__file__).resolve().parents[2]
    for name,want in m['sources'].items():require(hashlib.sha256((repo/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==want,'source '+name)
    hashes=read(root/'sha256.json')
    for name,want in hashes.items():require(hashlib.sha256((root/name).read_bytes()).hexdigest()==want,'hash '+name)
    results=read(root/'summary.json');expected={(s,c,k) for s,spec in p['studies'].items() for c in spec['conditions'] for k in spec['policies']}
    require({(r['study'],r['condition'],r['policy']) for r in results}==expected and len(results)==len(expected),'matrix')
    prefixes={};checks=[]
    for result in results:
        study,condition,policy=[result[k] for k in ('study','condition','policy')];cell=root/f'{study}--{condition}--{policy}'
        require(result==read(cell/'summary.json'),'summary copy')
        with gzip.open(cell/'control.csv.gz','rt',encoding='utf8') as f:rows=list(csv.DictReader(f))
        with gzip.open(cell/'states.jsonl.gz','rt',encoding='utf8') as f:states=[json.loads(line) for line in f]
        require(len(rows)==6000 and len(states)==600,'record count')
        maxz=max(float(r['cube_z']) for r in rows)
        require(close(maxz,result['max_cube_z']),'maximum lift')
        final=[r for r in rows if float(r['time'])>=11.5]
        require(result['placement']==bool(maxz>.1 and all(support(r) for r in final) and not result['warnings']),'placement')
        for index,row in enumerate(rows):
            tick=index+1;require(int(row['tick'])==tick and close(row['time'],tick*.002),'clock')
            require(int(row['finger_contact'])==int(bool({'left_pad','right_pad'}&set(row['contacts'].split('|')))),'contact projection')
            packets=json.loads(row['received'])
            require(len(packets)<=1 and (not packets or index%10==0),'cadence')
            for packet in packets:
                require(packet['seq']==index//10 and packet['capture_tick']==tick,'packet timestamp')
                if condition=='false-good-report' and tick==3301:
                    require(packet['contacts']=='bin_floor' and packet['z']==.026 and packet['speed']==0,'specified forged observation')
                else:
                    require(packet['contacts']==row['contacts'] and close(packet['z'],row['cube_z']) and close(packet['speed'],row['cube_speed']),'observation projection')
        for state in states:
            row=rows[state['tick']-1];q,v,ctrl=state['qpos'],state['qvel'],state['ctrl']
            require(all(close(q[i],row[k]) for i,k in enumerate(('cube_x','cube_y','cube_z'))),'qpos cube')
            require(close(math.sqrt(sum(x*x for x in v[:3])),row['cube_speed']),'qvel speed')
            require(all(close(ctrl[i],value) for i,value in enumerate([float(row['target_x']),float(row['target_y']),float(row['target_z'])-.16,float(row['applied_grip']),float(row['applied_grip'])])),'actuator trace')
            require(all(close(q[i],float(row[k])-offset) for i,k,offset in ((7,'hand_x',0),(8,'hand_y',0),(9,'hand_z',.16))),'hand coordinates')
        events=result['events']
        if study=='E8':
            first=None;latest=None;bad=None;previous=None
            for row in rows:
                tick=int(row['tick']);phase=row['phase'];fresh=json.loads(row['received'])
                if fresh:latest=fresh[0]
                if phase!=previous:bad=None
                previous=phase
                if first is not None or phase not in ('transfer','lower'):continue
                reason='stale' if latest is None or tick-latest['capture_tick']>=30 else None
                for packet in fresh:
                    good={'left_pad','right_pad'}<=set(packet['contacts'].split('|')) and packet['grasp_error']<.05 and (phase=='lower' or packet['cube_z']>.12)
                    if good:bad=None
                    elif bad is None:bad=packet['capture_tick']
                    elif packet['capture_tick']-bad>=20:reason=reason or 'grasp'
                if reason:first=dict(type='stop',tick=tick,phase=phase,reason=reason,age_ticks=None if latest is None else tick-latest['capture_tick'],bad_since=bad)
            require(events==([] if first is None else [first]),'E8 decisions')
            if first:
                stop=first['tick'];held=rows[stop-1]
                for row in rows[stop:]:
                    tick=int(row['tick']);require(row['phase']=='exit','exit phase')
                    for axis in ('x','y'):require(close(row['target_'+axis],held['target_'+axis]),'exit XY')
                    alpha=min(1,max(0,((tick-stop)*.002-.2)/.6))
                    z=float(held['target_z'])+(.1*alpha*alpha*(3-2*alpha) if policy=='open-retreat' else 0)
                    require(close(row['target_z'],z),'exit height')
                    require(close(row['target_grip'],held['target_grip'] if policy=='hold' else 0),'exit grip')
            prefixes.setdefault(condition,[]).append((policy,rows,states,result['first_stop']))
        if study=='E9':
            last=start=single=window=None;lift=False
            for row in rows:
                now=int(row['tick']);lift=lift or float(row['cube_z'])>.1
                if last is not None and now-last>=30:start=None
                packets=json.loads(row['received'])
                if packets:
                    packet=packets[0];capture=packet['capture_tick'];gap=last is None or capture-last>10;last=capture
                    if now<3251 or not lift or not release_good(packet):start=None
                    else:
                        if single is None:single=now
                        if gap or start is None:start=capture
                        if window is None and capture-start>=125:window=now
                require(row['single']==('' if single is None else str(single)),'single completion')
                require(row['window']==('' if window is None else str(window)),'window completion')
            require(result['single_completion']==single and result['window_completion']==window,'completion summary')
        if study=='E10':
            resumes=[e for e in events if e['type']=='resume'];require(len(resumes)==result['resumes'],'resume count')
            require(policy=='unlimited' or len(resumes)<=2,'resume budget')
            hold=None
            for event in events:
                if event['type']=='hold':hold=event['tick']
                if event['type']=='resume':
                    require(hold is not None and event['tick']-hold<400,'deadline')
                    require(event['window_start']>hold and event['window_end']-event['window_start']>=50,'fresh evidence window')
                    require(event['age_ticks']<30 and event['good'],'resume freshness')
                    require(policy!='budget-two-cooldown' or event['tick']-hold>=200,'cooldown')
                    for tick in range(event['window_start'],event['window_end']+1,10):
                        packet=json.loads(rows[tick-1]['received'])[0]
                        require({'left_pad','right_pad'}<=set(packet['contacts'].split('|')) and packet['cube_z']>.12 and packet['grasp_error']<.05,'window physical evidence')
            if result['state']=='aborted':require(events[-1]['type']=='abort','abort event')
        checks.append(dict(study=study,condition=condition,policy=policy,rows=len(rows),states=len(states),placement=result['placement']))
    pairs=0
    for condition,cells in prefixes.items():
        for a,b in itertools.combinations(cells,2):
            end=min(a[3] or 6000,b[3] or 6000)
            aa={s['tick']:s for s in a[2] if s['tick']<=end};bb={s['tick']:s for s in b[2] if s['tick']<=end}
            require(aa==bb,'predecision state prefix '+condition);pairs+=1
    return dict(valid=True,episodes=len(results),raw_files=len(hashes),source_files=len(m['sources']),e8_prefix_pairs=pairs,checks=checks,
                limitations='Checks recorded physics projections, E8 decisions/exit targets, E9 completion and E10 resume evidence/budgets. Does not recompute contact forces or establish hardware safety.')
if __name__=='__main__':
    result=audit(sys.argv[1]);(Path(sys.argv[1])/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
