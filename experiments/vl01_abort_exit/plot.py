import csv,gzip,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path(__file__).resolve().parents[2]/'evidence/abort-exit-20261003'
fig,axes=plt.subplots(1,2,figsize=(15,6),dpi=100);fig.set_facecolor('#faf9f6')
for policy,color,style in zip(('hold','open','open-retreat'),('#56836d','#b78061','#899ab4'),('-','-','--')):
 with gzip.open(out/('repeated-gap--'+policy)/'control.csv.gz','rt') as f:rows=list(csv.DictReader(f))
 rows=[r for r in rows if 4<=float(r['time'])<=8]
 for ax,field in zip(axes,['cube_z','hand_z']):ax.plot([float(r['time']) for r in rows],[float(r[field])*1000 for r in rows],style,label=policy,color=color,linewidth=2)
for ax,title in zip(axes,['Cube height','Gripper height']):
 ax.set_facecolor('#faf9f6');ax.set_title(title);ax.axvline(5.422,color='#555',linestyle=':',label='Abort at 5.422s');ax.set_xlabel('Simulation time (s)');ax.set_ylabel('World z (mm)');ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False)
fig.suptitle('E12 / Repeated sensor gaps: three exits, none completes placement',fontsize=17);fig.tight_layout();fig.savefig(out/'abort-exit.png');plt.close(fig)
