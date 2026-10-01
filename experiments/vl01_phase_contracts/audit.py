"""Independent E7 evidence checks. Standard library only; no controller imports.

This validates recorded state/command consistency, not every contact force or
the simulator implementation. SHA-256 establishes integrity, not authenticity.
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = ("control.csv", "trajectory.csv", "states.jsonl", "events.json", "summary.json")
SCHEDULE = (("approach", 1., (0., 0., .16, 0.)),
            ("descend", 1., (0., 0., .024, 0.)),
            ("close", .8, (0., 0., .024, .033)),
            ("lift", 1.2, (0., 0., .18, .033)),
            ("transfer", 1.5, (.24, .12, .18, .033)),
            ("lower", 1., (.24, .12, .04, .033)),
            ("release", .7, (.24, .12, .04, 0.)),
            ("retreat", 1., (.24, .12, .20, 0.)),
            ("settle", 1., (.24, .12, .20, 0.)))


def check(value, message):
    if not value:
        raise ValueError(message)


def close(a, b, message, tol=1e-9):
    check(math.isfinite(float(a)) and abs(float(a) - b) <= tol, message)


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def digest(path, lf=False):
    raw = path.read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n") if lf else raw).hexdigest()


def schedule(tick, dt):
    elapsed, previous = 0, (0., 0., .16, 0.)
    for phase, seconds, end in SCHEDULE:
        duration = round(seconds / dt)
        if tick <= elapsed + duration:
            x = (tick - elapsed) / duration
            blend = 3*x*x - 2*x*x*x
            return phase, [a + (b-a)*blend for a, b in zip(previous, end)]
        elapsed += duration
        previous = end
    raise ValueError("tick exceeds schedule")


def episode(folder, condition, policy, p):
    with (folder / "control.csv").open(encoding="utf8", newline="") as f:
        rows = list(csv.DictReader(f))
    with (folder / "trajectory.csv").open(encoding="utf8", newline="") as f:
        trajectory = list(csv.DictReader(f))
    states = [json.loads(s) for s in (folder / "states.jsonl").read_text(encoding="utf8").splitlines()]
    n = round(p["horizon_s"] / p["dt_s"])
    check(len(rows) == n, "control count")
    sampled = rows[::p["capture_every_ticks"]]
    check(len(sampled) == len(trajectory) == len(states), "sample count")
    latest, replay_packet, bad_start, stop, held, previous_phase = None, None, None, None, None, None
    ignored, derived_events = 0, []
    for tick, row in enumerate(rows, 1):
        check(int(row["tick"]) == tick, "tick order")
        close(row["time"], tick*p["dt_s"], "clock")
        scheduled_phase, goal = schedule(tick, p["dt_s"])
        phase = "hold" if stop else scheduled_phase
        check(row["phase"] == phase and row["scheduled_phase"] == scheduled_phase, "phase")
        target = held if stop else goal
        for key, expected in zip(("target_x", "target_y", "target_z", "target_grip"), target):
            close(row[key], expected, "target hold/schedule")
        # Fault starts at command tick = start/dt + 1; samples are post-step.
        active = condition["start_s"] is not None and (
            round(condition["start_s"] / p["dt_s"]) <= tick-1
            < round((condition["start_s"]+condition["duration_s"]) / p["dt_s"]))
        check(int(row["fault_active"]) == int(active), "fault window")
        grip = 0. if active and condition["kind"] == "open" else target[3]
        close(row["applied_grip"], grip, "grip injection")
        xyz = [float(row["cube_"+a]) for a in "xyz"]
        hand = [float(row["hand_"+a]) for a in "xyz"]
        for v in xyz+hand+[float(row["cube_speed"])]:
            check(math.isfinite(v), "finite physical state")
        error = math.dist(xyz, hand)
        close(row["grasp_error"], error, "grasp error")
        contacts = set(row["contacts"].split("|"))
        check(int(row["finger_contact"]) == int(bool(contacts & {"left_pad", "right_pad"})), "finger flag")
        expected_packets = []
        if (tick-1) % p["capture_every_ticks"] == 0:
            packet = {"seq": (tick-1)//p["capture_every_ticks"], "capture_tick": tick,
                      "contacts": row["contacts"], "cube_z": xyz[2], "grasp_error": float(row["grasp_error"])}
            if not active or condition["kind"] not in ("silence", "replay", "empty"):
                expected_packets = [packet]
            elif condition["kind"] == "empty":
                expected_packets = [{**packet, "contacts": ""}]
            elif condition["kind"] == "replay":
                check(replay_packet is not None, "replay baseline")
                expected_packets = [replay_packet]
            if not active:
                replay_packet = packet
        received = json.loads(row["received"])
        check(received == expected_packets, "packet injection/physical source")
        accepted = []
        for packet in received:
            if latest is None or (packet["seq"] > latest["seq"] and packet["capture_tick"] > latest["capture_tick"]):
                latest = packet
                accepted.append(packet)
            else:
                ignored += 1
        age = tick-latest["capture_tick"] if latest else None
        check(row["latest_seq"] == (str(latest["seq"]) if latest else ""), "latest sequence")
        check(row["age_ticks"] == (str(age) if age is not None else ""), "capture age")
        if previous_phase != phase:
            bad_start = None
        previous_phase = phase
        monitoring = phase == "transfer" or (phase == "lower" and policy != "transfer-only")
        if stop or not monitoring:
            bad_start = None
        else:
            reason = "stale" if age is None or age >= p["max_age_ticks"] else None
            for packet in accepted:
                bilateral = {"left_pad", "right_pad"} <= set(packet["contacts"].split("|"))
                height_required = phase == "transfer" or policy == "reuse-transfer"
                good = (bilateral and packet["grasp_error"] < p["max_grasp_error_m"]
                        and (not height_required or packet["cube_z"] > p["min_transfer_height_m"]))
                if good:
                    bad_start = None
                elif bad_start is None:
                    bad_start = packet["capture_tick"]
                elif packet["capture_tick"]-bad_start >= p["bad_span_ticks"]:
                    reason = reason or "grasp"
            if reason:
                stop = {"type": "stop", "tick": tick, "phase": phase, "reason": reason,
                        "age_ticks": age, "bad_since": bad_start}
                derived_events.append(stop)
                held = goal
        check(int(row["stopped_after"]) == int(stop is not None), "stop decision")
        check(row["bad_since"] == (str(bad_start) if bad_start is not None else ""), "bad span")
    check(read(folder/"events.json") == derived_events, "events")
    for row, trace, state in zip(sampled, trajectory, states):
        check(all(trace[k] == row[k] for k in trace) and len(trace) == 20, "trajectory/control")
        check(state["tick"] == int(row["tick"]), "state tick")
        q, v, u = state["qpos"], state["qvel"], state["ctrl"]
        check(len(q) == 12 and len(v) == 11 and len(u) == 5, "state layout")
        check(all(math.isfinite(x) for x in q+v+u), "state finite")
        for a, expected in zip("xyz", q[:3]):
            close(row["cube_"+a], expected, "cube qpos")
        for a, expected in zip("xyz", [q[7], q[8], q[9]+.16]):
            close(row["hand_"+a], expected, "hand qpos")
        close(row["cube_speed"], math.sqrt(sum(x*x for x in v[:3])), "cube qvel")
        for actual, expected in zip(u, [float(row["target_x"]), float(row["target_y"]), float(row["target_z"])-.16, float(row["applied_grip"]), float(row["applied_grip"])]):
            close(actual, expected, "state actuator")
    c = p["placement"]
    tail = [r for r in sampled if float(r["time"]) >= p["horizon_s"]-c["settle_window_s"]]
    max_z = max(float(r["cube_z"]) for r in rows)
    placed = bool(tail) and max_z > c["lift_z_gt_m"] and all(
        abs(float(r["cube_x"])-c["center_xy_m"][0]) < c["xy_each_lt_m"]
        and abs(float(r["cube_y"])-c["center_xy_m"][1]) < c["xy_each_lt_m"]
        and abs(float(r["cube_z"])-c["rest_z_m"]) < c["z_error_lt_m"]
        and float(r["cube_speed"]) < c["speed_lt_m_s"]
        and not int(r["finger_contact"]) for r in tail)
    summary = read(folder/"summary.json")
    check(summary["warnings"] == {}, "simulation warning reported")
    check(summary["condition"] == condition["id"] and summary["policy"] == policy, "cell identity")
    check(summary["placement"] == placed, "placement summary")
    check(summary["first_stop"] == stop and summary["stopped"] == (stop is not None), "stop summary")
    check(summary["ignored_packets"] == ignored, "ignored packets")
    check(summary["entered_release"] == any(r["phase"] == "release" for r in rows), "release summary")
    close(summary["max_cube_z_m"], max_z, "max height")
    close(summary["simulated_seconds"], p["horizon_s"], "horizon")
    onset = None if condition["start_s"] is None else round(condition["start_s"]/p["dt_s"])+1
    latency = (stop["tick"]-onset)*p["dt_s"]*1000 if stop and onset and stop["tick"] >= onset else None
    return summary, states, {**summary, "fault_to_stop_ms": latency}


def audit(root):
    manifest = read(root/"manifest.json")
    p = manifest["protocol"]
    check(p == read(HERE/"protocol.json"), "frozen protocol")
    check(not manifest["dirtyBeforeOutput"], "uncommitted source at run start")
    check(manifest["mujoco"] == "3.3.7", "simulator version")
    expected_sources = {f.relative_to(ROOT).as_posix() for f in HERE.glob("*.py")}
    expected_sources |= {"experiments/vl01_phase_contracts/protocol.json"}
    expected_sources |= {"experiments/vl01_pick_place/"+x for x in ("run.py", "protocol.json", "scene.xml")}
    check(set(manifest["sourceLfSha256"]) == expected_sources, "source inventory")
    for filename, expected in manifest["sourceLfSha256"].items():
        check(digest(ROOT/filename, True) == expected, "source fingerprint: "+filename)
    hashes = read(root/"raw-sha256.json")
    cells = [c["id"]+"--"+v for c in p["conditions"] for v in p["policies"]]
    check(set(hashes) == {c+"/"+f for c in cells for f in RAW}, "raw inventory")
    for filename, expected in hashes.items():
        check(digest(root/filename) == expected, "raw fingerprint: "+filename)
    summaries, metrics, prefixes = [], [], []
    for condition in p["conditions"]:
        traces, outcomes = {}, {}
        for policy in p["policies"]:
            summary, states, metric = episode(root/(condition["id"]+"--"+policy), condition, policy, p)
            summaries.append(summary)
            metrics.append(metric)
            traces[policy], outcomes[policy] = states, summary
        for a, b in itertools.combinations(p["policies"], 2):
            decisions = [outcomes[x]["first_stop"]["tick"] for x in (a,b) if outcomes[x]["first_stop"]]
            limit = min(decisions) if decisions else round(p["horizon_s"]/p["dt_s"])
            count = 0
            for sa, sb in zip(traces[a], traces[b]):
                if sa["tick"] > limit:
                    break
                check(sa["tick"] == sb["tick"], "prefix ticks")
                for field in ("qpos", "qvel", "ctrl"):
                    check(all(abs(x-y) <= p["prefix_tolerance"] for x,y in zip(sa[field],sb[field])), "physical prefix")
                count += 1
            prefixes.append({"condition": condition["id"], "policies": [a,b], "through_decision_tick": limit, "state_samples": count})
    check(read(root/"summary.json") == summaries, "aggregate summary")
    return {"artifact_valid": True, "cells": len(cells), "raw_files": len(hashes),
            "source_files": len(expected_sources), "prefix_pairs": prefixes, "metrics": metrics,
            "limits": "Recorded-state audit, not a contact-force recomputation. Deterministic single rollouts, not population success rates."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    text = json.dumps(result, indent=2, allow_nan=False)+"\n"
    if args.out:
        with args.out.open("x", encoding="utf8", newline="\n") as f:
            f.write(text)
    print(text)
