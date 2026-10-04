import csv,gzip,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path(__file__).resolve().parents[2]/'evidence/phase-recovery-20261004'
fig,axes=plt.subplots(1,2,figsize=(15,6),dpi=100);fig.set_facecolor('#faf9f6')
for ax,condition in zip(axes,('clean','lower-late-gap')):
 for policy,color,style in zip(('transfer-only','reuse-transfer','phase-aware'),('#899ab4','#b78061','#56836d'),('--','-','-')):
  with gzip.open(out/(condition+'--'+policy)/'control.csv.gz','rt') as f:r=[x for x in csv.DictReader(f) if 5.5<=float(x['time'])<=9]
  ax.plot([float(x['time']) for x in r],[float(x['cube_z'])*1000 for x in r],style,color=color,label=policy,linewidth=2)
 ax.set_facecolor('#faf9f6');ax.set_title(condition);ax.set_xlabel('Simulation time (s)');ax.set_ylabel('Cube z (mm)');ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False)
 if condition=='lower-late-gap':ax.axvspan(6.1,6.34,color='#ddd',alpha=.5)
fig.suptitle('E13 / Lowering needs its own evidence and its own recovery destination',fontsize=17);fig.tight_layout();fig.savefig(out/'phase-recovery.png');plt.close(fig)
