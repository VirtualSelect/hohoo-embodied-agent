"""Packet identity, capture time and receipt time are distinct."""
class Monitor:
    def __init__(self, policy, bad_ticks=20, age_ticks=30):
        if policy not in ("count3", "elapsed40", "fresh60"):
            raise ValueError("unknown policy")
        if bad_ticks <= 0 or age_ticks <= 0:
            raise ValueError("nonpositive duration")
        self.policy, self.bad_ticks, self.age_ticks = policy, bad_ticks, age_ticks
        self.latest = None
        self.streak, self.bad_since = 0, None
        self.alarm, self.cause = False, ""
        self.last_now = -1

    def update(self, now, phase, packet=None):
        if now <= self.last_now:
            raise ValueError("control clock must advance")
        self.last_now = now
        fresh = False
        if packet is not None:
            seq, capture, contacts = packet["seq"], packet["capture_tick"], packet["contacts"]
            if not isinstance(seq, int) or not isinstance(capture, int) or seq < 0 or not 0 <= capture <= now or not isinstance(contacts, str):
                raise ValueError("invalid packet")
            if self.latest is None or (seq > self.latest["seq"] and capture > self.latest["capture_tick"]):
                self.latest = dict(packet)
                fresh = True
        if self.alarm:
            return fresh
        if phase != "transfer":
            self.streak, self.bad_since = 0, None
            return fresh
        age = None if self.latest is None else now - self.latest["capture_tick"]
        if self.policy == "fresh60" and (age is None or age >= self.age_ticks):
            self.alarm, self.cause = True, "stale"
            return fresh
        if fresh:
            both = {"left_pad", "right_pad"} <= set(self.latest["contacts"].split("|"))
            if both:
                self.streak, self.bad_since = 0, None
            else:
                self.streak += 1
                if self.bad_since is None:
                    self.bad_since = self.latest["capture_tick"]
                bad = self.streak >= 3 if self.policy == "count3" else self.latest["capture_tick"] - self.bad_since >= self.bad_ticks
                if bad:
                    self.alarm, self.cause = True, "contact"
        return fresh
