"""Plot observed logs only; these charts are not camera observations."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    parser=argparse.ArgumentParser();parser.add_argument('out',type=Path);args=parser.parse_args()
    dt=json.loads((args.out/'manifest.json').read_text())['protocol']['dt_s']
    for condition in ('gap','stale-replay'):
        fig,axes=plt.subplots(2,2,figsize=(11,6),sharex=True)
        for column,gate in enumerate(('receipt','revalidate')):
            for path,style in (('wallclock','-'),('replan','--')):
                episode=args.out/f'{condition}-{gate}-{path}'
                with (episode/'control.csv').open() as f:
                    rows=[r for r in csv.DictReader(f) if 4.7<=int(r['tick'])*dt<=5.8]
                t=[int(r['tick'])*dt for r in rows]
                axes[0,column].plot(t,[float(r['target_x']) for r in rows],style,label=f'{path} target')
                axes[0,column].plot(t,[float(r['hand_x']) for r in rows],style,alpha=.5,label=f'{path} measured')
                axes[1,column].plot(t,[float(r['age_ticks'])*dt*1000 for r in rows],style,label=path)
            axes[0,column].set_title(gate)
            axes[0,column].set_ylabel('World x (m)');axes[0,column].legend(fontsize=7)
            axes[1,column].set_ylabel('Latest packet age (ms)');axes[1,column].set_xlabel('Simulation time (s)')
            axes[1,column].axhline(60,color='red',alpha=.4,label='60ms threshold')
        fig.suptitle(f'E6 {condition}: logged targets, measured position and packet age')
        fig.tight_layout();fig.savefig(args.out/f'{condition}-comparison.png',dpi=150);plt.close(fig)
if __name__=='__main__':main()
