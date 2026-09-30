"""E5 recovery state machine. Uses packet evidence, never direct physics access."""
import math

class Gate:
    def __init__(self, policy, cadence=10, age=30, bad_span=20, confirm=50, deadline=300):
        if policy not in ("latched", "receipt", "revalidate"):
            raise ValueError("policy")
        if min(cadence, age, bad_span, confirm, deadline) <= 0:
            raise ValueError("threshold")
        self.policy, self.cadence, self.age = policy, cadence, age
        self.bad_span, self.confirm, self.deadline = bad_span, confirm, deadline
        self.state, self.latest, self.last_now = "running", None, -1
        self.bad_since, self.hold_tick, self.confirm_start, self.confirm_last = None, None, None, None
        self.accepted = self.ignored = 0
        self.events = []

    @staticmethod
    def good(p):
        return ({"left_pad", "right_pad"} <= set(p["contacts"].split("|"))
                and p["cube_z"] > .12 and p["grasp_error"] < .05)

    def update(self, now, phase, packets=()):
        if type(now) is not int or now <= self.last_now:
            raise ValueError("clock must advance")
        self.last_now = now
        fresh = []
        for p in packets:
            if (type(p.get("seq")) is not int or p["seq"] < 0
                or type(p.get("capture_tick")) is not int or not 0 <= p["capture_tick"] <= now
                or not isinstance(p.get("contacts"), str)
                or any(type(p.get(k)) not in (int,float) or not math.isfinite(p[k]) for k in ("cube_z","grasp_error"))
                or p["grasp_error"] < 0):
                raise ValueError("invalid observation")
            if self.latest is None or (p["seq"] > self.latest["seq"] and p["capture_tick"] > self.latest["capture_tick"]):
                self.latest = dict(p)
                fresh.append(p)
                self.accepted += 1
            else:
                self.ignored += 1
        if self.state == "aborted":
            return
        age = None if self.latest is None else now-self.latest["capture_tick"]
        if self.state == "hold":
            if now-self.hold_tick >= self.deadline:
                self.state = "aborted"
                self.events.append({"type":"abort","tick":now,"reason":"revalidation_deadline"})
                return
            if self.policy == "latched":
                return
            if self.policy == "receipt":
                if packets:
                    self._resume(now,"receipt",age)
                return
            if age is None or age >= self.age:
                self.confirm_start = self.confirm_last = None
            for p in fresh:
                capture = p["capture_tick"]
                if capture <= self.hold_tick or now-capture >= self.age or not self.good(p):
                    self.confirm_start = self.confirm_last = None
                    continue
                if self.confirm_last is None or capture-self.confirm_last > self.cadence:
                    self.confirm_start = capture
                self.confirm_last = capture
            if (self.confirm_start is not None and self.confirm_last-self.confirm_start >= self.confirm
                and age < self.age and self.good(self.latest)):
                self._resume(now,"post_hold_window",age)
            return
        if phase != "transfer":
            self.bad_since = None
            return
        reason = "stale" if age is None or age >= self.age else None
        for p in fresh:
            if self.good(p):
                self.bad_since = None
            elif self.bad_since is None:
                self.bad_since = p["capture_tick"]
            elif p["capture_tick"]-self.bad_since >= self.bad_span:
                reason = reason or "grasp"
        if reason:
            self.state, self.hold_tick = "hold", now
            self.bad_since = self.confirm_start = self.confirm_last = None
            self.events.append({"type":"hold","tick":now,"reason":reason})

    def _resume(self, now, reason, age):
        self.events.append({"type":"resume","tick":now,"reason":reason,
                            "capture_tick":self.latest["capture_tick"],
                            "age_ticks":age,"good":self.good(self.latest),
                            "window_start":self.confirm_start,"window_end":self.confirm_last})
        self.state = "running"
        self.bad_since = self.confirm_start = self.confirm_last = None
