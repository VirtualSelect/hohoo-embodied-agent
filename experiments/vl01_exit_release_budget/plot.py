import csv,gzip,json,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(sys.argv[1]);out=root/'figures';out.mkdir(exist_ok=False)
assert json.loads((root/'audit.json').read_text())['valid']
plt.rcParams.update({'figure.facecolor':'#faf9f5','axes.facecolor':'#faf9f5','axes.spines.top':False,'axes.spines.right':False,'font.size':10})
def rows(study,condition,policy):
    with gzip.open(root/f'{study}--{condition}--{policy}'/'control.csv.gz','rt') as f:return list(csv.DictReader(f))
fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
for policy,color in zip(('hold','open','open-retreat'),('#aa7252','#54816c','#537d9f')):
    r=rows('E8','lower-drop-late',policy);ax.plot([float(x['time']) for x in r],[float(x['cube_z'])*1000 for x in r],label=policy,color=color)
ax.set(xlim=(6.15,8.7),xlabel='Simulation time (s)',ylabel='Cube centre height (mm)',title='E8 / Same late-drop alarm, different exit actions');ax.legend();fig.savefig(out/'exit-actions.png',dpi=150);plt.close(fig)
res=json.loads((root/'summary.json').read_text());data=[r for r in res if r['study']=='E9'];fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
for i,r in enumerate(data):
    for key,marker,color in (('single_completion','o','#aa7252'),('window_completion','s','#54816c')):
        if r[key] is not None:ax.scatter(r[key]*.002,i,marker=marker,color=color,label=key if i==0 else None)
    ax.text(10.1,i,'final pass' if r['placement'] else 'final fail',va='center')
ax.set(yticks=range(len(data)),yticklabels=[r['condition'] for r in data],xlim=(6.4,12),xlabel='Simulation time (s)',title='E9 / Completion declarations and independently checked final state');ax.legend(loc='lower right');fig.savefig(out/'release-verification.png',dpi=150);plt.close(fig)
fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
for i,policy in enumerate(('unlimited','budget-two','budget-two-cooldown')):
    r=next(x for x in res if x['study']=='E10' and x['condition']=='repeated-gap' and x['policy']==policy)
    for e in r['events']:
        color={'hold':'#aa7252','resume':'#54816c','abort':'#86577e'}[e['type']]
        ax.scatter(e['tick']*.002,i,color=color,marker={'hold':'|','resume':'o','abort':'x'}[e['type']],s=90)
    ax.text(9,i,f"resumes={r['resumes']}; final={'pass' if r['placement'] else 'fail'}",va='center')
ax.set(yticks=range(3),yticklabels=['unlimited','budget-two','budget-two-cooldown'],xlim=(4,12),ylim=(-.6,2.6),xlabel='Simulation time (s)',title='E10 / Repeated gaps: hold |, resume o, abort x');fig.savefig(out/'recovery-budget.png',dpi=150);plt.close(fig)
