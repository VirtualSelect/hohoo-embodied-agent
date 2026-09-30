"""Independent E6 artifact audit and descriptive factorial metrics.

Reads raw artifacts only: no Gate import, controller execution, or MuJoCo replay.
A valid audit can accompany an unsupported hypothesis. Resume decisions occur
AFTER the physics step: tick r is the last held target and measured resume pose;
r+1 is the first post-resume command. Hand speed is the 2 ms backward difference.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW_FILES = ("control.csv", "trajectory.csv", "states.jsonl", "events.json", "replans.json", "summary.json")
CONDITIONS = {"clean", "delay-40ms", "reordered", "gap", "stale-replay", "gap-and-drop"}
VARIANTS = {("receipt", "wallclock"), ("receipt", "replan"),
            ("revalidate", "wallclock"), ("revalidate", "replan"), ("latched", "wallclock")}


class AuditError(ValueError):
    """An artifact-integrity or recorded-fact inconsistency."""


def require(ok, message):
    if not ok:
        raise AuditError(message)


def finite_tree(value, label):
    if isinstance(value, float):
        require(math.isfinite(value), f"{label}: nonfinite value")
    elif isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, f"{label}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            finite_tree(item, f"{label}[{i}]")


def decode(text, label):
    value = json.loads(text)
    finite_tree(value, label)
    return value


def read(path):
    return decode(path.read_text(encoding="utf8"), str(path))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(value, label):
    value = float(value)
    require(math.isfinite(value), f"{label}: nonfinite value")
    return value


def table(path, floats, integers, optional=()):
    with path.open(encoding="utf8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(bool(rows), f"{path}: empty table")
    for index, row in enumerate(rows):
        label = f"{path.name}:{index + 2}"
        require(None not in row and all(v is not None for v in row.values()), f"{label}: malformed row")
        for key in floats:
            row[key] = numeric(row[key], f"{label}.{key}")
        for key in integers:
            row[key] = int(row[key])
        for key in optional:
            row[key] = None if row[key] == "" else int(row[key])
    return rows


def xyz(row, stem):
    return [row[stem + "_" + axis] for axis in "xyz"]


def distance(a, b):
    require(len(a) == len(b), "vector lengths differ")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def close(a, b, label, tolerance=1e-10):
    require(abs(a - b) <= tolerance, f"{label}: {a!r} != {b!r}")


def good(packet):
    return ({"left_pad", "right_pad"} <= set(packet["contacts"].split("|"))
            and packet["cube_z"] > .12 and packet["grasp_error"] < .05)


def scene_layout(path):
    """Read scalar/free joint offsets from XML, without loading the simulator."""
    root = ET.parse(path).getroot()
    nq = nv = 0
    joints = {}
    for element in root.find("worldbody").iter():
        if element.tag not in ("joint", "freejoint"):
            continue
        kind = "free" if element.tag == "freejoint" else element.get("type", "hinge")
        joints[element.get("name", "cube_free")] = (nq, nv)
        nq += {"free": 7, "ball": 4}.get(kind, 1)
        nv += {"free": 6, "ball": 3}.get(kind, 1)
    hand = root.find(".//body[@name='hand']")
    origin = [float(x) for x in hand.get("pos", "0 0 0").split()]
    return joints, origin, nq, nv


def expected_deliveries(condition, protocol, total, cadence):
    """Check the frozen transport schedule, independently of logged gate state."""
    dt = protocol["dt_s"]
    deliveries = {}
    last_pre_fault = None
    for capture in range(1, total + 1, cadence):
        t = (capture - 1) * dt
        seq = (capture - 1) // cadence
        in_gap = (condition in ("gap", "stale-replay", "gap-and-drop")
                  and protocol["fault_start_s"] <= t < protocol["gap_end_s"])
        replay = condition == "stale-replay" and protocol["gap_end_s"] <= t < protocol["replay_end_s"]
        if not in_gap:
            source = last_pre_fault if replay else capture
            delay = (round(.040 / dt) if condition == "delay-40ms" else
                     round(.080 / dt) if condition == "reordered" and t >= protocol["fault_start_s"] and seq % 3 == 0 else 0)
            arrival = capture + delay
            if arrival <= total:
                deliveries.setdefault(arrival, []).append((seq, source))
        if t < protocol["fault_start_s"]:
            last_pre_fault = capture
    return {tick: [source for _, source in sorted(values)] for tick, values in deliveries.items()}


def placed(row, config):
    return (abs(row["cube_x"] - config["bin_center_xy_m"][0]) < config["max_abs_xy_error_m"]
            and abs(row["cube_y"] - config["bin_center_xy_m"][1]) < config["max_abs_xy_error_m"]
            and abs(row["cube_z"] - config["cube_rest_z_m"]) < config["max_abs_z_error_m"]
            and row["cube_speed"] < config["max_linear_speed_m_s"]
            and (not config["require_no_finger_contact"] or not row["finger_contact"]))


def initial_gate_check(summary, trajectory, controls, config, dt):
    first_transfer = next(row["tick"] for row in controls if row["phase"] == "transfer")
    now = (first_transfer - 1) * dt
    window = [row for row in trajectory if now - config["window_s"] - 1e-9 <= row["time"] <= now]
    complete = (len(window) >= config["min_samples"] and
                window[-1]["time"] - window[0]["time"] >= config["minimum_span_s"] - 1e-9 and
                now - window[-1]["time"] <= config["max_sample_age_s"] and
                all(0 < b["time"] - a["time"] <= .0200001 for a, b in zip(window, window[1:])))
    high = bool(window) and all(row["cube_z"] > config["min_cube_z_m"] for row in window)
    both = bool(window) and all({"left_pad", "right_pad"} <= set(row["contacts"].split("|")) for row in window)
    expected = {"accepted": complete and high and both,
                "reasons": [name for ok, name in ((complete, "incomplete_window"), (high, "height_not_confirmed"),
                                                  (both, "bilateral_contact_not_confirmed")) if not ok],
                "samples": len(window), "window_start": window[0]["time"] if window else None,
                "window_end": window[-1]["time"] if window else None,
                "min_cube_z_m": min(row["cube_z"] for row in window) if window else None,
                "both_pad_samples": sum({"left_pad", "right_pad"} <= set(row["contacts"].split("|")) for row in window)}
    require(expected == summary["initial_gate"], "initial gate summary differs from raw samples")
    require(expected["accepted"], "initial gate not accepted")


def evidence_window(event, hold_tick, accepted, controls, age, cadence, confirm, deadline):
    """Compute the maximal valid packet suffix; event window fields are claims.

    This inspects observed evidence only, and never predicts gate transitions.
    It also evaluates receipt resumes, whose event window fields are empty.
    """
    tick = event["tick"]
    suffix = []
    for recv, packet in accepted:
        if recv <= hold_tick or recv > tick:
            continue
        capture = packet["capture_tick"]
        if capture <= hold_tick or recv - capture >= age or not good(packet):
            suffix = []
            continue
        if suffix:
            prior_recv, prior = suffix[-1]
            uninterrupted = all(row["age_ticks"] is not None and row["age_ticks"] < age
                                for row in controls[prior_recv - 1:recv - 1])
            if capture - prior["capture_tick"] > cadence or not uninterrupted:
                suffix = []
        suffix.append((recv, packet))
    problems = []
    latest = controls[tick - 1]
    if not suffix:
        problems.append("no_valid_post_hold_capture_suffix")
        start = end = None
    else:
        start, end = suffix[0][1]["capture_tick"], suffix[-1][1]["capture_tick"]
        if end - start < confirm:
            problems.append("confirmation_span_too_short")
        if any(not (a["seq"] < b["seq"] and 0 < b["capture_tick"] - a["capture_tick"] <= cadence)
               for (_, a), (_, b) in zip(suffix, suffix[1:])):
            problems.append("noncontinuous_or_unordered_captures")
        if latest["capture_tick"] != end or latest["age_ticks"] >= age or not latest["good"]:
            problems.append("latest_not_fresh_valid_at_resume")
        if any(row["age_ticks"] is None or row["age_ticks"] >= age
               for row in controls[suffix[-1][0] - 1:tick]):
            problems.append("freshness_lapse_after_last_capture")
    if tick - hold_tick >= deadline:
        problems.append("resume_at_or_after_hold_deadline")
    claimed_start, claimed_end = event["window_start"], event["window_end"]
    claim_matches = (claimed_start == start and claimed_end == end)
    return {"valid": not problems, "problems": problems, "packets": len(suffix),
            "start_capture_tick": start, "end_capture_tick": end,
            "span_ticks": end - start if start is not None else None,
            "claimed_start_capture_tick": claimed_start, "claimed_end_capture_tick": claimed_end,
            "event_window_matches_recomputed": claim_matches}


def inspect_episode(out, summary, protocol, config, guard_config, layout):
    name = summary["episode"]
    folder = out / name
    require(folder.parent == out and folder.is_dir(), f"invalid episode folder: {name}")
    for filename in RAW_FILES:
        require((folder / filename).is_file(), f"{name}: missing {filename}")
    local = read(folder / "summary.json")
    require(local == {key: value for key, value in summary.items() if key != "episode"}, f"{name}: summaries differ")
    controls = table(folder / "control.csv", [f"{stem}_{axis}" for stem in ("target", "hand") for axis in "xyz"] +
                     ["cube_z", "hand_speed"], ["tick"],
                     ["latest_seq", "capture_tick", "age_ticks", "good", "window_start", "window_end"])
    trajectory = table(folder / "trajectory.csv", [f"{stem}_{axis}" for stem in ("target", "hand", "cube") for axis in "xyz"] +
                       ["time", "grip_target", "cube_speed"], ["tick", "finger_contact"])
    states = [decode(line, f"{name}:state") for line in (folder / "states.jsonl").read_text(encoding="utf8").splitlines()]
    events, replans = read(folder / "events.json"), read(folder / "replans.json")
    dt, total = protocol["dt_s"], round(protocol["horizon_s"] / protocol["dt_s"])
    cadence = round(protocol["period_ms"] / 1000 / dt)
    age = round(protocol["max_age_ms"] / 1000 / dt)
    confirm = round(protocol["confirm_span_ms"] / 1000 / dt)
    deadline = round(protocol["max_hold_ms"] / 1000 / dt)
    record_ticks = list(range(1, total + 1, config["record_every_steps"]))
    require(len(controls) == total, f"{name}: control row count")
    require([r["tick"] for r in trajectory] == record_ticks, f"{name}: trajectory tick coverage")
    require([s["tick"] for s in states] == record_ticks, f"{name}: state tick coverage")
    close(summary["simulation_seconds"], total * dt, f"{name}: horizon", 1e-9)
    require(not summary["warnings"], f"{name}: MuJoCo warnings")
    require(summary["policy"] == summary["gate_mode"], f"{name}: incompatible policy alias")
    expected = expected_deliveries(summary["condition"], protocol, total, cadence)
    captured = {row["tick"]: row for row in trajectory}
    previous_hand = layout[1]
    latest = None
    ignored = 0
    accepted = []
    by_tick = {}
    for event in events:
        require(type(event["tick"]) is int and 1 <= event["tick"] <= total, f"{name}: event tick")
        require(event["type"] in ("hold", "resume", "abort"), f"{name}: event kind")
        require(event["tick"] not in by_tick, f"{name}: multiple transitions in one tick")
        by_tick[event["tick"]] = event
    require([e["tick"] for e in events] == sorted(by_tick), f"{name}: event order")
    previous_state, active_hold, hold_target = "running", None, None
    resume_metrics, deadline_checks = [], []
    for tick, row in enumerate(controls, 1):
        require(row["tick"] == tick, f"{name}: control tick sequence")
        require(row["gate_mode"] == summary["gate_mode"] and row["path_mode"] == summary["path_mode"], f"{name}: control variant")
        hand = xyz(row, "hand")
        close(row["hand_speed"], distance(hand, previous_hand) / dt, f"{name}:{tick}: hand speed", 1e-9)
        previous_hand = hand
        packets = decode(row["received"], f"{name}:{tick}: received")
        require(isinstance(packets, list), f"{name}:{tick}: packet array")
        require([pkt["capture_tick"] for pkt in packets] == expected.get(tick, []), f"{name}:{tick}: transport delivery schedule")
        for pkt in packets:
            require(type(pkt["seq"]) is int and pkt["seq"] >= 0 and type(pkt["capture_tick"]) is int,
                    f"{name}:{tick}: packet identifiers")
            capture = pkt["capture_tick"]
            require(0 < capture <= tick and capture in captured, f"{name}:{tick}: capture coverage")
            require(pkt["seq"] == (capture - 1) // cadence, f"{name}:{tick}: capture sequence")
            source = captured[capture]
            require(pkt["contacts"] == source["contacts"], f"{name}:{tick}: packet contacts")
            close(pkt["cube_z"], source["cube_z"], f"{name}:{tick}: packet cube_z")
            close(pkt["grasp_error"], distance(xyz(source, "cube"), xyz(source, "hand")), f"{name}:{tick}: packet grasp error")
            if latest is None or pkt["seq"] > latest["seq"] and capture > latest["capture_tick"]:
                latest = pkt
                accepted.append((tick, pkt))
            else:
                ignored += 1
        for key, value in (("latest_seq", None if latest is None else latest["seq"]),
                           ("capture_tick", None if latest is None else latest["capture_tick"]),
                           ("age_ticks", None if latest is None else tick - latest["capture_tick"]),
                           ("good", None if latest is None else int(good(latest)))):
            require(row[key] == value, f"{name}:{tick}: independently recomputed {key}")
        if previous_state != "running":
            require(row["phase"] == ("hold" if previous_state == "hold" else "aborted"), f"{name}:{tick}: stopped phase")
            close(distance(xyz(row, "target"), hold_target), 0, f"{name}:{tick}: held target")
        event = by_tick.get(tick)
        if event is None:
            require(row["state"] == previous_state, f"{name}:{tick}: unlogged transition")
        elif event["type"] == "hold":
            require(previous_state == "running" and row["state"] == "hold" and row["phase"] == "transfer", f"{name}:{tick}: hold transition")
            active_hold, hold_target = tick, xyz(row, "target")
            if event["reason"] == "stale":
                require(latest is None or tick - latest["capture_tick"] >= age, f"{name}:{tick}: false stale evidence")
            else:
                require(event["reason"] == "grasp", f"{name}:{tick}: hold reason")
                start_tick = tick
                while start_tick > 1:
                    previous = controls[start_tick - 2]
                    if previous["phase"] != "transfer" or previous["state"] != "running":
                        break
                    start_tick -= 1
                bad_suffix = []
                for recv, packet in accepted:
                    if recv < start_tick:
                        continue
                    if good(packet):
                        bad_suffix = []
                    else:
                        bad_suffix.append(packet)
                require(latest is not None and tick - latest["capture_tick"] < age,
                        f"{name}:{tick}: grasp reason masks stale evidence")
                require(len(bad_suffix) >= 2 and bad_suffix[-1]["capture_tick"] - bad_suffix[0]["capture_tick"] >=
                        round(protocol["bad_span_ms"] / 1000 / dt), f"{name}:{tick}: grasp hold lacks bad-span evidence")
        elif event["type"] == "resume":
            require(previous_state == "hold" and row["state"] == "running" and active_hold is not None,
                    f"{name}:{tick}: resume transition")
            require(latest is not None, f"{name}:{tick}: resume without any packet")
            for key, value in (("capture_tick", latest["capture_tick"]), ("age_ticks", tick - latest["capture_tick"]), ("good", good(latest))):
                require(event[key] == value, f"{name}:{tick}: resume {key}")
            window = evidence_window(event, active_hold, accepted, controls, age, cadence, confirm, deadline)
            support = tick - latest["capture_tick"] < age and good(latest)
            if summary["gate_mode"] == "receipt":
                require(bool(packets), f"{name}:{tick}: receipt resume without delivery")
            require(tick < total, f"{name}:{tick}: resume has no post-resume command")
            first = controls[tick]
            speeds = [r["hand_speed"] for r in controls[tick:min(total, tick + round(.2 / dt))]]
            resume_metrics.append({"tick": tick, "hold_tick": active_hold, "resume_latency_s": (tick - active_hold) * dt,
                                   "age_ticks": tick - latest["capture_tick"], "age_ms": (tick - latest["capture_tick"]) * dt * 1000,
                                   "grasp_good": good(latest), "fresh_and_grasp_supported": support,
                                   "confirmation_window": window, "before_deadline": tick - active_hold < deadline,
                                   "last_held_target_xyz_m": xyz(row, "target"), "resume_hand_xyz_m": hand,
                                   "first_post_resume_tick": tick + 1, "first_post_resume_target_xyz_m": xyz(first, "target"),
                                   "J_m": distance(xyz(first, "target"), xyz(row, "target")),
                                   "E_m": distance(xyz(first, "target"), hand),
                                   "peak_hand_speed_200ms_m_s": max(speeds),
                                   "speed_window_samples": len(speeds), "speed_window_complete": len(speeds) == round(.2 / dt)})
        else:
            require(previous_state == "hold" and row["state"] == "aborted" and active_hold is not None,
                    f"{name}:{tick}: abort transition")
            deadline_checks.append({"hold_tick": active_hold, "abort_tick": tick,
                                    "elapsed_ticks": tick - active_hold, "exact_deadline": tick - active_hold == deadline})
        previous_state = row["state"]
    require(summary["state"] == previous_state, f"{name}: final state")
    holds = [event for event in events if event["type"] == "hold"]
    resumes = [event for event in events if event["type"] == "resume"]
    require(summary["holds"] == len(holds) and summary["resumes"] == len(resumes), f"{name}: transition counts")
    unsupported = sum(not metric["fresh_and_grasp_supported"] for metric in resume_metrics)
    require(summary["unsupported_resumes"] == unsupported, f"{name}: unsupported resume count")
    require(summary["ignored_packets"] == ignored, f"{name}: ignored packet count")
    require(summary["first_hold_tick"] == (holds[0]["tick"] if holds else None), f"{name}: first hold tick")
    require(summary["first_resume_tick"] == (resumes[0]["tick"] if resumes else None), f"{name}: first resume tick")
    joints, origin, nq, nv = layout
    for row, state in zip(trajectory, states):
        tick, control = row["tick"], controls[row["tick"] - 1]
        require(len(state["qpos"]) == nq and len(state["qvel"]) == nv and len(state["ctrl"]) == 5, f"{name}:{tick}: state dimensions")
        close(row["time"], tick * dt, f"{name}:{tick}: sample timestamp", 1e-9)
        for stem in ("target", "hand"):
            close(distance(xyz(row, stem), xyz(control, stem)), 0, f"{name}:{tick}: table {stem}")
        close(row["cube_z"], control["cube_z"], f"{name}:{tick}: table cube_z")
        require(row["phase"] == control["phase"] and row["contacts"] == control["physical_contacts"], f"{name}:{tick}: table phase/contacts")
        require(row["finger_contact"] == int(bool({"left_pad", "right_pad"} & set(row["contacts"].split("|")))), f"{name}:{tick}: finger contact")
        observed_hand = [state["qpos"][joints[axis][0]] + origin[i] for i, axis in enumerate("xyz")]
        close(distance(observed_hand, xyz(row, "hand")), 0, f"{name}:{tick}: hand vs qpos")
        cube_qpos, cube_qvel = joints["cube_free"]
        close(distance(state["qpos"][cube_qpos:cube_qpos + 3], xyz(row, "cube")), 0, f"{name}:{tick}: cube vs qpos")
        close(math.sqrt(sum(v * v for v in state["qvel"][cube_qvel:cube_qvel + 3])), row["cube_speed"], f"{name}:{tick}: cube speed")
        expected_ctrl = [row["target_x"], row["target_y"], row["target_z"] - origin[2], row["grip_target"], row["grip_target"]]
        close(distance(state["ctrl"], expected_ctrl), 0, f"{name}:{tick}: actuator targets")
    initial_gate_check(summary, trajectory, controls, guard_config, dt)
    max_z = max(row["cube_z"] for row in controls)
    success_config = config["success"]
    final = [row for row in trajectory if row["time"] >= summary["simulation_seconds"] - success_config["settle_window_s"]]
    success = bool(final) and max_z > success_config["cube_lift_height_m"] and all(placed(row, success_config) for row in final)
    require(success == summary["success"], f"{name}: placement success differs from raw data")
    streak_start, time_to_success, lifted = None, None, False
    for row in trajectory:
        lifted = lifted or row["cube_z"] > success_config["cube_lift_height_m"]
        if not placed(row, success_config):
            streak_start = None
        elif streak_start is None:
            streak_start = row["time"]
        if (lifted and streak_start is not None and row["time"] - streak_start >= success_config["settle_window_s"] - 1e-9
                and time_to_success is None):
            time_to_success = row["time"]
    hold_deadlines = []
    for index, event in enumerate(events):
        if event["type"] != "hold":
            continue
        following = events[index + 1] if index + 1 < len(events) else None
        if following is None:
            compliant = total < event["tick"] + deadline
        elif following["type"] == "resume":
            compliant = following["tick"] < event["tick"] + deadline
        else:
            compliant = following["type"] == "abort" and following["tick"] == event["tick"] + deadline
        hold_deadlines.append({"hold_tick": event["tick"], "deadline_tick": event["tick"] + deadline,
                               "next_transition": following, "compliant": compliant})
    expected_replan_ticks = [event["tick"] for event in resumes] if summary["path_mode"] == "replan" else []
    require([item["tick"] for item in replans] == expected_replan_ticks, f"{name}: replan/resume mapping")
    for record, metric in zip(replans, resume_metrics):
        require(len(record["measured_start"]) == 4 and len(record["old_target"]) == 4 and len(record["goal"]) == 4,
                f"{name}: replan vector shape")
        close(distance(record["old_target"][:3], metric["last_held_target_xyz_m"]), 0, f"{name}: replan old target")
        close(record["duration_s"], protocol["replan_transfer_s"], f"{name}: replan duration")
        close(distance(record["goal"], [.24, .12, .18, .033]), 0, f"{name}: replan goal")
        metric["replan_start_error_m"] = distance(record["measured_start"][:3], metric["resume_hand_xyz_m"])
    metrics = {"episode": name, "condition": summary["condition"], "gate_mode": summary["gate_mode"], "path_mode": summary["path_mode"],
               "success": success, "state": summary["state"], "holds": len(holds), "resumes": len(resumes),
               "unsupported_resumes": unsupported, "invalid_revalidation_windows": sum(not m["confirmation_window"]["valid"] for m in resume_metrics),
               "full_window_supported_resumes": sum(m["confirmation_window"]["valid"] for m in resume_metrics),
               "missing_full_window_resumes": sum(not m["confirmation_window"]["valid"] for m in resume_metrics),
               "revalidation_window_claim_mismatches": sum(not m["confirmation_window"]["event_window_matches_recomputed"] for m in resume_metrics) if summary["gate_mode"] == "revalidate" else None,
               "ignored_packets": ignored, "first_hold_tick": summary["first_hold_tick"], "first_resume_tick": summary["first_resume_tick"],
               "first_resume_latency_s": resume_metrics[0]["resume_latency_s"] if resume_metrics else None,
               "first_resume": resume_metrics[0] if resume_metrics else None, "resume_metrics": resume_metrics,
               "time_to_success_s": time_to_success, "completed_within_horizon": time_to_success is not None,
               "simulation_seconds": summary["simulation_seconds"], "max_cube_z_m": max_z, "abort_deadline_checks": deadline_checks,
               "hold_deadline_checks": hold_deadlines,
               "stop_reference_compliant": summary["gate_mode"] != "latched" or not resumes,
               "recorded_rows": {"control": len(controls), "trajectory": len(trajectory), "states": len(states)}}
    return metrics, controls, states


def compare_prefix(left, right, limit, left_controls, right_controls, tolerance, kind):
    pairs = [(a, b) for a, b in zip(left["states"], right["states"]) if a["tick"] <= limit]
    require(pairs, "empty prefix")
    max_error = 0.
    for a, b in pairs:
        require(a["tick"] == b["tick"], "prefix ticks differ")
        for key in ("qpos", "qvel", "ctrl"):
            require(len(a[key]) == len(b[key]), "prefix state dimensions differ")
            max_error = max(max_error, max(abs(x - y) for x, y in zip(a[key], b[key])))
    max_control_error = 0.
    for a, b in zip(left_controls[:limit], right_controls[:limit]):
        for key in ("target_x", "target_y", "target_z", "hand_x", "hand_y", "hand_z", "hand_speed", "cube_z"):
            max_control_error = max(max_control_error, abs(a[key] - b[key]))
        require(a["phase"] == b["phase"] and a["received"] == b["received"], f"{kind}: pre-decision phase/packets differ")
    require(max_error < tolerance and max_control_error < tolerance, f"{kind}: prefix mismatch {max_error}/{max_control_error}")
    return {"kind": kind, "left": left["metrics"]["episode"], "right": right["metrics"]["episode"],
            "through_tick_inclusive": limit, "state_samples": len(pairs), "control_samples": limit,
            "max_state_abs_error": max_error, "max_control_abs_error": max_control_error}


def audit(out):
    manifest, summaries = read(out / "manifest.json"), read(out / "summary.json")
    protocol = manifest["protocol"]
    require(set(protocol["conditions"]) == CONDITIONS and len(protocol["conditions"]) == 6, "frozen six conditions differ")
    require({(v["gate_mode"], v["path_mode"]) for v in protocol["variants"]} == VARIANTS and len(protocol["variants"]) == 5,
            "frozen five variants differ")
    require(protocol["repeats"] == 1 and protocol.get("seed") is None, "deterministic single-cell matrix required")
    require(len(summaries) == 30, "expected exactly 30 episodes")
    expected_keys = {(condition, gate, path) for condition in CONDITIONS for gate, path in VARIANTS}
    require({(r["condition"], r["gate_mode"], r["path_mode"]) for r in summaries} == expected_keys, "missing/duplicate matrix cells")
    require(len({r["episode"] for r in summaries}) == 30, "duplicate episode folders")
    for row in summaries:
        require(row["episode"] == "-".join((row["condition"], row["gate_mode"], row["path_mode"])), "episode naming mismatch")
    required_sources = {"experiments/vl01_recovery_ablation/" + f for f in ("run.py", "gate.py", "audit.py", "protocol.json")}
    required_sources |= {"experiments/vl01_pick_place/" + f for f in ("run.py", "protocol.json", "scene.xml")}
    required_sources |= {"experiments/vl01_grasp_guard/" + f for f in ("run.py", "protocol.json")}
    require(required_sources <= set(manifest["sourceSha256"]), "manifest missing required source hashes")
    for filename, expected in manifest["sourceSha256"].items():
        source = (ROOT / filename).resolve()
        require(source.is_relative_to(ROOT) and digest(source) == expected, f"source hash mismatch: {filename}")
    require(protocol == read(HERE / "protocol.json"), "manifest protocol differs from frozen source")
    config = read(ROOT / "experiments/vl01_pick_place/protocol.json")
    guard_config = read(ROOT / "experiments/vl01_grasp_guard/protocol.json")
    layout = scene_layout(ROOT / "experiments/vl01_pick_place/scene.xml")
    raw_hashes = {filename: digest(out / filename) for filename in ("manifest.json", "summary.json")}
    cells = {}
    for summary in summaries:
        try:
            metrics, controls, states = inspect_episode(out, summary, protocol, config, guard_config, layout)
        except (AuditError, KeyError, TypeError, ValueError) as error:
            raise AuditError(f"{summary['episode']}: {error}") from error
        cells[(summary["condition"], summary["gate_mode"], summary["path_mode"])] = {"metrics": metrics, "controls": controls, "states": states}
        for filename in RAW_FILES:
            name = summary["episode"] + "/" + filename
            raw_hashes[name] = digest(out / name)
    for filename, expected in manifest.get("rawFileSha256", {}).items():
        require(filename in raw_hashes and raw_hashes[filename] == expected, f"raw hash mismatch: {filename}")
    total = round(protocol["horizon_s"] / protocol["dt_s"])
    thresholds = protocol.get("acceptance", {})
    tolerance = thresholds.get("prefix_abs_tolerance", 1e-10)
    prefixes, path_pairs, gate_pairs, interactions = [], [], [], []
    for condition in protocol["conditions"]:
        reference = cells[(condition, "latched", "wallclock")]
        for gate, path in sorted(VARIANTS - {("latched", "wallclock")}):
            cell = cells[(condition, gate, path)]
            limit = min(reference["metrics"]["first_hold_tick"] or total, cell["metrics"]["first_hold_tick"] or total)
            prefixes.append(compare_prefix(reference, cell, limit, reference["controls"], cell["controls"], tolerance, "before_first_hold"))
        for gate in ("receipt", "revalidate"):
            a, b = cells[(condition, gate, "wallclock")], cells[(condition, gate, "replan")]
            first_a, first_b = a["metrics"]["first_resume"], b["metrics"]["first_resume"]
            require(a["metrics"]["first_resume_tick"] == b["metrics"]["first_resume_tick"], f"{condition}/{gate}: first resume ticks differ")
            limit = a["metrics"]["first_resume_tick"] or total
            prefixes.append(compare_prefix(a, b, limit, a["controls"], b["controls"], tolerance, "same_gate_before_first_resume"))
            pair = {"condition": condition, "gate_mode": gate, "wallclock": a["metrics"]["episode"], "replan": b["metrics"]["episode"],
                    "first_resume_tick": a["metrics"]["first_resume_tick"], "comparable_first_resume": first_a is not None and first_b is not None,
                    "success_difference_replan_minus_wallclock": int(b["metrics"]["success"]) - int(a["metrics"]["success"]),
                    "resume_count_difference_replan_minus_wallclock": b["metrics"]["resumes"] - a["metrics"]["resumes"]}
            if first_a and first_b:
                for field in ("J_m", "E_m", "peak_hand_speed_200ms_m_s"):
                    pair[field] = {"wallclock": first_a[field], "replan": first_b[field], "difference_replan_minus_wallclock": first_b[field] - first_a[field]}
                ratio = first_b["J_m"] / first_a["J_m"] if first_a["J_m"] > 0 else None
                pair["jump_ratio_replan_over_wallclock"] = ratio
                pair["jump_half_supported"] = first_b["J_m"] <= thresholds.get("jump_ratio_max", .5) * first_a["J_m"]
                pair["jump_half_is_primary_test"] = condition in ("gap", "stale-replay")
            path_pairs.append(pair)
        for path in ("wallclock", "replan"):
            a, b = cells[(condition, "receipt", path)]["metrics"], cells[(condition, "revalidate", path)]["metrics"]
            pair = {"condition": condition, "path_mode": path, "receipt": a["episode"], "revalidate": b["episode"]}
            for field in ("unsupported_resumes", "resumes", "success"):
                pair[field + "_difference_revalidate_minus_receipt"] = int(b[field]) - int(a[field])
            pair["first_resume_latency_difference_s"] = (b["first_resume_latency_s"] - a["first_resume_latency_s"]
                                                          if a["first_resume_latency_s"] is not None and b["first_resume_latency_s"] is not None else None)
            gate_pairs.append(pair)
        interaction = {"condition": condition, "definition": "(revalidate/replan - revalidate/wallclock) - (receipt/replan - receipt/wallclock)"}
        for field in ("success", "resumes", "unsupported_resumes"):
            interaction[field] = ((int(cells[(condition, "revalidate", "replan")]["metrics"][field]) - int(cells[(condition, "revalidate", "wallclock")]["metrics"][field]))
                                  - (int(cells[(condition, "receipt", "replan")]["metrics"][field]) - int(cells[(condition, "receipt", "wallclock")]["metrics"][field])))
        firsts = [cells[(condition, gate, path)]["metrics"]["first_resume"] for gate, path in
                  (("revalidate", "replan"), ("revalidate", "wallclock"), ("receipt", "replan"), ("receipt", "wallclock"))]
        for field in ("J_m", "E_m", "peak_hand_speed_200ms_m_s"):
            interaction[field] = firsts[0][field] - firsts[1][field] - firsts[2][field] + firsts[3][field] if all(firsts) else None
        interactions.append(interaction)
    metrics_list = [cells[(r["condition"], r["gate_mode"], r["path_mode"])]["metrics"] for r in summaries]
    revalidated = [m for m in metrics_list if m["gate_mode"] == "revalidate"]
    replan_resumes = [r for m in metrics_list if m["path_mode"] == "replan" for r in m["resume_metrics"]]
    primary = [pair for pair in path_pairs if pair.get("jump_half_is_primary_test")]
    dropped = [m for m in revalidated if m["condition"] == "gap-and-drop"]
    acceptance = {
        "revalidate_zero_unsupported_resumes": all(m["unsupported_resumes"] == 0 for m in revalidated),
        "revalidate_all_confirmation_windows_valid": all(m["invalid_revalidation_windows"] == 0 for m in revalidated),
        "revalidate_window_claims_match_raw_evidence": all(m["revalidation_window_claim_mismatches"] == 0 for m in revalidated),
        "all_abort_deadlines_exact": all(c["exact_deadline"] for m in metrics_list for c in m["abort_deadline_checks"]),
        "no_hold_exceeds_deadline": all(c["compliant"] for m in metrics_list for c in m["hold_deadline_checks"]),
        "all_resumes_before_deadline": all(r["before_deadline"] for m in metrics_list for r in m["resume_metrics"]),
        "latched_never_resumes": all(m["stop_reference_compliant"] for m in metrics_list),
        "revalidate_drop_stops_without_resume": len(dropped) == 2 and all(m["resumes"] == 0 and m["state"] == "aborted" and len(m["abort_deadline_checks"]) == 1 and m["abort_deadline_checks"][0]["exact_deadline"] for m in dropped),
        "replan_starts_at_measured_hand": bool(replan_resumes) and all(r["replan_start_error_m"] <= thresholds.get("replan_start_tolerance_m", 1e-9) for r in replan_resumes),
        "replan_first_target_E_at_most_1mm": bool(replan_resumes) and all(r["E_m"] <= thresholds.get("first_target_error_max_m", .001) for r in replan_resumes),
        "replan_J_at_most_half_on_all_primary_pairs": len(primary) == 4 and all(pair["jump_half_supported"] for pair in primary),
        "full_strategy_places_in_five_nondrop_conditions": all(cells[(condition, "revalidate", "replan")]["metrics"]["success"] for condition in CONDITIONS - {"gap-and-drop"}),
    }
    metrics = {"kind": "deterministic descriptive factorial ablation; no statistical/generalization claim",
               "definitions": {"unsupported_resumes": "Legacy count: stale latest packet (age>=60ms) OR invalid grasp, independent of the 100ms confirmation window",
                               "full_window_supported_resumes": "Independent count of fresh, valid, post-hold, ordered continuous capture windows spanning>=100ms at resume; includes receipt evaluations",
                               "J_m": "Euclidean first post-resume XYZ target minus last held XYZ target; r+1 versus r",
                               "E_m": "Euclidean first post-resume XYZ target minus measured hand XYZ at resume tick r",
                               "hand_speed": "2ms backward finite difference of measured grip-center XYZ, not instantaneous qvel",
                               "peak_hand_speed_200ms_m_s": "maximum speed over ticks r+1 through r+100 inclusive",
                               "time_to_success_s": "earliest sampled endpoint with >=0.5s uninterrupted valid placement samples after lift; 20ms sampling resolution",
                               "prefix": "state qpos/qvel/ctrl sampled each20ms plus target/measured hand/packets each2ms, through decision tick inclusive",
                               "interpretation": "First-resume same-gate pairs share pre-decision histories. Later resumes are closed-loop totals. Replanning includes retiming; gates change waiting time."},
               "thresholds": thresholds, "episodes": metrics_list, "path_pairs": path_pairs, "gate_pairs": gate_pairs,
               "interaction_effects": interactions, "hypothesis_acceptance": acceptance,
               "all_proposed_criteria_supported": all(acceptance.values())}
    write(out / "metrics.json", metrics)
    report = {"audit_valid": True, "episodes": len(summaries), "raw_episode_files": len(summaries) * len(RAW_FILES),
              "source_hashes_verified": len(manifest["sourceSha256"]), "matched_latched_prefixes": 24,
              "matched_same_gate_prefixes": 12, "max_prefix_abs_error": max(max(p["max_state_abs_error"], p["max_control_abs_error"]) for p in prefixes),
              "verified_resume_records": sum(m["resumes"] for m in metrics_list),
              "valid_revalidation_windows": sum(r["confirmation_window"]["valid"] for m in revalidated for r in m["resume_metrics"]),
              "hypothesis_acceptance": acceptance, "all_proposed_criteria_supported": all(acceptance.values()),
              "prefix_pairs": prefixes, "rawFileSha256": raw_hashes, "metricsSha256": digest(out / "metrics.json"),
              "kind": "independent raw CSV/state/packet audit; no Gate import, controller replay, or independent randomized trials",
              "integrity_scope": "source hashes matched manifest; all raw file digests recorded here; raw digests independently verified if included in manifest"}
    write(out / "audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, help="completed E6 evidence directory")
    args = parser.parse_args()
    try:
        report = audit(args.out.resolve())
    except (AuditError, OSError, KeyError, TypeError, ValueError, StopIteration) as error:
        report = {"audit_valid": False, "error": str(error), "hypothesis_acceptance": None}
        if args.out.is_dir():
            write(args.out / "audit.json", report)
        print(json.dumps(report, indent=2))
        raise SystemExit(1) from error
    print(json.dumps({key: value for key, value in report.items() if key not in ("prefix_pairs", "rawFileSha256")}, indent=2))


if __name__ == "__main__":
    main()
