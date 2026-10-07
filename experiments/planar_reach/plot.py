import argparse,csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);out=p.parse_args().directory;rs=json.loads((out/'results.json').read_text())
for family in ['gain','path','observation']:
 fig,ax=plt.subplots(figsize=(8,4))
 for r in rs:
  c=r['config']
  if c['family']!=family or c['seed']!=7:continue
  rows=list(csv.DictReader((out/r['file']).open()));x=np.array([float(a['x']) for a in rows]);y=np.array([float(a['y']) for a in rows]);t=np.array([float(a['t']) for a in rows])
  if family=='gain':ax.plot(t,x,label=f"m={c['mass']}, kd={c['kd']}")
  elif family=='path':ax.plot(x,y,label=f"wall={c['wall']}, {c['route']}")
  else:ax.plot(t,np.hypot(x-.6,y),label=f"lag={c['delay']}, noise={c['noise']}, {c['mode']}")
 ax.set(xlabel='x (m)' if family=='path' else 'time (s)',ylabel='y (m)' if family=='path' else 'position / error (m)',title=f'MuJoCo planar reach: {family} (recorded trajectories)');ax.legend(fontsize=7,ncol=2);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(out/f'{family}.svg');plt.close(fig)
