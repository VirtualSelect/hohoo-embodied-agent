"""Protocol logic without simulator state access."""
import importlib.util
from pathlib import Path

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

HERE=Path(__file__).resolve().parent
Gate=load('e10_base_gate',HERE.parent/'vl01_recovery_gate/gate.py').Gate

class BudgetGate(Gate):
    def __init__(self,cap=None,cooldown=0):
        if (cap is not None and (type(cap) is not int or cap<0)) or type(cooldown) is not int or cooldown<0:raise ValueError('budget')
        super().__init__('revalidate',deadline=400)
        self.cap,self.cooldown,self.resumes=cap,cooldown,0
    def _resume(self,now,reason,age):
        if self.cap is not None and self.resumes>=self.cap:
            self.state='aborted';self.events.append(dict(type='abort',tick=now,reason='budget'));return
        if now-self.hold_tick<self.cooldown:return
        self.resumes+=1;super()._resume(now,reason,age)

def placed(p):
    names=set(p['contacts'].split('|'))
    return (abs(p['x']-.24)<.045 and abs(p['y']-.12)<.045 and abs(p['z']-.026)<.006
            and p['speed']<.02 and 'bin_floor' in names and not {'left_pad','right_pad'}&names)

class ReleaseVerifier:
    def __init__(self,span=125,cadence=10,age=30):
        if min(span,cadence,age)<=0:raise ValueError('threshold')
        self.span,self.cadence,self.age=span,cadence,age
        self.last=None;self.start=None;self.single=None;self.window=None
    def update(self,now,released,lifted,packet):
        if self.last is not None and now-self.last>=self.age:self.start=None
        if packet is None:return
        capture=packet['capture_tick']
        if capture>now or capture<0:raise ValueError('capture')
        if self.last is not None and capture<=self.last:return
        gap=self.last is None or capture-self.last>self.cadence
        self.last=capture
        if not released or not lifted or now-capture>=self.age or not placed(packet):self.start=None;return
        if self.single is None:self.single=now
        if gap or self.start is None:self.start=capture
        if self.window is None and capture-self.start>=self.span:self.window=now
