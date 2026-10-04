"""Freeze the interrupted phase while HOLD is active; do not read simulator state."""
import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parent.parent/'vl01_exit_release_budget/contracts.py'
s=importlib.util.spec_from_file_location('e13_contracts',p);ref=importlib.util.module_from_spec(s);s.loader.exec_module(ref)
class PhaseGate(ref.BudgetGate):
 def __init__(self,policy,cap=2,cooldown=200):
  if policy not in ('transfer-only','reuse-transfer','phase-aware'):raise ValueError('policy')
  super().__init__(cap,cooldown);self.phase_policy=policy;self.context=None
 def good(self,p):
  contact={'left_pad','right_pad'}<=set(p['contacts'].split('|')) and p['grasp_error']<.05
  return contact and (p['cube_z']>.12 if self.context=='transfer' or self.phase_policy=='reuse-transfer' else True)
 def update(self,now,phase,packets=()):
  if self.state=='running' and phase!=self.context:self.context=phase;self.bad_since=None
  active=phase=='transfer' or phase=='lower' and self.phase_policy!='transfer-only'
  before=len(self.events);super().update(now,'transfer' if active else phase,packets)
  for e in self.events[before:]:e['interrupted_phase']=self.context
def recovery_schedule(phase,schedule):
 if phase=='transfer':return [('transfer',.5,[.24,.12,.18,.033])]+schedule[5:]
 if phase=='lower':return [('lower',.5,[.24,.12,.04,.033])]+schedule[6:]
 raise ValueError('cannot resume inactive phase')
