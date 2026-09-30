"""Charts come only from stored rows. No fabricated trajectory or benchmark."""
import csv,json,sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
out=Path(sys.argv[1])
policies=["latched","receipt","revalidate"]
colors=["#8a7895","#bf7a51","#417969"]
fig,axs=plt.subplots(3,1,figsize=(10,7),sharex=True)
for ax,cond in zip(axs,["gap","stale-replay","gap-and-drop"]):
    for pol,color in zip(policies,colors):
        rows=list(csv.DictReader((out/(cond+"-"+pol)/"control.csv").open()))
        ax.step([int(r["tick"])*.002 for r in rows],[{"running":2,"hold":1,"aborted":0}[r["state"]] for r in rows],where="post",label=pol,color=color,lw=1.6,alpha=.8)
    ax.set(yticks=[0,1,2],yticklabels=["aborted","hold","running"],title=cond,xlim=(4.7,6))
    ax.grid(alpha=.15);ax.spines[["top","right"]].set_visible(False)
axs[0].legend(ncol=3,loc="lower left");axs[-1].set_xlabel("Simulation time (s)")
fig.suptitle("Recorded recovery decisions | MuJoCo 3.3.7",fontsize=14)
fig.tight_layout();fig.savefig(out/"recovery-decisions.png",dpi=170);plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(10,4))
for ax,cond in zip(axs,["gap","gap-and-drop"]):
    for pol,color in zip(policies,colors):
        rows=list(csv.DictReader((out/(cond+"-"+pol)/"trajectory.csv").open()))
        ax.plot([float(r["cube_x"]) for r in rows],[float(r["cube_z"]) for r in rows],label=pol,color=color,alpha=.8)
    ax.set(title=cond,xlabel="Cube x (m)",ylabel="Cube z (m)");ax.grid(alpha=.15)
    ax.spines[["top","right"]].set_visible(False)
axs[0].legend();fig.suptitle("Recorded object paths, not camera images");fig.tight_layout()
fig.savefig(out/"recovery-paths.png",dpi=170);plt.close(fig)
