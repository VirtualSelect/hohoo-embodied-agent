"""A completion event is historical; validity requires continuing evidence."""
import math

def placed(p):
    names=set(p['contacts'].split('|'))
    return (abs(p['x']-.24)<.045 and abs(p['y']-.12)<.045
            and abs(p['z']-.026)<.006 and 0<=p['speed']<.02
            and 'bin_floor' in names and not names & {'left_pad','right_pad'})

class Completion:
    def __init__(self, span=125, cadence=10, age=30):
        if any(type(x) is not int or x<=0 for x in (span,cadence,age)):
            raise ValueError('positive integer ticks required')
        self.span,self.cadence,self.age=span,cadence,age
        self.last=self.start=self.completed_at=None
        self.state='NOT_READY';self.events=[];self.now=-1

    def transition(self, state, now, reason):
        if state!=self.state:
            self.events.append(dict(tick=now,from_state=self.state,to_state=state,reason=reason))
            self.state=state

    def update(self, now, released, lifted, packet):
        if type(now) is not int or now<self.now:raise ValueError('monotonic time required')
        self.now=now
        if not released or not lifted:
            self.start=None;self.transition('NOT_READY',now,'prerequisite');return
        if self.last is None or now-self.last>=self.age:
            self.start=None;self.transition('UNKNOWN',now,'no-fresh-evidence')
        if packet is None:return
        capture=packet.get('capture_tick')
        valid=(type(capture) is int and 0<=capture<=now and isinstance(packet.get('contacts'),str)
               and all(type(packet.get(k)) in (int,float) and math.isfinite(packet[k]) for k in ('x','y','z','speed')))
        if not valid:
            self.start=None;self.transition('UNKNOWN',now,'malformed');return
        if self.last is not None and capture<=self.last:return
        gap=self.last is None or capture-self.last>self.cadence
        self.last=capture
        if now-capture>=self.age:
            self.start=None;self.transition('UNKNOWN',now,'stale');return
        if not placed(packet):
            self.start=None;self.transition('INVALID',now,'fresh-violation');return
        if gap or self.start is None:self.start=capture
        if capture-self.start>=self.span:
            self.transition('VALID',now,'sustained-evidence')
            if self.completed_at is None:self.completed_at=now
        else:self.transition('VERIFYING',now,'collecting-evidence')
