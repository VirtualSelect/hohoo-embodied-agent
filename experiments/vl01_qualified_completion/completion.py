import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parent.parent/'vl01_completion_lifecycle/lifecycle.py'
s=importlib.util.spec_from_file_location('e14_completion_base',p);ref=importlib.util.module_from_spec(s);s.loader.exec_module(ref)
Completion=ref.Completion
class Qualified(Completion):
 def __init__(self,**kw):super().__init__(**kw);self.aborted=False
 def observe(self,now,released,lifted,packet,aborted):
  if type(now) is not int or now<self.now:raise ValueError('monotonic time required')
  if aborted or self.aborted:
   self.now=now;self.aborted=True;self.start=None;self.transition('ABORTED',now,'controller-terminal');return
  self.update(now,released,lifted,packet)
