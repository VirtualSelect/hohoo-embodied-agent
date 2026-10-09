import math
import numpy as np

class VelocityEstimator:
    def __init__(self, mode, tau=.06):
        if mode not in ('difference','ema') or tau<=0: raise ValueError('invalid mode or tau')
        self.mode=mode;self.tau=tau;self.previous=None;self.velocity=np.zeros(2)
    def update(self,time,position):
        position=np.asarray(position,dtype=float)
        if position.shape!=(2,) or not np.isfinite(position).all() or not math.isfinite(time): raise ValueError('finite 2D sample required')
        if self.previous is not None:
            previous_t,previous_p=self.previous;dt=time-previous_t
            if dt<=0:raise ValueError('capture times must strictly increase')
            difference=(position-previous_p)/dt
            alpha=1 if self.mode=='difference' else -math.expm1(-dt/self.tau)
            self.velocity+=alpha*(difference-self.velocity)
        self.previous=(time,position.copy())
        return self.velocity.copy()
