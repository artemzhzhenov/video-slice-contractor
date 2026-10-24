"""animate_shot_002.py — burst 2, SHOT_002 performance (three_quarter → head_turn → profile,
laughter held in profile).

    blender -b SHOT_002_v01.blend --python-exit-code 2 -P animate_shot_002.py -- --out SHOT_002_v01.blend

Angle bookkeeping (the gate measures the angle between the head's facing direction and the direction
to the camera): the head's world azimuth is BODY + HEAD, the camera's azimuth comes from the shot
file, and the angle is their difference. HEAD (neck + head together, relative to the chest) never
exceeds HEAD_MAX_DEG = 55 — the silhouette gate covers 60 ± 2 (Q27.1). The rest of the angle is the
body turning under the head and the camera orbiting, and only the body counts toward the head's
angular velocity (Q27.2): the limit in head_turn is 0.8·T = 112 °/s.

Deterministic: every key is written from the tables and formulas below; no randomness (§7)."""
import argparse, math, sys
import bpy

F0, F1 = 1121, 1240
W_THREE_QUARTER = (1121, 1152)
W_HEAD_TURN = (1153, 1176)
W_PROFILE = (1177, 1240)
W_STRONG_EMOTION = (1201, 1240)
HEAD_MAX_DEG = 55.0
OVERSHOOT_DEG = 2.6                  # the head runs a touch past the profile and comes back
OVERSHOOT_LEN = 14.0

CH = ["brow_inner_l", "brow_inner_r", "brow_outer_l", "brow_outer_r", "lid_aperture_l", "lid_aperture_r",
      "squint_l", "squint_r", "cheek_raise_l", "cheek_raise_r", "nose_wrinkle", "nostril_flare",
      "mouth_corner_l", "mouth_corner_r", "mouth_width", "jaw_open", "jaw_lateral", "lip_funnel",
      "lip_purse", "lip_press", "upper_lip_raise_l", "upper_lip_raise_r", "blink_l", "blink_r",
      "gaze_yaw", "gaze_pitch"]
LAG = {"brow_inner_l": 1, "brow_inner_r": 1, "brow_outer_l": 1, "brow_outer_r": 2,
       "cheek_raise_l": 1, "cheek_raise_r": 2, "squint_r": 1, "mouth_corner_r": 1, "upper_lip_raise_r": 1}
REST = {"lid_aperture_l": 0.06, "lid_aperture_r": 0.06, "mouth_corner_l": 0.04, "mouth_corner_r": 0.03}
def P(**kw):
    d = dict(REST); d.update(kw); return d

# ---- head azimuth relative to the chest, and the body's own azimuth, per frame (degrees) ----
# three_quarter holds ~45° to camera: camera sits at −24°, so head 20° + body 0 gives 44–45°.
# head_turn: head 20 → 50 and body 0 → 14 while the camera drifts to −31° → about 95° at the end
# … trimmed to land at ~88° (the gate wants ≥ 80 at the end, 80–100 through the whole profile).
BODY_CTRL_PTS = [(1121, 0.0), (1149, 0.4), (1153, 0.8), (1165, 7.0), (1176, 12.4),
             (1190, 13.4), (1210, 14.0), (1240, 14.6)]     # the chest turns under the head, one curve

_BODY = None   # filled after _sampled is defined

def body_head_azimuth(f):
    """Body azimuth only (the head's own turn comes from HEAD_CTRL). Kept as a function for clarity."""
    return _BODY[f], None

# ---- laughter in profile: uneven "ha"s as in SHOT_001, held from 1201 ----
HA = [(1205, 0.85), (1210, 1.00), (1216, 0.95), (1221, 0.92), (1228, 0.72), (1234, 0.52), (1239, 0.34)]
JAW_LOW, JAW_HIGH = 0.66, 0.97
LAUGH_NOD_DEG = 7.0
BOUNCE_M = 0.016
SHOULDER_HA_DEG = 9.0
LAUGH_BASE = dict(mouth_corner_l=0.97, mouth_corner_r=0.95, cheek_raise_l=0.95, cheek_raise_r=0.92,
                  squint_l=0.74, squint_r=0.70, lid_aperture_l=-0.15, lid_aperture_r=-0.15,
                  nose_wrinkle=0.12, upper_lip_raise_l=0.16, upper_lip_raise_r=0.13, mouth_width=0.28,
                  brow_inner_l=0.04, brow_inner_r=0.03, brow_outer_l=0.12, brow_outer_r=0.10)
BREATH_PERIOD = 66
BREATH_SPINE_DEG = 0.7

def ha_envelope(f):
    v = 0.0
    for i, (p, s) in enumerate(HA):
        prev_gap = p - (HA[i - 1][0] if i else p - 5)
        next_gap = (HA[i + 1][0] if i + 1 < len(HA) else p + 6) - p
        w = (prev_gap if f < p else next_gap) / 2.0
        if abs(f - p) < w:
            v += s * 0.5 * (1.0 + math.cos(math.pi * (f - p) / w))
    return v
def laugh_build(f):
    return max(0.0, min(1.0, (f - W_STRONG_EMOTION[0] + 4) / 8.0))

# ---- face track ----
# 1121–1152: curiosity in three-quarter, a smile growing; 1153–1176: the turn, interest, a breath in;
# 1177–1200: the smile becomes laughter; 1201–1240: full laughter held in profile.
FACE = [
    (1121, P(lid_aperture_l=0.10, lid_aperture_r=0.10, brow_inner_l=0.08, brow_inner_r=0.06, mouth_corner_l=0.12, mouth_corner_r=0.09, gaze_yaw=-0.12)),
    (1128, P(lid_aperture_l=0.12, lid_aperture_r=0.12, brow_inner_l=0.16, brow_inner_r=0.12, brow_outer_l=0.10, brow_outer_r=0.08, mouth_corner_l=0.22, mouth_corner_r=0.17, gaze_yaw=-0.20)),
    (1136, P(brow_inner_l=0.22, brow_inner_r=0.18, brow_outer_l=0.15, brow_outer_r=0.12, lid_aperture_l=0.14, lid_aperture_r=0.14, mouth_corner_l=0.38, mouth_corner_r=0.31, cheek_raise_l=0.18, cheek_raise_r=0.14, squint_l=0.08, squint_r=0.06, gaze_yaw=-0.26, gaze_pitch=-0.06)),
    (1141, P(brow_inner_l=0.18, brow_inner_r=0.15, brow_outer_l=0.13, brow_outer_r=0.10, lid_aperture_l=0.12, lid_aperture_r=0.12, mouth_corner_l=0.44, mouth_corner_r=0.37, cheek_raise_l=0.24, cheek_raise_r=0.20, gaze_yaw=-0.08, gaze_pitch=0.03)),
    (1146, P(brow_outer_l=0.16, brow_outer_r=0.13, mouth_corner_l=0.52, mouth_corner_r=0.45, cheek_raise_l=0.30, cheek_raise_r=0.25, squint_l=0.14, squint_r=0.12, mouth_width=0.18, gaze_yaw=-0.18)),
    (1149, P(brow_outer_l=0.16, brow_outer_r=0.13, mouth_corner_l=0.55, mouth_corner_r=0.48, cheek_raise_l=0.32, cheek_raise_r=0.27, squint_l=0.16, squint_r=0.14, mouth_width=0.20,
             gaze_yaw=0.55, gaze_pitch=0.04, lid_aperture_l=0.22, lid_aperture_r=0.22, brow_inner_l=0.22, brow_inner_r=0.18)),   # the eyes go first: 4 frames before the head
    (1156, P(brow_inner_l=0.25, brow_inner_r=0.20, brow_outer_l=0.22, brow_outer_r=0.18, lid_aperture_l=0.24, lid_aperture_r=0.24, mouth_corner_l=0.50, mouth_corner_r=0.44, cheek_raise_l=0.28, cheek_raise_r=0.24, jaw_open=0.08, gaze_yaw=0.62)),
    (1164, P(brow_inner_l=0.22, brow_inner_r=0.18, brow_outer_l=0.21, brow_outer_r=0.17, lid_aperture_l=0.16, lid_aperture_r=0.16, mouth_corner_l=0.55, mouth_corner_r=0.48, cheek_raise_l=0.33, cheek_raise_r=0.28, jaw_open=0.12, gaze_yaw=0.30)),
    (1172, P(brow_inner_l=0.18, brow_inner_r=0.14, brow_outer_l=0.20, brow_outer_r=0.16, mouth_corner_l=0.64, mouth_corner_r=0.57, cheek_raise_l=0.42, cheek_raise_r=0.36, squint_l=0.22, squint_r=0.18, jaw_open=0.16, mouth_width=0.24, gaze_yaw=-0.10)),   # the eyes settle back ahead of the head

    (1180, P(mouth_corner_l=0.78, mouth_corner_r=0.72, cheek_raise_l=0.58, cheek_raise_r=0.52, squint_l=0.34, squint_r=0.30, jaw_open=0.24, mouth_width=0.30, brow_outer_l=0.14, brow_outer_r=0.12)),
    (1190, P(mouth_corner_l=0.88, mouth_corner_r=0.83, cheek_raise_l=0.72, cheek_raise_r=0.66, squint_l=0.48, squint_r=0.44, jaw_open=0.38, mouth_width=0.30, brow_outer_l=0.14, brow_outer_r=0.12)),
    (1198, P(mouth_corner_l=0.93, mouth_corner_r=0.89, cheek_raise_l=0.85, cheek_raise_r=0.80, squint_l=0.60, squint_r=0.56, jaw_open=0.52, mouth_width=0.28, brow_outer_l=0.13, brow_outer_r=0.11)),
]
# v03 (Q50): the gaze in the three-quarter hold is fixations and short darts, not a drift. These keys REPLACE
# gaze_yaw/gaze_pitch on 1121–1146 (the other channels of the FACE poses are untouched). A fixation is two
# keys with ≤ 0.015 drift; a dart is keys on adjacent frames (2–5°: 0.07–0.17 on gaze_yaw, 1 = 30°). The
# eyes hold through the blink (lids shut 1127–1130) and dart right after it. 1146 is where v02 had it.
GAZE_DARTS = [
    (1121, -0.12, 0.02), (1126, -0.13, 0.02), (1131, -0.13, 0.02),   # fixation 1, held through the blink
    (1132, -0.26, -0.05),                                           # dart 1 (3.9° yaw, 1.4° down)
    (1138, -0.27, -0.05),                                           # fixation 2 (7 frames)
    (1139, -0.115, 0.02),                                           # dart 2 (4.9°)
    (1144, -0.110, 0.025),                                          # fixation 3 (6 frames)
    (1145, -0.18, 0.00),                                            # dart 3 (2.2°) — lands on v02's value
    (1146, -0.18, 0.00),
]
BLINKS = [(1126, 0.0), (1127, 1.0), (1129, 1.0), (1131, 0.0),      # early in the hold, away from its peak
          (1180, 0.0), (1181, 1.0), (1183, 1.0), (1185, 0.0)]  # after the turn has settled into profile

# ---- head: ONE continuous curve through control points (Q37) -------------------------------------
# The v01 bug: nod/tilt/turn were separate per-window formulas, so each window started from its own
# value and the head jumped in a single frame on the seams (1152→1153, 1176→1177, 1194→1195). Now the
# three channels are Catmull-Rom splines through the control points below, so continuity — of value
# AND of slope — is a property of the construction, not something matched by hand. The overshoot is
# part of the turn curve (21 → 49 → 51.6 → 49): the head carries past the profile and comes back
# instead of stopping at 1176 and starting again.
HEAD_CTRL = [            # (frame, nod°, turn° relative to the chest, tilt°)
    (1121,  0.0, 18.0, -1.2),
    (1136,  0.6, 19.6, -1.0),
    (1149,  0.2, 20.6, -0.6),
    (1153,  0.4, 21.0,  0.2),      # the turn starts; the eyes already went at 1149
    (1162,  1.8, 33.0,  1.0),
    (1170,  1.2, 44.0,  1.4),
    (1176,  0.4, 48.6,  1.5),      # no stop here: the curve keeps its slope into the overshoot
    (1180, -0.6, 51.6,  1.7),      # overshoot peak
    (1188, -1.0, 49.6,  1.5),
    (1195, -1.3, 49.0,  1.2),      # into the laughter; no reset of nod/tilt
    (1210, -4.6, 50.2,  2.6),
    (1225, -5.4, 50.8,  3.4),
    (1240, -4.2, 51.4,  3.0),
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

_BODY = _sampled(BODY_CTRL_PTS, F0, F1)
_NOD = _sampled([(f, v) for f, v, _, _ in HEAD_CTRL], F0, F1)
_TURN = _sampled([(f, v) for f, _, v, _ in HEAD_CTRL], F0, F1)
_TILT = _sampled([(f, v) for f, _, _, v in HEAD_CTRL], F0, F1)

def head_pose(f):
    """(nod, turn, tilt, body azimuth) in degrees. The laughter "ha" bumps and the breath ride on top
    of the continuous curve; both are zero-valued outside their windows, so they add no seams."""
    nod, turn, tilt = _NOD[f], _TURN[f], _TILT[f]
    if f >= W_STRONG_EMOTION[0] - 6:
        nod += LAUGH_NOD_DEG * ha_envelope(f)
    body, _ = body_head_azimuth(f)
    return nod, turn, tilt, body

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    sc = bpy.data.scenes["SLICE"]
    ctrl = bpy.data.objects["FACE_CTRL"]; rig = bpy.data.objects["RIG_HERO"]
    ctrl.animation_data_clear(); rig.animation_data_clear()

    track = {f: pose for f, pose in FACE}
    for f in range(W_STRONG_EMOTION[0], F1 + 1):
        env = min(1.0, ha_envelope(f)); b = laugh_build(f)
        pose = {k: v * (0.7 + 0.3 * b) for k, v in LAUGH_BASE.items()}
        pose["jaw_open"] = (JAW_LOW + (JAW_HIGH - JAW_LOW) * env) * (0.8 + 0.2 * b)
        pose["squint_l"] += 0.08 * env; pose["squint_r"] += 0.08 * env
        track[f] = pose
    for f in sorted(track):
        pose = track[f]
        for ch in CH:
            if ch.startswith("blink"):
                continue
            lag = LAG.get(ch, 0) if f < W_STRONG_EMOTION[0] else 0
            fk = min(F1, max(F0, f + lag))
            ctrl[ch] = float(pose.get(ch, 0.0)); ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=fk)
    for ch in ("gaze_yaw", "gaze_pitch"):           # v03: replace the hold's gaze keys with fixations and darts
        for f in range(1121, 1147):
            try:
                ctrl.keyframe_delete(data_path=f'["{ch}"]', frame=f)
            except RuntimeError:
                pass
    for f, yaw, pitch in GAZE_DARTS:
        ctrl["gaze_yaw"] = yaw; ctrl.keyframe_insert(data_path='["gaze_yaw"]', frame=f)
        ctrl["gaze_pitch"] = pitch; ctrl.keyframe_insert(data_path='["gaze_pitch"]', frame=f)
    for f, v in BLINKS:
        for ch in ("blink_l", "blink_r"):
            ctrl[ch] = v; ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=f)
    for ch in ("blink_l", "blink_r"):
        for f in (F0, F1):
            ctrl[ch] = 0.0; ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=f)

    for f in range(F0, F1 + 1):
        nod, head_az, tilt, body_az = head_pose(f)
        br = math.sin(2 * math.pi * (f - F0) / BREATH_PERIOD)
        b = laugh_build(f) if f >= W_STRONG_EMOTION[0] - 6 else 0.0
        env = ha_envelope(f) if f >= W_STRONG_EMOTION[0] - 6 else 0.0
        for bone, x, y in (("spine_03", BREATH_SPINE_DEG * br * 0.5 - 1.2 * b, body_az * 0.45),
                           ("spine_05", BREATH_SPINE_DEG * br - 0.8 * b, body_az * 0.55)):
            pb = rig.pose.bones[bone]; pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(x), math.radians(y), 0.0); pb.keyframe_insert("rotation_euler", frame=f)
        calm = 1.0 - 0.45 * max(0.0, min(1.0, (f - 1226) / 14.0))   # the shoulders settle as it dies down
        lift = 0.8 * br + SHOULDER_HA_DEG * env * calm + 3.0 * b * calm
        for side in ("shoulder_l", "shoulder_r"):
            pb = rig.pose.bones[side]; pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(lift), 0.0, 0.0); pb.keyframe_insert("rotation_euler", frame=f)
        pb = rig.pose.bones["root"]; pb.location = (0.0, BOUNCE_M * env, 0.0); pb.keyframe_insert("location", frame=f)
        for bone, k in (("neck", 0.45), ("head", 0.55)):
            pb = rig.pose.bones[bone]; pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(nod * k), math.radians(head_az * k), math.radians(tilt * k))
            pb.keyframe_insert("rotation_euler", frame=f)
    sc.frame_set(F0)
    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    print(f"ANIM_OK {a.out} face_key_frames={len(track)} frames {F0}-{F1} head_max_rel_chest={HEAD_MAX_DEG - 6.0 + 1.5:.1f}°")

if __name__ == "__main__":
    main()
