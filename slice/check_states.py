"""Burst-2 gate "states reached" (contractor/burst-2/ACCEPTANCE.md item 3): every benchmark state
window of a shot, checked against slice/state_requirements.json from the shot's EXPORTS only —
performance_track.json (channels), socket.json and camera.json (head angle to the camera, angular
velocity), lighting_ref.json (the strong-light key), default_head_rest.obj (the head seen on screen
for the jump rule). Two rules cover the whole shot: no freeze, and no single-frame head jump — a
step of the head on screen more than jump_rule's ratio times BOTH neighbouring steps (the
2026-09-24 finding: per-window pose formulas that do not meet at the window boundaries throw the
head by a whole step in one frame, and no other rule sees it). Python with numpy, no Blender:

    .venv/bin/python slice/check_states.py <exports dir> --shot SHOT_002 [--json report.json]
        [--state-map slice/state_map.json] [--requirements slice/state_requirements.json]

Verdict and exit code: STATES_OK (0) — every rule evaluated and met; STATES_PARTIAL (3) — every
evaluated rule met but some rule could not be evaluated (the animator's angular-velocity
threshold T is not declared in state_map.json yet); STATES_FAIL (2) — a rule failed, with the
window, the rule and the measured value. The velocity rules carry the separation margin of
state_requirements.json → velocity_separation (MEDIUM windows ≤ 0.8·T, fast_movement ≥ 1.5·T).
This is a gate against a frozen or timid performance, not a judgement of acting (ACCEPTANCE
item 4 is the human's). Rules marked "human" in the requirements are listed as HUMAN and never
evaluated here."""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())


class StatesError(RuntimeError):
    pass


def load_exports(d):
    d = Path(d)
    track = json.loads((d / "performance_track.json").read_text())
    sock = json.loads((d / "socket.json").read_text())
    cam = json.loads((d / "camera.json").read_text())
    lights = json.loads((d / "lighting_ref.json").read_text())
    centre = lambda f: next(s for s in f["samples"] if s["offset"] == 0.0)  # noqa: E731
    frames = {}
    for tf in track["frames"]:
        frames[tf["frame"]] = {"channels": tf["channels"]}
    for sf in sock["frames"]:
        c = centre(sf)
        m = c["matrix_4x4"]
        frames.setdefault(sf["frame"], {})["face_dir"] = [m[0][2], m[1][2], m[2][2]]
        frames[sf["frame"]]["pos"] = c["position_m"]
        frames[sf["frame"]]["quat"] = c["quaternion"]
        frames[sf["frame"]]["sock_m"] = m
    for cf in cam["frames"]:
        c = centre(cf)
        frames.setdefault(cf["frame"], {})["cam_pos"] = c["position_m"]
        frames[cf["frame"]]["cam_m"] = c.get("extrinsic_matrix_4x4")
        frames[cf["frame"]]["cam_px"] = cf.get("intrinsics", {}).get("px_by_profile", {})
    for fr, f in frames.items():
        if not {"channels", "face_dir", "cam_pos"} <= set(f):
            raise StatesError(f"frame {fr}: performance_track / socket / camera do not cover the same frames")
        a, b = f["face_dir"], [f["cam_pos"][i] - f["pos"][i] for i in range(3)]
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
        f["head_angle_deg"] = math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))))
    order = sorted(frames)
    fps = track["fps"]
    for i, fr in enumerate(order):
        q0, q1 = frames[fr]["quat"], frames[order[min(i + 1, len(order) - 1)]]["quat"]
        dot = min(1.0, abs(sum(x * y for x, y in zip(q0, q1))))
        frames[fr]["ang_vel_deg_s"] = math.degrees(2 * math.acos(dot)) * fps if i + 1 < len(order) else frames[order[i - 1]]["ang_vel_deg_s"] if i else 0.0
    obj = d / "default_head_rest.obj"
    head_rest = np.asarray([[float(t) for t in ln.split()[1:4]] for ln in obj.read_text().splitlines() if ln.startswith("v ")]) if obj.exists() else None
    return frames, order, lights, fps, head_rest


def rot_between_deg(qa, qb):
    return math.degrees(2 * math.acos(min(1.0, abs(sum(x * y for x, y in zip(qa, qb))))))


def head_steps_px(frames, order, head_rest, profile):
    """Screen step of the head between consecutive frames (state_requirements.json → jump_rule):
    the median over the rest head's vertices of their displacement when the head is placed by the
    earlier and by the later frame's socket, both seen through the later frame's camera — the
    head's own motion, not the camera's. Pinhole as slice/camera_model.project (camera −Z forward,
    v down)."""
    V = np.c_[head_rest, np.ones(len(head_rest))].T

    def screen(sock_m, cam_m, px):
        c = (np.linalg.inv(np.asarray(cam_m, float)) @ (np.asarray(sock_m, float) @ V))[:3]
        depth = -c[2]
        if (depth <= 0).any():
            raise StatesError("a head vertex is at or behind the camera — the exports are inconsistent")
        (fx, fy), (cx, cy) = px["focal_length_px"], px["principal_point_px"]
        return np.stack([cx + fx * c[0] / depth, cy - fy * c[1] / depth], 1)
    steps = []
    for a, b in zip(order, order[1:]):
        cam_m, px = frames[b]["cam_m"], frames[b]["cam_px"][profile]
        steps.append(float(np.median(np.linalg.norm(screen(frames[b]["sock_m"], cam_m, px) - screen(frames[a]["sock_m"], cam_m, px), axis=1))))
    return steps


def jump_rule(frames, order, head_rest, jr):
    """The global "no single-frame head jump" rule as a report entry."""
    ratio_max, floor, profile = jr["ratio_over_both_neighbours_max"], jr["floor_px"], jr["profile"]
    name = f"no single-frame head jump (a screen step > {ratio_max:g}× both neighbouring steps and > {floor:g} px, {profile} profile)"
    if head_rest is None or not len(head_rest):
        return {"rule": name, "status": "NOT_EVALUATED", "measured": "default_head_rest.obj missing from the exports"}
    if any(frames[fr].get("cam_m") is None or profile not in (frames[fr].get("cam_px") or {}) for fr in order):
        return {"rule": name, "status": "NOT_EVALUATED", "measured": f"camera.json carries no extrinsic matrix or no '{profile}' pixel intrinsics"}
    steps = head_steps_px(frames, order, head_rest, profile)
    jumps, others = [], []
    for i, s in enumerate(steps):
        adj = max(steps[j] for j in (i - 1, i + 1) if 0 <= j < len(steps))
        e = {"frames": f"{order[i]}→{order[i + 1]}", "step_px": round(s, 2), "neighbours_max_px": round(adj, 2), "ratio": round(s / max(adj, 1e-9), 2)}
        (jumps if e["ratio"] > ratio_max and s > floor else others).append(e)
    above_floor = [e for e in others if e["step_px"] > floor]
    measured = {"jumps": jumps, "highest_ratio_elsewhere_above_floor": max(above_floor, key=lambda e: e["ratio"]) if above_floor else None,
                "step_px_median": round(float(np.median(steps)), 2), "step_px_max": round(max(steps), 2)}
    return {"rule": name, "status": "FAIL" if jumps else "PASS", "measured": measured}


def evaluate_window(state, spec, ranges, frames, lights, T, sep):
    """One state's windows against its requirement block. Returns a list of rule results."""
    results = []
    win = [fr for a, b in ranges for fr in range(a, b + 1) if fr in frames]
    missing = [fr for a, b in ranges for fr in range(a, b + 1) if fr not in frames]
    if missing:
        return [{"rule": "window_in_exports", "status": "FAIL", "measured": f"frames missing from the exports: {missing[:5]}…"}]
    ch = lambda fr, c: frames[fr]["channels"][c]  # noqa: E731

    def res(rule, ok, measured, status=None):
        results.append({"rule": rule, "status": status or ("PASS" if ok else "FAIL"), "measured": measured})

    for kind, rule in spec.items():
        if kind == "human":
            results.append({"rule": "human", "status": "HUMAN", "measured": rule})
        elif kind == "peak":
            for c, v in rule.get("min", {}).items():
                m = max(ch(fr, c) for fr in win); res(f"peak {c} ≥ {v}", m >= v, round(m, 4))
            for c, v in rule.get("max", {}).items():
                m = min(ch(fr, c) for fr in win); res(f"peak {c} ≤ {v}", m <= v, round(m, 4))
            if "any_abs_min" in rule:
                m = {c: max(abs(ch(fr, c)) for fr in win) for c in rule["any_abs_min"]}
                res("peak any of " + ", ".join(f"|{c}| ≥ {v}" for c, v in rule["any_abs_min"].items()), any(m[c] >= v for c, v in rule["any_abs_min"].items()), {c: round(x, 4) for c, x in m.items()})
        elif kind == "peak_per_window":
            for a, b in ranges:
                sub = [fr for fr in win if a <= fr <= b]
                for c, v in rule.get("min", {}).items():
                    m = max(ch(fr, c) for fr in sub); res(f"peak {c} ≥ {v} in {a}–{b}", m >= v, round(m, 4))
        elif kind == "all_frames":
            if "abs_channels_max" in rule:
                m = max(abs(ch(fr, c)) for fr in win for c in frames[fr]["channels"])
                res(f"all frames |channel| ≤ {rule['abs_channels_max']}", m <= rule["abs_channels_max"], round(m, 4))
            if "head_angle_deg_max" in rule:
                m = max(frames[fr]["head_angle_deg"] for fr in win)
                res(f"all frames head angle ≤ {rule['head_angle_deg_max']}°", m <= rule["head_angle_deg_max"], round(m, 2))
            if "head_angle_deg_range" in rule:
                lo, hi = rule["head_angle_deg_range"]
                mn, mx = min(frames[fr]["head_angle_deg"] for fr in win), max(frames[fr]["head_angle_deg"] for fr in win)
                res(f"all frames head angle in [{lo}, {hi}]°", lo <= mn and mx <= hi, [round(mn, 2), round(mx, 2)])
            if "head_rotation_from_window_start_deg_max" in rule:
                q0 = frames[win[0]]["quat"]
                m = max(rot_between_deg(q0, frames[fr]["quat"]) for fr in win)
                res(f"all frames head rotation from window start ≤ {rule['head_rotation_from_window_start_deg_max']}°", m <= rule["head_rotation_from_window_start_deg_max"], round(m, 2))
        elif kind == "hold":
            lo, hi = rule["head_angle_deg_range"]
            best = run = 0
            for fr in win:
                run = run + 1 if lo <= frames[fr]["head_angle_deg"] <= hi else 0
                best = max(best, run)
            res(f"head angle in [{lo}, {hi}]° for ≥ {rule['min_consecutive_frames']} consecutive frames", best >= rule["min_consecutive_frames"], best)
        elif kind == "endpoints":
            a0, a1 = frames[win[0]]["head_angle_deg"], frames[win[-1]]["head_angle_deg"]
            res(f"head angle at window start ≤ {rule['head_angle_deg_at_start_max']}°", a0 <= rule["head_angle_deg_at_start_max"], round(a0, 2))
            res(f"head angle at window end ≥ {rule['head_angle_deg_at_end_min']}°", a1 >= rule["head_angle_deg_at_end_min"], round(a1, 2))
        elif kind == "velocity":
            m = max(frames[fr]["ang_vel_deg_s"] for fr in win)
            if T is None:
                res("angular velocity vs T", False, f"T not declared in state_map.json (max measured {m:.1f}°/s)", status="NOT_EVALUATED")
            elif "max_deg_s" in rule:
                lim = sep["medium_max_over_T"] * T
                res(f"angular velocity ≤ {sep['medium_max_over_T']}·T = {lim:g}°/s on every frame", m <= lim, round(m, 2))
            else:
                lim = sep["fast_peak_over_T_min"] * T
                res(f"angular velocity ≥ {sep['fast_peak_over_T_min']}·T = {lim:g}°/s on some frame", m >= lim, round(m, 2))
        elif kind == "lighting":
            ok_lights = []
            for L in lights["lights"]:
                rgb = L["colour_rgb_linear"]
                ratio = (max(rgb) / min(rgb)) if min(rgb) > 0 else float("inf")
                ok_lights.append((L["name"], round(ratio, 3)))
            enough = len(lights["lights"]) >= rule["min_lights"]
            coloured = any(r >= rule["colour_ratio_max_over_min_min"] for _, r in ok_lights)
            res(f"≥ {rule['min_lights']} light(s) in C_LIGHTS", enough, len(lights["lights"]))
            res(f"a light with max/min RGB ≥ {rule['colour_ratio_max_over_min_min']}", coloured, ok_lights)
        else:
            raise StatesError(f"{state}: unknown rule kind {kind}")
    return results


def check(exports, shot, smap, reqs):
    frames, order, lights, fps, head_rest = load_exports(exports)
    T = smap.get("head_angular_velocity_threshold_deg_s")
    sep = reqs["velocity_separation"]
    if T is not None and not (isinstance(T, (int, float)) and T > 0):
        raise StatesError(f"state_map.json head_angular_velocity_threshold_deg_s must be a positive number, got {T!r}")
    windows = [w for w in smap["windows"] if w["shot_id"] == shot]
    if not windows:
        raise StatesError(f"state_map.json has no windows for {shot}")
    tier_of = {s: t for t, ss in smap["tiers"].items() for s in ss}
    report = {"shot": shot, "frames": [order[0], order[-1]], "fps": fps, "T_deg_s": T, "velocity_separation": {k: sep[k] for k in ("medium_max_over_T", "fast_peak_over_T_min")}, "windows": [], "global": []}
    for w in windows:
        spec = reqs["states"].get(w["state"])
        if spec is None:
            raise StatesError(f"no requirement block for state {w['state']}")
        rules = evaluate_window(w["state"], spec, w["frames"], frames, lights, T, sep)
        if tier_of.get(w["state"]) == "MEDIUM":
            win = [fr for a, b in w["frames"] for fr in range(a, b + 1) if fr in frames]
            m = max(frames[fr]["ang_vel_deg_s"] for fr in win) if win else 0.0
            if T is None:
                rules.append({"rule": "MEDIUM window: angular velocity ≤ T", "status": "NOT_EVALUATED", "measured": f"T not declared (max measured {m:.1f}°/s)"})
            else:
                lim = sep["medium_max_over_T"] * T
                rules.append({"rule": f"MEDIUM window: angular velocity ≤ {sep['medium_max_over_T']}·T = {lim:g}°/s", "status": "PASS" if m <= lim else "FAIL", "measured": round(m, 2)})
        report["windows"].append({"state": w["state"], "tier": tier_of.get(w["state"]), "frames": w["frames"], "rules": rules})
    fz = reqs["freeze_rule"]
    run, best, best_at = 0, 0, None
    for i in range(1, len(order)):
        a, b = frames[order[i - 1]], frames[order[i]]
        dch = max(abs(a["channels"][c] - b["channels"][c]) for c in a["channels"])
        dpos = max(abs(x - y) for x, y in zip(a["pos"], b["pos"]))
        dq = max(abs(x - y) for x, y in zip(a["quat"], b["quat"]))
        if dch <= fz["channel_epsilon"] and dpos <= fz["socket_position_epsilon_m"] and dq <= fz["socket_quaternion_epsilon"]:
            run += 1
            if run > best:
                best, best_at = run, order[i]
        else:
            run = 0
    report["global"].append({"rule": f"no freeze longer than {fz['max_frames_without_change']} frames (no channel, socket position or rotation change)", "status": "PASS" if best <= fz["max_frames_without_change"] else "FAIL", "measured": {"longest_frozen_run": best, "ending_at_frame": best_at}})
    report["global"].append(jump_rule(frames, order, head_rest, reqs["jump_rule"]))
    statuses = [r["status"] for w in report["windows"] for r in w["rules"]] + [g["status"] for g in report["global"]]
    report["counts"] = {s: statuses.count(s) for s in ("PASS", "FAIL", "NOT_EVALUATED", "HUMAN")}
    report["status"] = "FAIL" if "FAIL" in statuses else ("PARTIAL" if "NOT_EVALUATED" in statuses else "OK")
    return report


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("exports")
    p.add_argument("--shot", required=True)
    p.add_argument("--json", default="")
    p.add_argument("--state-map", default=str(ROOT / "slice" / "state_map.json"))
    p.add_argument("--requirements", default=str(ROOT / "slice" / "state_requirements.json"))
    args = p.parse_args(argv)
    report = check(args.exports, args.shot, json.loads(Path(args.state_map).read_text()), json.loads(Path(args.requirements).read_text()))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1) + "\n")
    for w in report["windows"]:
        for r in w["rules"]:
            if r["status"] in ("FAIL", "NOT_EVALUATED"):
                print(f"STATES_{r['status']} {w['state']} {w['frames']}: {r['rule']} — {r['measured']}")
    for g in report["global"]:
        if g["status"] in ("FAIL", "NOT_EVALUATED"):
            shown = g["measured"]["jumps"] if isinstance(g["measured"], dict) and "jumps" in g["measured"] else g["measured"]
            print(f"STATES_{g['status']} global: {g['rule']} — {shown}")
    c = report["counts"]
    print(f"STATES_{report['status']} {args.shot} windows={len(report['windows'])} pass={c['PASS']} fail={c['FAIL']} not_evaluated={c['NOT_EVALUATED']} human={c['HUMAN']}")
    return {"OK": 0, "PARTIAL": 3, "FAIL": 2}[report["status"]]


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except StatesError as e:
        print(f"STATES_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
