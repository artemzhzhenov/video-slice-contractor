"""animate_shot_001.py — burst 2, SHOT_001 performance, pass 2 (Q25).

    blender -b SHOT_001_v01.blend --python-exit-code 2 -P animate_shot_001.py -- --out SHOT_001_v01.blend

Pass 2 over pass 1: surprise peaks earlier and the second blink lands on the closing of the mouth
(Q25.2); laughter carried by the shoulders and a whole-body bounce on the root bone — translation,
which does not enter the head's angular velocity — with the spine left as it was (Q25.3); the "ha"s
follow a table of uneven intervals and strengths with a fade at the end (Q25.4); gaze to PROP_A with
the eyes leading and the head following late, lids following the gaze down; per-channel lags for
asymmetry and secondary motion. Pass-1 bug fixed: the shoulders were rotated about Z (forward/back);
the lift axis is X for both sides.

Keys only on FACE_CTRL properties and the RIG_HERO bones root/spine/shoulders/neck/head. Deterministic:
every key comes from the tables and formulas below; no randomness, no time dependence (§7). Default
Bezier interpolation with auto-clamped handles (no Constant keys)."""
import argparse, math, sys
import bpy

F0, F1 = 1001, 1120
CH = ["brow_inner_l", "brow_inner_r", "brow_outer_l", "brow_outer_r", "lid_aperture_l", "lid_aperture_r",
      "squint_l", "squint_r", "cheek_raise_l", "cheek_raise_r", "nose_wrinkle", "nostril_flare",
      "mouth_corner_l", "mouth_corner_r", "mouth_width", "jaw_open", "jaw_lateral", "lip_funnel",
      "lip_purse", "lip_press", "upper_lip_raise_l", "upper_lip_raise_r", "blink_l", "blink_r",
      "gaze_yaw", "gaze_pitch"]
# secondary motion: these channels arrive this many frames after the key that drives them
LAG = {"brow_inner_l": 1, "brow_inner_r": 1, "brow_outer_l": 1, "brow_outer_r": 2,
       "cheek_raise_l": 1, "cheek_raise_r": 2, "squint_r": 1, "mouth_corner_r": 1, "upper_lip_raise_r": 1}
# windows the lag must not push a key out of (state peaks stay inside their window)
WINDOWS = [(1001, 1018), (1019, 1030), (1031, 1036), (1037, 1060), (1061, 1084), (1085, 1120)]

REST = {"lid_aperture_l": 0.06, "lid_aperture_r": 0.06, "mouth_corner_l": 0.04, "mouth_corner_r": 0.03}
def P(**kw):
    d = dict(REST); d.update(kw); return d

# ---- front_neutral 1001–1018: attentive, alive, all channels within ±0.15 ----
NEUTRAL = [
    (1001, P()),
    (1004, P(gaze_yaw=0.05, gaze_pitch=0.02, brow_inner_l=0.06, brow_inner_r=0.05)),
    (1007, P(gaze_yaw=0.05, gaze_pitch=0.02, brow_inner_l=0.08, brow_inner_r=0.07, lid_aperture_l=0.10, lid_aperture_r=0.10)),
    (1010, P(gaze_yaw=-0.06, gaze_pitch=-0.01, brow_inner_l=0.05, brow_inner_r=0.05, mouth_corner_l=0.07, mouth_corner_r=0.06)),
    (1013, P(gaze_yaw=-0.05, gaze_pitch=-0.01, mouth_corner_l=0.08, mouth_corner_r=0.07, lip_press=0.06)),
    (1016, P(gaze_yaw=0.02, gaze_pitch=0.03, brow_outer_l=0.05, brow_outer_r=0.05, lid_aperture_l=0.12, lid_aperture_r=0.12)),
    (1018, P(gaze_yaw=0.03, gaze_pitch=0.02, brow_outer_l=0.06, brow_outer_r=0.06, lid_aperture_l=0.12, lid_aperture_r=0.12)),
]
# ---- gaze_shift 1019–1030: eyes lead to PROP_A (character's left, below), lids follow the gaze down,
#      a small interest in the brows, a return with a slight overshoot ----
GAZE = [
    (1020, P(gaze_yaw=0.06, gaze_pitch=0.01, lid_aperture_l=0.12, lid_aperture_r=0.12)),
    (1022, P(gaze_yaw=0.74, gaze_pitch=-0.47, lid_aperture_l=-0.02, lid_aperture_r=-0.04, brow_inner_l=0.10, brow_inner_r=0.08)),
    (1024, P(gaze_yaw=0.90, gaze_pitch=-0.58, lid_aperture_l=-0.08, lid_aperture_r=-0.10, brow_inner_l=0.20, brow_inner_r=0.15, mouth_corner_l=0.08)),
    (1027, P(gaze_yaw=0.88, gaze_pitch=-0.56, lid_aperture_l=-0.06, lid_aperture_r=-0.08, brow_inner_l=0.22, brow_inner_r=0.16, mouth_corner_l=0.14, mouth_corner_r=0.09)),
    (1029, P(gaze_yaw=-0.07, gaze_pitch=0.03, mouth_corner_l=0.15, mouth_corner_r=0.11, lid_aperture_l=0.10, lid_aperture_r=0.10)),
    (1030, P(gaze_yaw=-0.03, gaze_pitch=0.02, mouth_corner_l=0.15, mouth_corner_r=0.11, lid_aperture_l=0.10, lid_aperture_r=0.10)),
]
BLINK1 = [(1031, 0.0), (1032, 1.0), (1034, 1.0), (1036, 0.0)]
# ---- smile 1037–1060 (approved manner; unchanged values) ----
SMILE = [
    (1037, P(mouth_corner_l=0.18, mouth_corner_r=0.12, cheek_raise_l=0.05, cheek_raise_r=0.03)),
    (1041, P(mouth_corner_l=0.48, mouth_corner_r=0.38, cheek_raise_l=0.22, cheek_raise_r=0.16, mouth_width=0.15, squint_l=0.08, squint_r=0.06)),
    (1046, P(mouth_corner_l=0.86, mouth_corner_r=0.80, cheek_raise_l=0.55, cheek_raise_r=0.50, mouth_width=0.35, squint_l=0.25, squint_r=0.22,
             brow_outer_l=0.12, brow_outer_r=0.10, upper_lip_raise_l=0.12, upper_lip_raise_r=0.10, lid_aperture_l=-0.08, lid_aperture_r=-0.08)),
    (1052, P(mouth_corner_l=0.90, mouth_corner_r=0.86, cheek_raise_l=0.62, cheek_raise_r=0.58, mouth_width=0.40, squint_l=0.30, squint_r=0.28,
             brow_outer_l=0.14, brow_outer_r=0.12, upper_lip_raise_l=0.15, upper_lip_raise_r=0.12, lid_aperture_l=-0.10, lid_aperture_r=-0.10, jaw_open=0.06)),
    (1058, P(mouth_corner_l=0.95, mouth_corner_r=0.92, cheek_raise_l=0.70, cheek_raise_r=0.66, mouth_width=0.45, squint_l=0.34, squint_r=0.32,
             brow_outer_l=0.15, brow_outer_r=0.13, upper_lip_raise_l=0.18, upper_lip_raise_r=0.15, lid_aperture_l=-0.12, lid_aperture_r=-0.12, jaw_open=0.10)),
    (1060, P(mouth_corner_l=0.94, mouth_corner_r=0.91, cheek_raise_l=0.68, cheek_raise_r=0.64, mouth_width=0.44, squint_l=0.32, squint_r=0.30,
             brow_outer_l=0.15, brow_outer_r=0.13, upper_lip_raise_l=0.17, upper_lip_raise_r=0.14, lid_aperture_l=-0.10, lid_aperture_r=-0.10, jaw_open=0.10)),
]
# ---- open_mouth 1061–1084: "oh!" peaks early (1066–1073), the mouth closes into a smile, and the
#      blink lands on the closing mouth (Q25.2) as a reset before the laughter ----
OPEN = [
    (1062, P(mouth_corner_l=0.70, mouth_corner_r=0.66, jaw_open=0.14, brow_inner_l=0.30, brow_inner_r=0.26, brow_outer_l=0.28, brow_outer_r=0.25, lid_aperture_l=0.15, lid_aperture_r=0.15)),
    (1066, P(mouth_corner_l=0.14, mouth_corner_r=0.12, jaw_open=0.80, lip_funnel=0.32, brow_inner_l=0.86, brow_inner_r=0.82, brow_outer_l=0.76, brow_outer_r=0.72, lid_aperture_l=0.58, lid_aperture_r=0.58, nostril_flare=0.25)),
    (1070, P(mouth_corner_l=0.16, mouth_corner_r=0.13, jaw_open=0.76, lip_funnel=0.28, brow_inner_l=0.84, brow_inner_r=0.80, brow_outer_l=0.74, brow_outer_r=0.70, lid_aperture_l=0.55, lid_aperture_r=0.55, nostril_flare=0.20)),
    (1073, P(mouth_corner_l=0.24, mouth_corner_r=0.20, jaw_open=0.71, lip_funnel=0.22, brow_inner_l=0.78, brow_inner_r=0.74, brow_outer_l=0.68, brow_outer_r=0.64, lid_aperture_l=0.48, lid_aperture_r=0.48)),
    (1076, P(mouth_corner_l=0.42, mouth_corner_r=0.37, jaw_open=0.40, brow_inner_l=0.55, brow_inner_r=0.50, brow_outer_l=0.45, brow_outer_r=0.42, lid_aperture_l=0.25, lid_aperture_r=0.25)),
    (1079, P(mouth_corner_l=0.60, mouth_corner_r=0.54, jaw_open=0.16, cheek_raise_l=0.30, cheek_raise_r=0.26, brow_inner_l=0.30, brow_inner_r=0.27, brow_outer_l=0.25, brow_outer_r=0.22)),
    (1082, P(mouth_corner_l=0.72, mouth_corner_r=0.66, jaw_open=0.14, cheek_raise_l=0.45, cheek_raise_r=0.40, squint_l=0.22, squint_r=0.20, brow_outer_l=0.15, brow_outer_r=0.13)),
    (1084, P(mouth_corner_l=0.82, mouth_corner_r=0.76, jaw_open=0.30, cheek_raise_l=0.58, cheek_raise_r=0.52, squint_l=0.34, squint_r=0.30, brow_outer_l=0.12, brow_outer_r=0.10)),
]
BLINK2 = [(1078, 0.0), (1079, 1.0), (1081, 1.0), (1083, 0.0)]
# ---- laughter 1085–1120: onset, then uneven "ha"s (Q25.4), a fade at the end ----
LAUGH_BASE = dict(mouth_corner_l=0.97, mouth_corner_r=0.95, cheek_raise_l=0.95, cheek_raise_r=0.92, squint_l=0.72, squint_r=0.68,
                  lid_aperture_l=-0.15, lid_aperture_r=-0.15, nose_wrinkle=0.12, upper_lip_raise_l=0.16, upper_lip_raise_r=0.13,
                  mouth_width=0.28, brow_inner_l=0.04, brow_inner_r=0.03, brow_outer_l=0.12, brow_outer_r=0.10)
HA = [(1089, 0.80), (1094, 1.00), (1100, 0.95), (1105, 1.00), (1112, 0.78), (1118, 0.60)]   # (peak frame, strength)
JAW_LOW, JAW_HIGH = 0.64, 0.97          # between the "ha"s / at a full-strength "ha"
LAUGH_NOD_DEG = 7.5                      # peak-to-peak nod per full "ha" (raised-cosine bump)
BOUNCE_M = 0.016                         # whole-body lift per full "ha" (root translation, not in T)
SHOULDER_HA_DEG = 9.0                    # shoulder lift per full "ha" (about local X, both sides +)

def ha_envelope(f):
    """Sum of raised-cosine bumps, one per "ha"; each bump spans half the interval to its neighbours."""
    v = 0.0
    for i, (p, s) in enumerate(HA):
        prev_gap = p - (HA[i - 1][0] if i else p - 5)
        next_gap = (HA[i + 1][0] if i + 1 < len(HA) else p + 6) - p
        w = (prev_gap if f < p else next_gap) / 2.0
        if abs(f - p) < w:
            v += s * 0.5 * (1.0 + math.cos(math.pi * (f - p) / w))
    return v
def laugh_build(f):
    return max(0.0, min(1.0, (f - 1085) / 5.0))
def laugh_fade(f):
    return 1.0 - 0.35 * max(0.0, min(1.0, (f - 1112) / 8.0))

BREATH_PERIOD = 66
BREATH_SPINE_DEG = 0.7

# ---- head: ONE continuous curve through control points (Q37) -------------------------------------
# v01 had per-window formulas, so the tilt reset from 0.47° to 0 between front_neutral and gaze_shift
# (1018→1019) — a 7.5 px one-frame jump next to 1.7 px neighbours. Now nod/turn/tilt are Catmull-Rom
# splines through the control points below: continuity of value and slope comes from the construction.
HEAD_CTRL = [            # (frame, nod°, turn°, tilt°)
    (1001,  0.0,  0.0,  0.0),
    (1010,  0.3,  1.1,  0.7),
    (1018,  0.2,  0.9,  0.5),
    (1021,  0.6,  1.8,  0.6),      # head starts following the eyes (they left at 1019)
    (1025,  2.4,  4.4,  1.0),
    (1027,  2.5,  4.5,  1.0),
    (1031,  0.8,  1.4,  0.4),
    (1037,  0.4,  0.0,  0.6),
    (1049,  1.4, -0.9,  3.4),      # smile: warm tilt, chin a touch down
    (1060,  1.5, -1.0,  4.0),
    (1066, -5.4, -0.7,  2.4),      # surprise recoil, tilt eases off
    (1074, -2.2, -0.4,  1.2),
    (1080,  0.4, -0.2,  0.6),
    (1085, -0.8,  0.4,  0.6),      # into the laughter; no reset
    (1095, -5.2,  1.6,  2.6),
    (1110, -6.0,  2.0,  3.4),
    (1120, -5.4,  2.0,  3.0),
]

def _catmull(pts, f):
    """Catmull-Rom through (frame, value) control points; clamped ends, continuous slope."""
    if f <= pts[0][0]:
        return pts[0][1]
    if f >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        f0, v0 = pts[i]; f1, v1 = pts[i + 1]
        if f0 <= f <= f1:
            t = (f - f0) / (f1 - f0)
            vm1 = pts[i - 1][1] if i > 0 else v0 - (v1 - v0)
            vp1 = pts[i + 2][1] if i + 2 < len(pts) else v1 + (v1 - v0)
            m0 = 0.5 * (v1 - vm1); m1 = 0.5 * (vp1 - v0)
            t2, t3 = t * t, t * t * t
            return ((2 * t3 - 3 * t2 + 1) * v0 + (t3 - 2 * t2 + t) * m0 +
                    (-2 * t3 + 3 * t2) * v1 + (t3 - t2) * m1)
    return pts[-1][1]

def _sampled(pts, f0, f1, passes=3):
    """Catmull-Rom sampled per frame, then smoothed 1-2-1 `passes` times. Unevenly spaced control
    points give a continuous VALUE but a discontinuous per-frame step (found by the jump rule on
    v01: 1018→1019 was 0.47° next to 0.09°). The smoothing makes the step continuous too, and the
    end frames are held so the curve still starts and ends where the control points say."""
    vals = [_catmull(pts, f) for f in range(f0, f1 + 1)]
    for _ in range(passes):
        vals = [vals[0]] + [(vals[i - 1] + 2 * vals[i] + vals[i + 1]) / 4 for i in range(1, len(vals) - 1)] + [vals[-1]]
    return {f0 + i: v for i, v in enumerate(vals)}

_NOD = _sampled([(f, v) for f, v, _, _ in HEAD_CTRL], F0, F1)
_TURN = _sampled([(f, v) for f, _, v, _ in HEAD_CTRL], F0, F1)
_TILT = _sampled([(f, v) for f, _, _, v in HEAD_CTRL], F0, F1)

def head_curve(f):
    """neck/head split 40/60; the laughter "ha" nods ride on the continuous curve."""
    nod, turn, tilt = _NOD[f], _TURN[f], _TILT[f]
    if f >= 1085:
        nod += LAUGH_NOD_DEG * ha_envelope(f) * laugh_fade(f)
    return {"neck": (0.4 * nod, 0.4 * turn, 0.4 * tilt), "head": (0.6 * nod, 0.6 * turn, 0.6 * tilt)}

LAUGH_NOD_DEG = 7.5                      # peak-to-peak nod per full "ha" (raised-cosine bump)
BOUNCE_M = 0.016                         # whole-body lift per full "ha" (root translation, not in T)
SHOULDER_HA_DEG = 9.0                    # shoulder lift per full "ha" (about local X, both sides +)

def ha_envelope(f):
    """Sum of raised-cosine bumps, one per "ha"; each bump spans half the interval to its neighbours."""
    v = 0.0
    for i, (p, s) in enumerate(HA):
        prev_gap = p - (HA[i - 1][0] if i else p - 5)
        next_gap = (HA[i + 1][0] if i + 1 < len(HA) else p + 6) - p
        w = (prev_gap if f < p else next_gap) / 2.0
        if abs(f - p) < w:
            v += s * 0.5 * (1.0 + math.cos(math.pi * (f - p) / w))
    return v
def laugh_build(f):
    return max(0.0, min(1.0, (f - 1085) / 5.0))
def laugh_fade(f):
    return 1.0 - 0.35 * max(0.0, min(1.0, (f - 1112) / 8.0))

BREATH_PERIOD = 66
BREATH_SPINE_DEG = 0.7

def window_of(f):
    for a, b in WINDOWS:
        if a <= f <= b:
            return a, b
    return F0, F1

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    sc = bpy.data.scenes["SLICE"]
    ctrl = bpy.data.objects["FACE_CTRL"]; rig = bpy.data.objects["RIG_HERO"]
    ctrl.animation_data_clear(); rig.animation_data_clear()

    track = {}
    for tbl in (NEUTRAL, GAZE, SMILE, OPEN):
        for f, pose in tbl:
            track[f] = pose
    for f in range(1085, F1 + 1):                   # laughter face: dense keys driven by the "ha" table
        env = min(1.0, ha_envelope(f)); b = laugh_build(f); fade = laugh_fade(f)
        pose = {k: v * (0.55 + 0.45 * b) * (1.0 if k.startswith(("mouth_corner", "cheek")) else fade) for k, v in LAUGH_BASE.items()}
        pose["jaw_open"] = (JAW_LOW + (JAW_HIGH - JAW_LOW) * env) * (0.7 + 0.3 * b) * (0.92 + 0.08 * fade)
        pose["squint_l"] = pose["squint_l"] + 0.08 * env; pose["squint_r"] = pose["squint_r"] + 0.08 * env
        track[f] = pose
    for f in sorted(track):
        pose = track[f]
        w0, w1 = window_of(f)
        for ch in CH:
            if ch.startswith("blink"):
                continue
            lag = LAG.get(ch, 0) if f < 1085 else 0          # laughter is already dense
            fk = min(w1, max(w0, f + lag)) if f not in (F0, F1) else f
            ctrl[ch] = float(pose.get(ch, 0.0))
            ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=fk)
    for tbl in (BLINK1, BLINK2):
        for f, v in tbl:
            for ch in ("blink_l", "blink_r"):
                ctrl[ch] = v; ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=f)
    for ch in ("blink_l", "blink_r"):
        for f in (F0, F1):
            ctrl[ch] = 0.0; ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=f)

    for f in range(F0, F1 + 1):                     # body: a key on every frame (uneven "ha"s need it)
        br = math.sin(2 * math.pi * (f - F0) / BREATH_PERIOD)
        b = laugh_build(f) if f >= 1085 else 0.0
        env = ha_envelope(f) * laugh_fade(f) if f >= 1085 else 0.0
        for bone, x in (("spine_03", BREATH_SPINE_DEG * br * 0.5 - 1.5 * b),
                        ("spine_05", BREATH_SPINE_DEG * br - 1.0 * b)):        # spine as in pass 1 (Q25.3)
            pb = rig.pose.bones[bone]; pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(x), 0.0, 0.0); pb.keyframe_insert("rotation_euler", frame=f)
        lift = 0.8 * br + SHOULDER_HA_DEG * env + (3.0 * b if f >= 1085 else 0.0)
        surprise = 2.5 * math.sin(math.pi * max(0.0, min(1.0, (f - 1062) / 10.0))) if 1062 <= f <= 1072 else 0.0
        for side in ("shoulder_l", "shoulder_r"):   # lift = +X on both sides (measured)
            pb = rig.pose.bones[side]; pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(lift + surprise), 0.0, 0.0); pb.keyframe_insert("rotation_euler", frame=f)
        pb = rig.pose.bones["root"]                 # vertical bounce: root's local Y is world up
        pb.location = (0.0, BOUNCE_M * env, 0.0); pb.keyframe_insert("location", frame=f)
        for bone, (x, y, z) in head_curve(f).items():
            pb = rig.pose.bones[bone]; pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
            pb.keyframe_insert("rotation_euler", frame=f)
    sc.frame_set(F0)
    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    print(f"ANIM_OK {a.out} face_key_frames={len(track)} frames {F0}-{F1} pass=2")

if __name__ == "__main__":
    main()
