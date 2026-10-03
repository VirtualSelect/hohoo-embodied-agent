"""Exit target policy; not a safety certificate."""
import numpy as np
def exit_target(held,elapsed,policy):
    if policy not in ('hold','open','open-retreat') or elapsed<0:raise ValueError('exit arguments')
    target=np.array(held,dtype=float,copy=True)
    if policy!='hold':target[3]=0.
    if policy=='open-retreat':
        a=np.clip((elapsed-.2)/.6,0.,1.);target[2]+=.1*a*a*(3.-2.*a)
    return target
