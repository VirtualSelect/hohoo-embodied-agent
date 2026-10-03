import csv,gzip,itertools,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
HERE=Path(__file__).resolve().parent;out=HERE.parents[1]/'evidence/completion-lifecycle-20261003'
results=json.loads((out/'summary.json').read_text('utf8'))
colors={'NOT_READY':'#bbb8b2','UNKNOWN':'#8a9baa','INVALID':'#b78061','VERIFYING':'#c9b77e','VALID':'#56836d'}
fig,ax=plt.subplots(figsize=(15,6),dpi=100);fig.set_facecolor('#faf9f6');ax.set_facecolor('#faf9f6')
for y,result in enumerate(results):
 with gzip.open(out/result['condition']/'control.csv.gz','rt',encoding='utf8') as f:rows=[r for r in csv.DictReader(f) if 6.5<=float(r['time'])<=9]
 for state,items in itertools.groupby(rows,key=lambda r:r['state']):
  span=list(items);start=float(span[0]['time']);end=float(span[-1]['time'])+.002
  ax.broken_barh([(start,end-start)],(y-.32,.64),facecolors=colors[state])
ax.axvline(7.102,linestyle='--',color='#434b4b',linewidth=1);ax.axvline(8,linestyle=':',color='#434b4b',linewidth=1)
ax.set_yticks(range(len(results)),[r['condition'] for r in results]);ax.invert_yaxis();ax.set_xlim(6.5,9)
ax.set_xlabel('Simulation time (s)');ax.set_title('E11 / Historical completion at 7.102 s; current validity continues to change',fontsize=17,pad=17)
ax.legend(handles=[Patch(color=c,label=s) for s,c in colors.items() if s!='NOT_READY'],loc='upper center',bbox_to_anchor=(.5,-.13),ncol=4,frameon=False)
ax.spines[['top','right']].set_visible(False);fig.tight_layout();fig.savefig(out/'completion-lifecycle.png');plt.close(fig)
