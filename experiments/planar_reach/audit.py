"""Independent CSV recomputation, bounds checks and source/file verification."""
import argparse,csv,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);out=p.parse_args().directory;m=json.loads((out/'manifest.json').read_text());rs=json.loads((out/'results.json').read_text());assert len(rs)==36
 for name,value in m['sources'].items():assert sha(ROOT/name)==value,name
 for name,value in m['files'].items():assert sha(out/name)==value,name
 for r in rs:
  rows=[{k:float(v) for k,v in row.items()} for row in csv.DictReader((out/r['file']).open())];assert len(rows)==2000
  assert all(math.isfinite(v) for row in rows for v in row.values())
  assert all(abs(row['fx'])<=5 and abs(row['fy'])<=5 for row in rows)
  assert all(row['capture_t']<=row['t'] for row in rows)
  for i,row in enumerate(rows):assert abs(row['t']-(i+1)*.002)<1e-9
  tail=[row for row in rows if row['t']>=3.7-1e-9]
  errs=[math.hypot(row['x']-.6,row['y']) for row in rows]
  success=all(math.hypot(row['x']-.6,row['y'])<.015 and math.hypot(row['vx'],row['vy'])<.04 for row in tail)
  assert success==r['success'];assert abs(errs[-1]-r['final_error_m'])<1e-12
  assert sum(row['contact']>0 for row in rows)==r['contact_steps']
  assert abs(max(0,max(row['x'] for row in rows)-.6)-r['peak_overshoot_m'])<1e-12
  assert abs(math.sqrt(sum(math.hypot(row['x']-.6,row['y'])**2 for row in tail)/len(tail))-r['rms_tail_error_m'])<1e-12
 print(json.dumps({'episodes':len(rs),'rows':len(rs)*2000,'families':{f:{'episodes':sum(r['config']['family']==f for r in rs),'passed':sum(r['config']['family']==f and r['success'] for r in rs)} for f in ['gain','path','observation']},'verified':'source hashes, file hashes, timeline, force bounds, causal observations, completion, contact, overshoot, RMS'},indent=2))
if __name__=='__main__':main()
