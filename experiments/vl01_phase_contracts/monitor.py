"""A phase-dependent sampled-observation monitor; no simulator access."""
import math

POLICIES = ("transfer-only", "reuse-transfer", "phase-aware")


class PhaseMonitor:
    def __init__(self, policy, age=30, bad_span=20, height=.12, error=.05):
        if (policy not in POLICIES or type(age) is not int or age <= 0
            or type(bad_span) is not int or bad_span <= 0
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in (height, error))
            or error <= 0):
            raise ValueError("invalid monitor configuration")
        self.policy, self.age, self.bad_span = policy, age, bad_span
        self.height, self.error = height, error
        self.latest = None
        self.bad_since = None
        self.last_tick = -1
        self.previous_phase = None
        self.stopped = False
        self.events = []
        self.ignored = 0

    def active(self, phase):
        return phase == "transfer" or (phase == "lower" and self.policy != "transfer-only")

    def good(self, packet, phase):
        contact = {"left_pad", "right_pad"} <= set(packet["contacts"].split("|"))
        retained = contact and packet["grasp_error"] < self.error
        height_required = phase == "transfer" or self.policy == "reuse-transfer"
        return retained and (not height_required or packet["cube_z"] > self.height)

    def update(self, tick, phase, packets=()):
        if type(tick) is not int or tick <= self.last_tick:
            raise ValueError("clock must advance")
        self.last_tick = tick
        fresh = []
        for packet in packets:
            if (type(packet.get("seq")) is not int or packet["seq"] < 0
                or type(packet.get("capture_tick")) is not int
                or not 0 <= packet["capture_tick"] <= tick
                or not isinstance(packet.get("contacts"), str)
                or any(type(packet.get(k)) not in (int, float) or not math.isfinite(packet[k])
                       for k in ("cube_z", "grasp_error"))
                or packet["grasp_error"] < 0):
                raise ValueError("invalid observation")
            if (self.latest is None or (packet["seq"] > self.latest["seq"]
                    and packet["capture_tick"] > self.latest["capture_tick"])):
                self.latest = dict(packet)
                fresh.append(packet)
            else:
                self.ignored += 1
        if phase != self.previous_phase:
            self.bad_since = None
        self.previous_phase = phase
        if self.stopped or not self.active(phase):
            self.bad_since = None
            return
        age = None if self.latest is None else tick - self.latest["capture_tick"]
        reason = "stale" if age is None or age >= self.age else None
        for packet in fresh:
            if self.good(packet, phase):
                self.bad_since = None
            elif self.bad_since is None:
                self.bad_since = packet["capture_tick"]
            elif packet["capture_tick"] - self.bad_since >= self.bad_span:
                reason = reason or "grasp"
        if reason:
            self.stopped = True
            self.events.append({"type": "stop", "tick": tick, "phase": phase,
                                "reason": reason, "age_ticks": age,
                                "bad_since": self.bad_since})
