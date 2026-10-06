import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parent.parent/'vl01_completion_lifecycle/lifecycle.py'
s=importlib.util.spec_from_file_location('e14_completion_base',p);ref=importlib.util.module_from_spec(s);s.loader.exec_module(ref)
Completion=ref.Completion
class Qualified(Completion):
 def __init__(self,**kw):super().__init__(**kw);self.aborted=False;self.release_tick=None
 def observe(self,now,released,lifted,packet,aborted):
  if type(now) is not int or now<self.now:raise ValueError('monotonic time required')
  if aborted or self.aborted:
   self.now=now;self.aborted=True;self.start=None;self.transition('ABORTED',now,'controller-terminal');return
  # Called at every control tick: first release intent establishes the boundary.
  if not released:self.release_tick=None
  elif self.release_tick is None:self.release_tick=now
  if (packet is not None and self.release_tick is not None
      and type(packet.get('capture_tick')) is int
      and packet['capture_tick']<self.release_tick):packet=None
  self.update(now,released,lifted,packet)
