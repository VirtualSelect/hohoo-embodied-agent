import csv,gzip
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path(__file__).resolve().parents[2]/'evidence/qualified-completion-20261005';states=['NOT_READY','UNKNOWN','VERIFYING','VALID','INVALID','ABORTED'];fig,axes=plt.subplots(1,2,figsize=(15,6),dpi=100);fig.set_facecolor('#faf9f6')
for ax,name in zip(axes,['lower-drop','post-release-push']):
 with gzip.open(out/name/'control.csv.gz','rt') as f:r=[v for v in csv.DictReader(f) if float(v['time'])>=5.5]
 for key,color,offset in [('current_physical','#b78061',-.06),('qualified','#56836d',.06)]:ax.step([float(v['time']) for v in r],[states.index(v[key])+offset for v in r],where='post',color=color,label=key,linewidth=2)
 ax.set_facecolor('#faf9f6');ax.set_yticks(range(6),states);ax.set_xlabel('Simulation time (s)');ax.set_title(name);ax.legend(frameon=False);ax.spines[['top','right']].set_visible(False)
fig.suptitle('E14 / Physical placement, execution authority and current validity are different facts',fontsize=16);fig.tight_layout();fig.savefig(out/'qualified-completion.png');plt.close(fig)
