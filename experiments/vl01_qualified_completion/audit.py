import csv,gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def audit(out):
 manifest=json.loads((out/'manifest.json').read_text('utf8'))
 if not manifest.get('sources'):raise ValueError('Missing source fingerprints')
 for name,h in manifest['sources'].items():
  source=(ROOT/name).resolve()
  if not source.is_relative_to(ROOT) or not source.is_file():raise ValueError('Invalid source path: '+name)
  if hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=h:raise ValueError('Source mismatch; checkout evidence revision: '+name)
 for name,h in json.loads((out/'sha256.json').read_text('utf8')).items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==h
 summaries=json.loads((out/'summary.json').read_text('utf8'));assert len(summaries)==8;total=states=0;findings=[]
 for s in summaries:
  with gzip.open(out/s['condition']/'control.csv.gz','rt',encoding='utf8') as f:rows=list(csv.DictReader(f))
  with gzip.open(out/s['condition']/'states.jsonl.gz','rt',encoding='utf8') as f:frames=[json.loads(l) for l in f]
  assert len(rows)==6000 and len(frames)==600;total+=len(rows);states+=len(frames)
  observers={k:dict(last=None,start=None,state='NOT_READY',first=None) for k in ['current_physical','qualified']};latched=False;release=False;release_tick=None;abort=False;lift=False
  for r in rows:
   tick=int(r['tick']);packets=json.loads(r['received']);p=packets[0] if packets else None
   if r['phase']=='release' and float(r['target_grip'])<.005:
    if not release:release_tick=tick
    release=True
   abort=abort or r['state_after']=='aborted'
   if p and tick-p['capture_tick']<30 and p['cube_z']>.1:lift=True
   assert bool(int(r['release_intent']))==release and bool(int(r['observed_lift']))==lift
   for name,o in observers.items():
    if name=='qualified' and abort:o['state']='ABORTED';o['start']=None
    elif not lift or (name=='qualified' and not release):o['state']='NOT_READY';o['start']=None
    else:
     eligible=p and (name!='qualified' or p['capture_tick']>=release_tick)
     fresh_new=eligible and (o['last'] is None or p['capture_tick']>o['last']) and 0<=tick-p['capture_tick']<30
     if not fresh_new and (o['last'] is None or tick-o['last']>=30):o['state']='UNKNOWN';o['start']=None
     if eligible and (o['last'] is None or p['capture_tick']>o['last']):
      cap=p['capture_tick'];gap=o['last'] is None or cap-o['last']>10;o['last']=cap
      names=set(p['contacts'].split('|'));good=abs(p['x']-.24)<.045 and abs(p['y']-.12)<.045 and abs(p['z']-.026)<.006 and 0<=p['speed']<.02 and 'bin_floor' in names and not names&{'left_pad','right_pad'}
      if tick-cap>=30:o['state']='UNKNOWN';o['start']=None
      elif not good:o['state']='INVALID';o['start']=None
      else:
       if gap or o['start'] is None:o['start']=cap
       o['state']='VALID' if cap-o['start']>=125 else 'VERIFYING'
       if o['state']=='VALID' and o['first'] is None:o['first']=tick
    assert r[name]==o['state'],(s['condition'],tick,name,r[name],o)
   latched=latched or observers['current_physical']['state']=='VALID';assert bool(int(r['latched_physical']))==latched
  assert s['qualified']==observers['qualified']['state'] and s['qualified_completed_at']==observers['qualified']['first']
  assert s['physical_completed_at']==observers['current_physical']['first'] and s['latched_physical']==latched
  # Independent final physical acceptance, from raw physics rather than observer packets.
  tail=[r for r in rows if float(r['time'])>=11.5]
  physical=max(float(r['cube_z']) for r in rows)>.1 and all(abs(float(r['cube_x'])-.24)<.045 and abs(float(r['cube_y'])-.12)<.045 and abs(float(r['cube_z'])-.026)<.006 and float(r['cube_speed'])<.02 and 'bin_floor' in r['contacts'].split('|') and not {'left_pad','right_pad'}&set(r['contacts'].split('|')) for r in tail) and not s['warnings']
  assert bool(physical)==s['placement']
  findings.append({k:s[k] for k in ['condition','placement','state','latched_physical','current_physical','qualified','physical_completed_at','qualified_completed_at']})
 return dict(rollouts=8,observer_readouts=24,control_rows=total,replay_states=states,findings=findings)
if __name__=='__main__':
 out=Path(sys.argv[1]);a=audit(out);(out/'audit.json').write_text(json.dumps(a,indent=2)+'\n',encoding='utf8');print(json.dumps(a,indent=2))
