"""animate_shot_003.py — burst 2, SHOT_003: sadness → fear → hand over the eyes → a fast turn away.

    blender -b SHOT_003_v02.blend --python-exit-code 2 -P animate_shot_003.py -- --out SHOT_003_v02.blend

Everything that moves is ONE continuous curve per channel: Catmull-Rom through the control points
below, sampled per frame, smoothed 1-2-1 three times. Per-window formulas and per-window constants
produced the one-frame jumps in SHOT_001/002 v01 (Q37) and again a 12 mm socket jump at 1333 in this
shot's first pass (a body-lean constant switched off at the window edge) — so there are none here.
Deterministic: no randomness, no time dependence (§7).

Windows and what each must reach (slice/state_requirements.json v2):
  sadness        1241–1272  brow_inner ≥ 0.7, mouth_corner ≤ −0.6, gaze_pitch ≤ −0.3, head 35–55° to camera
  fear           1273–1304  brow_inner ≥ 0.9, lid_aperture ≥ 0.8, jaw_open ≥ 0.4, head 35–55°
  hand_over_face 1305–1332  lid_aperture ≤ −0.5, head 35–55°, the hand covers 1/5…1/2 of the head
  fast_movement  1333–1360  head angular velocity ≥ 210 °/s (1.5·T, T = 140)

The three-quarter angle comes from the camera (make_shot_003.py), so the girl can stand freely.
The hand poses were SOLVED numerically on four frames of the hold (1308, 1314, 1320, 1326) against a
target at the eyes with the palm turned to the face — the palm direction taken from the hand's own
principal plane, since a closed mesh's mean normal is zero. Solving a single frame let the hand slide
off the eyes: 0.20 → 0.12 → 0.11 of the head silhouette (Q40)."""
import argparse
import math
import sys

import bpy

F0, F1 = 1241, 1360
MIRROR = -1.0     # Q44: the camera is mirrored to the character's left; the performance mirrors with it —
                  # every yaw-type channel (head turn, tilt, body azimuth, gaze_yaw) changes sign, so the
                  # geometry relative to the camera is the one accepted in Q41 (angles equal in magnitude)
W_SAD, W_FEAR, W_HAND, W_FAST = (1241, 1272), (1273, 1304), (1305, 1332), (1333, 1360)

CH = ["brow_inner_l", "brow_inner_r", "brow_outer_l", "brow_outer_r", "lid_aperture_l", "lid_aperture_r",
      "squint_l", "squint_r", "cheek_raise_l", "cheek_raise_r", "nose_wrinkle", "nostril_flare",
      "mouth_corner_l", "mouth_corner_r", "mouth_width", "jaw_open", "jaw_lateral", "lip_funnel",
      "lip_purse", "lip_press", "upper_lip_raise_l", "upper_lip_raise_r", "blink_l", "blink_r",
      "gaze_yaw", "gaze_pitch"]
LAG = {"brow_outer_l": 1, "brow_outer_r": 2, "cheek_raise_r": 1, "mouth_corner_r": 1, "squint_r": 1}
REST = {"lid_aperture_l": 0.05, "lid_aperture_r": 0.05}


def P(**kw):
    d = dict(REST)
    d.update(kw)
    return d


FACE = [
    # ---- sadness: the corners fall first, then the inner brows climb, the gaze sinks ----
    (1241, P(brow_inner_l=0.20, brow_inner_r=0.18, mouth_corner_l=-0.15, mouth_corner_r=-0.12, gaze_pitch=-0.10, lip_press=0.15)),
    (1249, P(brow_inner_l=0.45, brow_inner_r=0.40, brow_outer_l=-0.20, brow_outer_r=-0.18, mouth_corner_l=-0.42, mouth_corner_r=-0.36, gaze_pitch=-0.28, lip_press=0.25, lid_aperture_l=-0.10, lid_aperture_r=-0.10)),
    (1258, P(brow_inner_l=0.74, brow_inner_r=0.70, brow_outer_l=-0.28, brow_outer_r=-0.25, mouth_corner_l=-0.66, mouth_corner_r=-0.62, gaze_pitch=-0.40, lip_press=0.30, lid_aperture_l=-0.16, lid_aperture_r=-0.16, mouth_width=-0.15)),
    (1266, P(brow_inner_l=0.78, brow_inner_r=0.74, brow_outer_l=-0.30, brow_outer_r=-0.27, mouth_corner_l=-0.70, mouth_corner_r=-0.66, gaze_pitch=-0.42, lip_press=0.28, lid_aperture_l=-0.14, lid_aperture_r=-0.14, mouth_width=-0.18)),
    (1272, P(brow_inner_l=0.72, brow_inner_r=0.68, brow_outer_l=-0.22, brow_outer_r=-0.20, mouth_corner_l=-0.55, mouth_corner_r=-0.50, gaze_pitch=-0.30, lid_aperture_l=0.05, lid_aperture_r=0.05)),
    # ---- fear: something off-camera; the eyes snap wide, the mouth opens ----
    (1277, P(brow_inner_l=0.86, brow_inner_r=0.82, brow_outer_l=0.20, brow_outer_r=0.16, lid_aperture_l=0.62, lid_aperture_r=0.60, jaw_open=0.24, gaze_pitch=0.10, gaze_yaw=-0.35, mouth_corner_l=-0.30, mouth_corner_r=-0.26)),
    (1286, P(brow_inner_l=0.96, brow_inner_r=0.94, brow_outer_l=0.30, brow_outer_r=0.26, lid_aperture_l=0.92, lid_aperture_r=0.90, jaw_open=0.52, gaze_pitch=0.12, gaze_yaw=-0.55, mouth_corner_l=-0.22, mouth_corner_r=-0.18, nostril_flare=0.35)),
    (1292, P(brow_inner_l=0.95, brow_inner_r=0.93, brow_outer_l=0.28, brow_outer_r=0.24, lid_aperture_l=0.88, lid_aperture_r=0.86, jaw_open=0.48, gaze_pitch=0.08, gaze_yaw=-0.48, nostril_flare=0.30, mouth_corner_l=-0.24, mouth_corner_r=-0.20)),
    # the lids start closing while the hand comes up — inside `fear`, after its peak
    (1299, P(brow_inner_l=0.90, brow_inner_r=0.88, brow_outer_l=0.18, brow_outer_r=0.15, lid_aperture_l=0.35, lid_aperture_r=0.32, jaw_open=0.40, gaze_pitch=-0.10, gaze_yaw=-0.30, nostril_flare=0.25, mouth_corner_l=-0.30, mouth_corner_r=-0.26)),
    (1304, P(brow_inner_l=0.86, brow_inner_r=0.84, lid_aperture_l=-0.10, lid_aperture_r=-0.12, jaw_open=0.30, gaze_pitch=-0.25, mouth_corner_l=-0.36, mouth_corner_r=-0.32, nose_wrinkle=0.15)),
    # ---- hand over the eyes: shut tight, the face braces ----
    (1310, P(brow_inner_l=0.82, brow_inner_r=0.80, lid_aperture_l=-0.62, lid_aperture_r=-0.64, jaw_open=0.22, mouth_corner_l=-0.40, mouth_corner_r=-0.36, nose_wrinkle=0.28, squint_l=0.30, squint_r=0.28, lip_press=0.30)),
    (1320, P(brow_inner_l=0.80, brow_inner_r=0.78, lid_aperture_l=-0.70, lid_aperture_r=-0.72, jaw_open=0.18, mouth_corner_l=-0.44, mouth_corner_r=-0.40, nose_wrinkle=0.32, squint_l=0.34, squint_r=0.32, lip_press=0.34)),
    (1330, P(brow_inner_l=0.78, brow_inner_r=0.76, lid_aperture_l=-0.58, lid_aperture_r=-0.60, jaw_open=0.20, mouth_corner_l=-0.40, mouth_corner_r=-0.36, nose_wrinkle=0.26, squint_l=0.28, squint_r=0.26, lip_press=0.30)),
    # ---- the turn away: she tears free, the eyes open mid-turn ----
    (1337, P(brow_inner_l=0.84, brow_inner_r=0.82, lid_aperture_l=0.10, lid_aperture_r=0.08, jaw_open=0.30, mouth_corner_l=-0.34, mouth_corner_r=-0.30, gaze_yaw=0.30)),
    (1344, P(brow_inner_l=0.88, brow_inner_r=0.86, brow_outer_l=0.20, brow_outer_r=0.17, lid_aperture_l=0.55, lid_aperture_r=0.52, jaw_open=0.38, mouth_corner_l=-0.28, mouth_corner_r=-0.24, gaze_yaw=0.55, nostril_flare=0.25)),
    (1352, P(brow_inner_l=0.80, brow_inner_r=0.78, brow_outer_l=0.14, brow_outer_r=0.12, lid_aperture_l=0.40, lid_aperture_r=0.38, jaw_open=0.26, mouth_corner_l=-0.26, mouth_corner_r=-0.22, gaze_yaw=0.35)),
    (1360, P(brow_inner_l=0.72, brow_inner_r=0.70, lid_aperture_l=0.22, lid_aperture_r=0.20, jaw_open=0.16, mouth_corner_l=-0.24, mouth_corner_r=-0.20, gaze_yaw=0.20)),
]
BLINKS = [(1269, 0.0), (1270, 1.0), (1272, 1.0), (1274, 0.0)]      # a slow sad blink before the fear hit

HEAD_CTRL = [            # (frame, nod° (+ down), turn° relative to the chest, tilt°)
    (1241,  6.0,   4.0,  3.0),
    (1258,  9.5,   2.0,  4.5),
    (1272,  8.0,   3.0,  4.0),
    (1277,  1.0,  -2.0,  2.0),
    (1286, -5.0,  -2.0,  1.0),
    (1292, -4.0,  -1.5,  1.2),
    (1300,  3.0,   0.0,  3.0),
    (1305,  6.0,   1.0,  4.6),      # into the hold: from here to 1332 the head is (almost) still relative
    (1318,  6.2,   1.0,  4.8),      # to the chest — it hides in the palm; the spine carries the life
    (1332,  6.0,   1.2,  4.6),
    (1333,  6.0,   1.2,  4.6),      # the head holds one frame longer: smoothing spread the turn start onto 1333
    (1335,  6.2,   2.6,  4.4),      # and the leaving hand met the head there (clearance −1.9 mm)
    (1337,  3.0,  16.0,  3.0),
    (1340, -1.0,  36.0,  0.5),
    (1343, -3.0,  50.0, -1.8),
    (1346, -2.2,  55.0, -2.5),      # head vs chest stays ≤ 55° (silhouette gate covers 60 ± 2)
    (1352,  0.0,  51.0, -1.2),
    (1360,  1.0,  48.0,  0.0),
]
BODY_CTRL = [(1241, -2.0), (1272, -2.5), (1286, -4.0), (1310, -5.0), (1332, -4.0),
             (1335, -1.0), (1339, 12.0), (1343, 24.0), (1348, 28.0), (1360, 29.0)]
LEAN_CTRL = [(1241, 1.0), (1258, 1.5), (1272, 1.3), (1286, 0.7), (1300, 0.9), (1310, 1.4),
             (1318, 1.0), (1326, 1.5), (1334, 0.8), (1342, 0.1), (1360, 0.0)]   # the spine breathes and sways on the hold
SHOULDER_CTRL = [(1241, 1.5), (1258, 2.5), (1272, 2.0), (1286, 6.5), (1300, 5.0),
                 (1310, 7.5), (1320, 8.0), (1332, 6.5), (1344, 3.0), (1360, 1.5)]
ARM_CTRL = {
    "shoulder_l":   [(1241, -4, 0, 0), (1272, -5, 0, 0), (1290, -3, 0, -2)],   # frozen on the hold: it is in the arm chain
    "shoulder_r":   [(1241, -4, 0, 0), (1258, -6, 0, 0), (1272, -5, 0, 0), (1286, 1, 0, 0),
                     (1300, 0, 0, 0), (1320, 0, 0, 0), (1360, -2, 0, 0)],
    # near arm: rest → HOLD → release. The hold is written as CONSTANT values (see hold_sample):
    # Catmull-Rom between identical keys bows toward its neighbours (owner measured −2.5…+4.8° on
    # upperarm01.L across a two-key hold) — that, not too few keys, was the 0.20 → 0.08 slide (Q41).
    "upperarm01.L": [(1241, 6, 0, -14), (1272, 7, 0, -17), (1290, 14, 4, -24)],   # 1290 key: the +60 Z was left from before the mirror and threw the arm out on 1286   # Z sign mirrored vs the right arm: measured 58° from vertical with +12, target 20–24°
    "upperarm02.L": [(1241, 0, 0, 0), (1290, 0, -4, 0)],
    "lowerarm01.L": [(1241, -10, 0, 0), (1272, -12, 0, 0), (1290, -40, 0, 0)],
    "lowerarm02.L": [(1241, 0, 0, 0), (1290, 0, -8, 0)],
    "wrist.L":      [(1241, 0, 0, 0), (1290, 14, 0, -20)],
    # far arm: out of the A-pose and alive for the whole shot (owner, Q39.3)
    "upperarm01.R": [(1241, 6, 0, 14), (1258, 8, 0, 17), (1272, 7, 0, 15), (1286, 16, 0, 26), (1300, 14, 0, 24),
                     (1320, 13, 0, 23), (1344, 10, 0, 20), (1360, 8, 0, 17)],
    "lowerarm01.R": [(1241, -10, 0, 0), (1258, -14, 0, 0), (1272, -12, 0, 0), (1286, -40, 0, 0), (1300, -36, 0, 0),
                     (1320, -34, 0, 0), (1344, -26, 0, 0), (1360, -20, 0, 0)],
    "wrist.R":      [(1241, 0, 0, 0), (1286, -8, 0, 6), (1320, -6, 0, 5), (1360, -2, 0, 2)],
}
# The hold: one pose, solved against the eyes with the palm to the face (hand_hold.py), written as
# constants on every frame of the window. HOLD_IN/HOLD_OUT: smoothstep from the last curve value into
# the pose and back out (zero speed at both edges of the hold).
# solved against the HAND MESH CENTROID (not the wrist bone: the wrist at the eyes left the palm and
# fingers past the head silhouette — 0.03 covered), palm to the face 0.95, centroid 8 mm off target
# The gesture (owner, Q43 option 1): from below and in front — the elbow below the shoulder joint and
# forward at chest height, the forearm rising diagonally, the palm over the near eye, fingers to the far
# temple. Posed under ANATOMY AS HARD CONSTRAINTS (elbow ≥ 20 mm below the shoulder and forward of it,
# elbow 30–180°, wrist ≤ 45°, forearm and hand ≥ 5 mm outside the head skin, hair and brows); among the
# poses that satisfy them the one closest to 12 mm from the face with the palm turned to it. At the
# pose: elbow 97°, wrist 30°, near eye hidden 97 %, no hand vertex behind head/hair/brows from the
# camera, clearance skin 39 mm / hair 16 mm / brows 31 mm (the closest thing to the hand is the hair).
# The numbers are a check, not the target: the previous holds (solved on a number alone) put the
# forearm through the head and the hand under the skin — Q43.
HOLD = {"shoulder_l": (-2, 0, -4),   # Q48 table E: the anatomical hold (owner, 28.09); shoulder_l kept
        "upperarm01.L": (61.094, -47.871, 5.086),
        "upperarm02.L": (0.0, 0.0, 0.0),
        "lowerarm01.L": (73.051, 0.0, 0.0),
        "lowerarm02.L": (0.0, -75.0, 0.0),
        "wrist.L": (-15.0, 0.0, 30.0),
}                                             # camera (+45°, the owner's was +33°)
# Transitions: the straight path hold → rest passes through the head (321 of 425 forearm/hand points inside on
# 1335 in the first pass), so both go through a VIA pose with the elbow out and the forearm open to the side.
VIA_IN = {"shoulder_l": (-2, 0, -4), "upperarm01.L": (122, 31.3, -150), "upperarm02.L": (0, -16, 0),
          "lowerarm01.L": (-140, 0, 0), "lowerarm02.L": (0, 16, 0), "wrist.L": (-30, 0, 10)}
VIA_OUT = {"shoulder_l": (-2, 0, -3), "upperarm01.L": (70, 20, -90), "upperarm02.L": (0, -10, 0),
           "lowerarm01.L": (-125, 0, 0), "lowerarm02.L": (0, 10, 0), "wrist.L": (-20, 0, 6)}
# release: the upper arm drops FIRST with the elbow still bent, the elbow opens last — the straight
# hold → rest interpolation opened the elbow while the arm was still up and flung it out on 1338
VIA_OUT_FRAME = 1348          # the upper arm is down at the via pose here; the elbow opens after it
# both via poses searched for a path (5 steps per leg) with no forearm/hand point inside the head skin,
# with the head where it is on those frames (1300 for the approach, 1340 for the release — the fast turn)
RELEASE = {"shoulder_l": (-3, 0, 0), "upperarm01.L": (10, 0, -12), "upperarm02.L": (0, 0, 0),
           "lowerarm01.L": (-50, 0, 0), "lowerarm02.L": (0, 0, 0), "wrist.L": (0, 0, 0)}   # elbow a little bent at the end: less travel
HOLD_IN = (1274, 1305)
VIA_IN_FRAME = 1300           # the long leg (rest → via) gets 26 frames, the short one (via → hold) 5: wrist ≤ 80 mm/frame         # approach: from the fear pose at 1296 into the hold by 1305
HOLD_OUT = (1335, 1360)        # release starts once the head is already turning AWAY from the hand; the
                               # window 1305–1332 stays constant — the pose simply holds two frames longer
# One hand pose, constant for the whole shot, on both hands (Q46.1): the rig's rest hand is straight and
# splayed (thumb 51° off the index, first-knuckle curl 10°, index–pinky 33°) and reads as "four fingers".
# Axes were measured per bone, not guessed (finger_axes.py): curl = X on the middle phalanx, the thumb and
# the splay close on Z; the right hand mirrors Z. Measured on this pose: thumb ~22°, curl 36°, splay 17°.
HAND_POSE = {   # Q48 table E: the living hand — X curls every phalanx, Z only on the knuckles (k-1)
    "finger1-1": (12, 0, -40),
    "finger2-1": (6, 0, -4),
    "finger3-1": (8, 0, -1),
    "finger4-1": (10, 0, 1),
    "finger5-1": (12, 0, 5),
    "finger2-2": (15, 0, 0),
    "finger3-2": (18, 0, 0),
    "finger4-2": (22, 0, 0),
    "finger5-2": (26, 0, 0),
    "finger2-3": (8, 0, 0),
    "finger3-3": (10, 0, 0),
    "finger4-3": (12, 0, 0),
    "finger5-3": (14, 0, 0),
}
BREATH_PERIOD = 58
BREATH_SPINE_DEG = 0.9
SOB_PERIOD = 19
SOB_DEG = 0.5


def _catmull(pts, f):
    if f <= pts[0][0]:
        return pts[0][1]
    if f >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        f0, v0 = pts[i]
        f1, v1 = pts[i + 1]
        if f0 <= f <= f1:
            t = (f - f0) / (f1 - f0)
            vm1 = pts[i - 1][1] if i > 0 else v0 - (v1 - v0)
            vp1 = pts[i + 2][1] if i + 2 < len(pts) else v1 + (v1 - v0)
            m0 = 0.5 * (v1 - vm1)
            m1 = 0.5 * (vp1 - v0)
            t2, t3 = t * t, t * t * t
            return ((2 * t3 - 3 * t2 + 1) * v0 + (t3 - 2 * t2 + t) * m0 +
                    (-2 * t3 + 3 * t2) * v1 + (t3 - t2) * m1)
    return pts[-1][1]


def _sampled(pts, passes=3):
    """Per-frame samples, then 1-2-1 smoothing: unevenly spaced control points otherwise leave the
    per-frame STEP discontinuous even when the value is continuous (Q37)."""
    vals = [_catmull(pts, f) for f in range(F0, F1 + 1)]
    for _ in range(passes):
        vals = [vals[0]] + [(vals[i - 1] + 2 * vals[i] + vals[i + 1]) / 4 for i in range(1, len(vals) - 1)] + [vals[-1]]
    return {F0 + i: v for i, v in enumerate(vals)}


_NOD = _sampled([(f, v) for f, v, _, _ in HEAD_CTRL])
_TURN = _sampled([(f, v) for f, _, v, _ in HEAD_CTRL])
_TILT = _sampled([(f, v) for f, _, _, v in HEAD_CTRL])
_BODY = _sampled(BODY_CTRL)
_LEAN = _sampled(LEAN_CTRL)
_SHOULDER = _sampled(SHOULDER_CTRL)
_ARM = {b: tuple(_sampled([(p[0], p[i + 1]) for p in pts]) for i in range(3)) for b, pts in ARM_CTRL.items()}


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _lerp(p, q, t):
    return tuple(p[i] + (q[i] - p[i]) * t for i in range(3))


APPROACH_FOLD_SHARE = 0.5    # share of the approach path from rest to the folded arm
RELEASE_VIA_SHARE = 0.45      # share of the release path taken by the first of the two joined legs


def _ease_trapezoid(u, ramp=0.25):
    """Position for a trapezoid speed profile: accelerate over `ramp`, cruise, decelerate over `ramp`.
    Peak speed = 1/(1 − ramp) of the mean (1.33×), against 1.5× for smoothstep."""
    u = max(0.0, min(1.0, u))
    k = 1.0 / (2.0 * ramp * (1.0 - ramp))
    if u < ramp:
        return k * u * u * ramp / ramp if False else u * u / (2.0 * ramp * (1.0 - ramp))
    if u <= 1.0 - ramp:
        return (u - ramp / 2.0) / (1.0 - ramp)
    return 1.0 - (1.0 - u) ** 2 / (2.0 * ramp * (1.0 - ramp))


# Q47 path B — the near arm's approach and release, designed by the owner's side under the gate
# (contractor/burst-2/SHOT_003_hand_transit_A.json, variant A), embedded VERBATIM so the build stays
# self-contained. Euler XYZ degrees per frame for the five bones; 1274–1305 and 1335–1360. It meets this
# script's HOLD, RELEASE and rest curve ARM_CTRL exactly — do not change those without regenerating it.
HAND_TRANSIT = {   # Q48 table E (variant E, gate v7), embedded verbatim; 1305 and 1335 equal HOLD_arm
    1274: {"upperarm01.L": (7.539, 0.285, -17.619), "upperarm02.L": (0.0, -2.694, 0.0), "lowerarm01.L": (-14.075, 0.0, 0.0), "lowerarm02.L": (0.0, -5.388, 0.0), "wrist.L": (9.429, -0.0, -13.469)},
    1275: {"upperarm01.L": (7.84, 0.449, -17.949), "upperarm02.L": (0.0, -2.776, 0.0), "lowerarm01.L": (-15.252, 0.0, 0.0), "lowerarm02.L": (0.0, -5.551, 0.0), "wrist.L": (9.714, 0.0, -13.878)},
    1276: {"upperarm01.L": (8.171, 0.632, -18.299), "upperarm02.L": (0.0, -2.857, 0.0), "lowerarm01.L": (-16.555, 0.0, 0.0), "lowerarm02.L": (0.0, -5.714, 0.0), "wrist.L": (10.0, -0.0, -14.286)},
    1277: {"upperarm01.L": (8.526, 0.832, -18.665), "upperarm02.L": (0.0, -2.939, 0.0), "lowerarm01.L": (-17.964, 0.0, 0.0), "lowerarm02.L": (0.0, -5.878, 0.0), "wrist.L": (10.286, -0.0, -14.694)},
    1278: {"upperarm01.L": (8.903, 1.046, -19.046), "upperarm02.L": (0.0, -3.02, 0.0), "lowerarm01.L": (-19.468, 0.0, 0.0), "lowerarm02.L": (0.0, -6.041, 0.0), "wrist.L": (10.571, 0.0, -15.102)},
    1279: {"upperarm01.L": (9.298, 1.273, -19.439), "upperarm02.L": (0.0, -3.102, 0.0), "lowerarm01.L": (-21.051, 0.0, 0.0), "lowerarm02.L": (0.0, -6.204, 0.0), "wrist.L": (10.857, -0.0, -15.51)},
    1280: {"upperarm01.L": (9.709, 1.51, -19.843), "upperarm02.L": (0.0, -3.184, 0.0), "lowerarm01.L": (-22.701, 0.0, 0.0), "lowerarm02.L": (0.0, -6.367, 0.0), "wrist.L": (11.143, 0.0, -15.918)},
    1281: {"upperarm01.L": (10.132, 1.755, -20.255), "upperarm02.L": (0.0, -3.265, 0.0), "lowerarm01.L": (-24.405, 0.0, 0.0), "lowerarm02.L": (0.0, -6.531, 0.0), "wrist.L": (11.429, -0.0, -16.327)},
    1282: {"upperarm01.L": (10.055, 1.7, -20.147), "upperarm02.L": (0.0, -3.236, 0.0), "lowerarm01.L": (-23.474, 0.0, 0.0), "lowerarm02.L": (0.0, -6.879, 0.0), "wrist.L": (11.506, 0.011, -16.179)},
    1283: {"upperarm01.L": (9.822, 1.537, -19.824), "upperarm02.L": (0.0, -3.147, 0.0), "lowerarm01.L": (-20.679, 0.0, 0.0), "lowerarm02.L": (0.0, -7.925, 0.0), "wrist.L": (11.737, 0.043, -15.736)},
    1284: {"upperarm01.L": (9.433, 1.268, -19.283), "upperarm02.L": (0.0, -2.999, 0.0), "lowerarm01.L": (-16.021, 0.0, 0.0), "lowerarm02.L": (0.0, -9.669, 0.0), "wrist.L": (12.124, 0.092, -14.996)},
    1285: {"upperarm01.L": (8.884, 0.898, -18.523), "upperarm02.L": (0.0, -2.792, 0.0), "lowerarm01.L": (-9.5, 0.0, 0.0), "lowerarm02.L": (0.0, -12.11, 0.0), "wrist.L": (12.667, 0.152, -13.961)},
    1286: {"upperarm01.L": (8.17, 0.434, -17.542), "upperarm02.L": (0.0, -2.525, 0.0), "lowerarm01.L": (-1.118, 0.0, 0.0), "lowerarm02.L": (0.0, -15.248, 0.0), "wrist.L": (13.365, 0.214, -12.63)},
    1287: {"upperarm01.L": (7.289, -0.117, -16.336), "upperarm02.L": (0.0, -2.2, 0.0), "lowerarm01.L": (9.113, -0.0, 0.0), "lowerarm02.L": (0.0, -19.078, 0.0), "wrist.L": (14.22, 0.269, -11.004)},
    1288: {"upperarm01.L": (6.237, -0.741, -14.905), "upperarm02.L": (0.0, -1.817, 0.0), "lowerarm01.L": (21.166, -0.0, 0.0), "lowerarm02.L": (0.0, -23.59, 0.0), "wrist.L": (15.228, 0.302, -9.087)},
    1289: {"upperarm01.L": (5.063, -1.396, -13.319), "upperarm02.L": (0.0, -1.397, 0.0), "lowerarm01.L": (34.406, -0.0, 0.0), "lowerarm02.L": (0.0, -28.546, 0.0), "wrist.L": (16.336, 0.3, -6.982)},
    1290: {"upperarm01.L": (3.877, -2.016, -11.728), "upperarm02.L": (0.0, -0.978, 0.0), "lowerarm01.L": (47.577, -0.0, 0.0), "lowerarm02.L": (0.0, -33.477, 0.0), "wrist.L": (17.437, 0.257, -4.888)},
    1291: {"upperarm01.L": (2.685, -2.596, -10.14), "upperarm02.L": (0.0, -0.564, 0.0), "lowerarm01.L": (60.623, -0.0, 0.0), "lowerarm02.L": (0.0, -38.361, 0.0), "wrist.L": (18.526, 0.175, -2.815)},
    1292: {"upperarm01.L": (1.489, -3.138, -8.555), "upperarm02.L": (0.0, -0.153, 0.0), "lowerarm01.L": (73.535, -0.0, 0.0), "lowerarm02.L": (0.0, -43.194, 0.0), "wrist.L": (19.6, 0.055, -0.765)},
    1293: {"upperarm01.L": (6.259, -6.6, -8.232), "upperarm02.L": (0.0, 2.661, 0.0), "lowerarm01.L": (78.603, -0.0, 0.0), "lowerarm02.L": (0.0, -50.321, 0.0), "wrist.L": (12.018, -0.0, 0.0)},
    1294: {"upperarm01.L": (14.803, -11.771, -9.309), "upperarm02.L": (0.0, 6.946, 0.0), "lowerarm01.L": (78.997, -0.0, 0.0), "lowerarm02.L": (0.0, -58.892, 0.0), "wrist.L": (-0.838, 0.0, 0.0)},
    1295: {"upperarm01.L": (23.711, -16.76, -11.216), "upperarm02.L": (0.0, 11.264, 0.0), "lowerarm01.L": (79.394, -0.0, 0.0), "lowerarm02.L": (0.0, -67.529, 0.0), "wrist.L": (-13.793, 0.0, 0.0)},
    1296: {"upperarm01.L": (33.152, -21.437, -14.018), "upperarm02.L": (0.0, 15.627, 0.0), "lowerarm01.L": (79.795, -0.0, 0.0), "lowerarm02.L": (0.0, -76.254, 0.0), "wrist.L": (-26.88, 0.0, 0.0)},
    1297: {"upperarm01.L": (43.227, -25.651, -17.683), "upperarm02.L": (0.0, 19.957, 0.0), "lowerarm01.L": (80.182, -0.0, 0.0), "lowerarm02.L": (0.0, -84.978, 0.0), "wrist.L": (-39.947, 0.014, 0.064)},
    1298: {"upperarm01.L": (47.947, -30.322, -12.113), "upperarm02.L": (0.0, 15.269, 0.0), "lowerarm01.L": (78.507, -0.0, 0.0), "lowerarm02.L": (0.0, -82.635, 0.0), "wrist.L": (-34.142, 1.19, 7.05)},
    1299: {"upperarm01.L": (51.873, -34.784, -7.32), "upperarm02.L": (0.0, 11.11, 0.0), "lowerarm01.L": (77.021, -0.0, 0.0), "lowerarm02.L": (0.0, -80.555, 0.0), "wrist.L": (-28.904, 1.632, 13.321)},
    1300: {"upperarm01.L": (54.946, -38.69, -3.419), "upperarm02.L": (0.0, 7.654, 0.0), "lowerarm01.L": (75.786, -0.0, 0.0), "lowerarm02.L": (0.0, -78.827, 0.0), "wrist.L": (-24.534, 1.56, 18.547)},
    1301: {"upperarm01.L": (57.293, -41.955, -0.312), "upperarm02.L": (0.0, 4.867, 0.0), "lowerarm01.L": (74.79, -0.0, 0.0), "lowerarm02.L": (0.0, -77.433, 0.0), "wrist.L": (-21.028, 1.214, 22.746)},
    1302: {"upperarm01.L": (59.015, -44.528, 2.064), "upperarm02.L": (0.0, 2.724, 0.0), "lowerarm01.L": (74.024, -0.0, 0.0), "lowerarm02.L": (0.0, -76.362, 0.0), "wrist.L": (-18.356, 0.774, 25.955)},
    1303: {"upperarm01.L": (60.189, -46.381, 3.747), "upperarm02.L": (0.0, 1.207, 0.0), "lowerarm01.L": (73.482, -0.0, 0.0), "lowerarm02.L": (0.0, -75.603, 0.0), "wrist.L": (-16.479, 0.372, 28.214)},
    1304: {"upperarm01.L": (60.87, -47.497, 4.751), "upperarm02.L": (0.0, 0.302, 0.0), "lowerarm01.L": (73.159, -0.0, 0.0), "lowerarm02.L": (0.0, -75.151, 0.0), "wrist.L": (-15.369, 0.097, 29.554)},
    1305: {"upperarm01.L": (61.094, -47.871, 5.086), "upperarm02.L": (0.0, 0.0, 0.0), "lowerarm01.L": (73.051, 0.0, 0.0), "lowerarm02.L": (0.0, -75.0, 0.0), "wrist.L": (-15.0, 0.0, 30.0)},
    1335: {"upperarm01.L": (61.094, -47.871, 5.086), "upperarm02.L": (0.0, 0.0, 0.0), "lowerarm01.L": (73.051, 0.0, 0.0), "lowerarm02.L": (0.0, -75.0, 0.0), "wrist.L": (-15.0, 0.0, 30.0)},
    1336: {"upperarm01.L": (60.589, -47.346, 5.089), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (73.483, -0.0, 0.0), "lowerarm02.L": (0.0, -74.833, 0.0), "wrist.L": (-15.409, 0.108, 29.506)},
    1337: {"upperarm01.L": (59.103, -45.77, 5.057), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (74.781, -0.0, 0.0), "lowerarm02.L": (0.0, -74.331, 0.0), "wrist.L": (-16.642, 0.41, 28.018)},
    1338: {"upperarm01.L": (56.692, -43.126, 4.879), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (76.961, -0.0, 0.0), "lowerarm02.L": (0.0, -73.487, 0.0), "wrist.L": (-18.729, 0.844, 25.506)},
    1339: {"upperarm01.L": (53.427, -39.402, 4.394), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (80.042, -0.0, 0.0), "lowerarm02.L": (0.0, -72.295, 0.0), "wrist.L": (-21.708, 1.301, 21.931)},
    1340: {"upperarm01.L": (49.349, -34.592, 3.413), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (84.055, -0.0, 0.0), "lowerarm02.L": (0.0, -70.743, 0.0), "wrist.L": (-25.621, 1.615, 17.247)},
    1341: {"upperarm01.L": (44.439, -28.719, 1.725), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (89.035, -0.0, 0.0), "lowerarm02.L": (0.0, -68.816, 0.0), "wrist.L": (-30.492, 1.559, 11.421)},
    1342: {"upperarm01.L": (38.595, -21.854, -0.907), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (95.019, -0.0, 0.0), "lowerarm02.L": (0.0, -66.501, 0.0), "wrist.L": (-36.299, 0.839, 4.46)},
    1343: {"upperarm01.L": (32.316, -11.565, -2.288), "upperarm02.L": (0.0, -2.51, 0.0), "lowerarm01.L": (96.911, -0.0, 0.0), "lowerarm02.L": (0.0, -61.236, 0.0), "wrist.L": (-32.471, 0.0, 0.0)},
    1344: {"upperarm01.L": (27.017, 2.197, -1.774), "upperarm02.L": (0.0, -8.256, 0.0), "lowerarm01.L": (92.359, -0.0, 0.0), "lowerarm02.L": (0.0, -52.616, 0.0), "wrist.L": (-15.232, 0.0, 0.0)},
    1345: {"upperarm01.L": (21.94, 15.208, -2.474), "upperarm02.L": (0.0, -13.692, 0.0), "lowerarm01.L": (88.053, -0.0, 0.0), "lowerarm02.L": (0.0, -44.461, 0.0), "wrist.L": (1.077, -0.0, 0.0)},
    1346: {"upperarm01.L": (16.53, 27.436, -4.384), "upperarm02.L": (0.0, -18.848, 0.0), "lowerarm01.L": (83.969, -0.0, 0.0), "lowerarm02.L": (0.0, -36.728, 0.0), "wrist.L": (16.544, -0.0, 0.0)},
    1347: {"upperarm01.L": (14.537, 27.653, -5.785), "upperarm02.L": (0.0, -18.331, 0.0), "lowerarm01.L": (71.952, -0.0, 0.0), "lowerarm02.L": (0.0, -32.079, 0.0), "wrist.L": (18.331, -0.0, 0.0)},
    1348: {"upperarm01.L": (13.783, 24.406, -6.708), "upperarm02.L": (0.0, -16.16, 0.0), "lowerarm01.L": (57.508, -0.0, 0.0), "lowerarm02.L": (0.0, -28.28, 0.0), "wrist.L": (16.16, -0.0, 0.0)},
    1349: {"upperarm01.L": (13.102, 21.144, -7.565), "upperarm02.L": (0.0, -13.985, 0.0), "lowerarm01.L": (43.038, -0.0, 0.0), "lowerarm02.L": (0.0, -24.474, 0.0), "wrist.L": (13.985, -0.0, 0.0)},
    1350: {"upperarm01.L": (12.484, 17.867, -8.365), "upperarm02.L": (0.0, -11.806, 0.0), "lowerarm01.L": (28.544, -0.0, 0.0), "lowerarm02.L": (0.0, -20.661, 0.0), "wrist.L": (11.806, -0.0, 0.0)},
    1351: {"upperarm01.L": (11.924, 14.577, -9.116), "upperarm02.L": (0.0, -9.624, 0.0), "lowerarm01.L": (14.027, -0.0, 0.0), "lowerarm02.L": (0.0, -16.842, 0.0), "wrist.L": (9.624, -0.0, 0.0)},
    1352: {"upperarm01.L": (11.415, 11.285, -9.824), "upperarm02.L": (0.0, -7.445, 0.0), "lowerarm01.L": (-0.469, 0.0, 0.0), "lowerarm02.L": (0.0, -13.029, 0.0), "wrist.L": (7.445, -0.0, 0.0)},
    1353: {"upperarm01.L": (10.994, 8.298, -10.434), "upperarm02.L": (0.0, -5.47, 0.0), "lowerarm01.L": (-13.607, 0.0, 0.0), "lowerarm02.L": (0.0, -9.573, 0.0), "wrist.L": (5.47, -0.0, 0.0)},
    1354: {"upperarm01.L": (10.665, 5.765, -10.93), "upperarm02.L": (0.0, -3.799, 0.0), "lowerarm01.L": (-24.728, 0.0, 0.0), "lowerarm02.L": (0.0, -6.648, 0.0), "wrist.L": (3.799, -0.0, 0.0)},
    1355: {"upperarm01.L": (10.412, 3.69, -11.324), "upperarm02.L": (0.0, -2.431, 0.0), "lowerarm01.L": (-33.829, 0.0, 0.0), "lowerarm02.L": (0.0, -4.254, 0.0), "wrist.L": (2.431, -0.0, 0.0)},
    1356: {"upperarm01.L": (10.226, 2.076, -11.623), "upperarm02.L": (0.0, -1.367, 0.0), "lowerarm01.L": (-40.905, 0.0, 0.0), "lowerarm02.L": (0.0, -2.392, 0.0), "wrist.L": (1.367, -0.0, 0.0)},
    1357: {"upperarm01.L": (10.099, 0.923, -11.834), "upperarm02.L": (0.0, -0.608, 0.0), "lowerarm01.L": (-45.958, 0.0, 0.0), "lowerarm02.L": (0.0, -1.063, 0.0), "wrist.L": (0.608, -0.0, 0.0)},
    1358: {"upperarm01.L": (10.024, 0.231, -11.959), "upperarm02.L": (0.0, -0.152, 0.0), "lowerarm01.L": (-48.99, 0.0, 0.0), "lowerarm02.L": (0.0, -0.266, 0.0), "wrist.L": (0.152, -0.0, 0.0)},
    1359: {"upperarm01.L": (10.0, -0.0, -12.0), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (-50.0, 0.0, 0.0), "lowerarm02.L": (0.0, -0.0, 0.0), "wrist.L": (0.0, -0.0, 0.0)},
    1360: {"upperarm01.L": (10.0, -0.0, -12.0), "upperarm02.L": (0.0, -0.0, 0.0), "lowerarm01.L": (-50.0, 0.0, 0.0), "lowerarm02.L": (0.0, -0.0, 0.0), "wrist.L": (0.0, -0.0, 0.0)},
}


def live_weight(f):
    """1 before the hold, smoothstep to 0 over the approach, 0 on the hold, smoothstep back to 1 over the release."""
    a0, a1 = HOLD_IN
    r0, r1 = HOLD_OUT
    if f <= a0 or f >= r1:
        return 1.0
    if f < a1:
        return 1.0 - _smoothstep((f - a0) / (a1 - a0))
    if f <= r0:
        return 0.0
    return _smoothstep((f - r0) / (r1 - r0))


def arm_value(bone, f):
    """Rest curve → VIA_IN → HOLD (constant on 1305–1332) → VIA_OUT → RELEASE, each leg a smoothstep."""
    if f in HAND_TRANSIT and bone in HAND_TRANSIT[f]:
        return HAND_TRANSIT[f][bone]
    if bone not in HOLD:
        return tuple(_ARM[bone][i][f] for i in range(3))
    a0, a1 = HOLD_IN
    r0, r1 = HOLD_OUT
    am = VIA_IN_FRAME
    rm = (r0 + r1) // 2
    if f < a0:
        return tuple(_ARM[bone][i][f] for i in range(3))
    base = tuple(_ARM[bone][i][a0] for i in range(3))
    if f <= a1:
        # rest → the arm folded in front of the chest (VIA_OUT) → straight up into the hold, ONE trapezoid-
        # profile motion. Earlier versions went through VIA_IN, which sits 199 mm in front of the chest with
        # the forearm level: slowed down to ≤ 80 mm/frame, that phase read as pointing for six frames.
        s = _ease_trapezoid((f - a0) / (a1 - a0))
        if s <= APPROACH_FOLD_SHARE:
            return _lerp(base, VIA_OUT[bone], s / APPROACH_FOLD_SHARE)
        return _lerp(VIA_OUT[bone], HOLD[bone], (s - APPROACH_FOLD_SHARE) / (1.0 - APPROACH_FOLD_SHARE))
    if f <= r0:
        return HOLD[bone]
    # release in three legs: back along the approach path (HOLD → VIA_IN, proven clear by the gate on the
    # way in), then the upper arm drops with the elbow still bent (→ VIA_OUT), then the elbow opens (→ RELEASE)
    m1, m2 = r0 + 4, VIA_OUT_FRAME
    if f <= m1:
        return _lerp(HOLD[bone], VIA_IN[bone], _smoothstep((f - r0) / (m1 - r0)))
    if f <= r1:
        # legs 2 and 3 as ONE motion through VIA_OUT with a trapezoid speed profile (ease in, cruise, ease out):
        # separate smoothsteps stopped the hand at the via and peaked at 1.5× the mean speed (82 mm/frame)
        s = _ease_trapezoid((f - m1) / (r1 - m1))
        if s <= RELEASE_VIA_SHARE:
            return _lerp(VIA_IN[bone], VIA_OUT[bone], s / RELEASE_VIA_SHARE)
        return _lerp(VIA_OUT[bone], RELEASE[bone], (s - RELEASE_VIA_SHARE) / (1.0 - RELEASE_VIA_SHARE))
    return RELEASE[bone]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sc = bpy.data.scenes["SLICE"]
    ctrl = bpy.data.objects["FACE_CTRL"]
    rig = bpy.data.objects["RIG_HERO"]
    ctrl.animation_data_clear()
    rig.animation_data_clear()

    for f, pose in FACE:
        for ch in CH:
            if ch.startswith("blink"):
                continue
            fk = min(F1, max(F0, f + LAG.get(ch, 0)))
            val = float(pose.get(ch, 0.0)) * (MIRROR if ch in ("gaze_yaw", "jaw_lateral") else 1.0)
            ctrl[ch] = val
            ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=fk)
    for f, v in BLINKS:
        for ch in ("blink_l", "blink_r"):
            ctrl[ch] = v
            ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=f)
    for ch in ("blink_l", "blink_r"):
        for f in (F0, F1):
            ctrl[ch] = 0.0
            ctrl.keyframe_insert(data_path=f'["{ch}"]', frame=f)

    for f in range(F0, F1 + 1):
        br = math.sin(2 * math.pi * (f - F0) / BREATH_PERIOD)
        sob_gate = max(0.0, min(1.0, (W_SAD[1] + 6 - f) / 10.0))      # fades, never switches off
        sob = SOB_DEG * math.sin(2 * math.pi * (f - F0) / SOB_PERIOD) * sob_gate
        body = MIRROR * _BODY[f]
        for bone, x, y in (("spine_03", BREATH_SPINE_DEG * br * 0.5 + sob + 1.2 * _LEAN[f], body * 0.45),
                           ("spine_05", BREATH_SPINE_DEG * br + sob + 1.8 * _LEAN[f], body * 0.55)):
            pb = rig.pose.bones[bone]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(x), math.radians(y), 0.0)
            pb.keyframe_insert("rotation_euler", frame=f)
        on_hold = HOLD_IN[1] <= f <= HOLD_OUT[0]
        for side in ("shoulder_l", "shoulder_r"):
            pb = rig.pose.bones[side]
            pb.rotation_mode = "XYZ"
            x, y, z = arm_value(side, f)
            live = _SHOULDER[f] * 0.5 + 0.6 * br
            if side == "shoulder_l":     # the breath on the arm chain fades out into the hold and back in after it —
                live *= live_weight(f)   # it was switched by a window test, and the step pushed the hand into the cheek on 1333
            pb.rotation_euler = (math.radians(x + live), math.radians(y), math.radians(z))
            pb.keyframe_insert("rotation_euler", frame=f)
        for bone in ("upperarm01.L", "upperarm02.L", "lowerarm01.L", "lowerarm02.L", "wrist.L",
                     "upperarm01.R", "lowerarm01.R", "wrist.R"):
            pb = rig.pose.bones[bone]
            pb.rotation_mode = "XYZ"
            x, y, z = arm_value(bone, f)
            pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
            pb.keyframe_insert("rotation_euler", frame=f)
        for base_name, (hx, hy, hz) in HAND_POSE.items():
            for side, zs in (("L", 1.0), ("R", -1.0)):
                pb = rig.pose.bones[f"{base_name}.{side}"]
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = (math.radians(hx), math.radians(hy), math.radians(hz * zs))
                pb.keyframe_insert("rotation_euler", frame=f)
        for bone, k in (("neck", 0.45), ("head", 0.55)):
            pb = rig.pose.bones[bone]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (math.radians(_NOD[f] * k), math.radians(MIRROR * _TURN[f] * k), math.radians(MIRROR * _TILT[f] * k))
            pb.keyframe_insert("rotation_euler", frame=f)
    sc.frame_set(F0)
    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    print(f"ANIM_OK {a.out} face_keys={len(FACE)} frames {F0}-{F1}")


if __name__ == "__main__":
    main()
