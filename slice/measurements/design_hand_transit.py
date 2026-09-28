"""The hand's approach and release for SHOT_003, designed by us — path B (owner, 2026-09-27): the contractor's v04
approach went through a horizontal forearm across the face (1292–1298) and the release left the hand in the air
while the head turned away — a straight-looking arm raised forward-up (1340–1344). Both read wrong; the owner chose
to have us set the transits, as we set the hold (path A).

The near arm's five bones (upperarm01/02, lowerarm01/02, wrist — shoulder_l keeps the contractor's breath) are
driven per frame by quaternion slerps through one station of our own, MID — the hand up at the chin, the elbow
low (154 mm under the shoulder joint) and a little forward (83 mm), in front of the chest on its own side, the
forearm near vertical, the hand 35 mm off the face: how a child brings a hand to the eyes. The ends are the
contractor's own poses — the rest curve, HOLD, RELEASE — read from his animate_shot_003.py:

  approach A0 → A1  rest → MID → HOLD: the hand comes up close to the body, from below, and slides up to the
                    eyes — no horizontal forearm in front of the face (v04 1292–1298);
  hold              the contractor's constants, untouched;
  release R0 → R1   HOLD → MID → RELEASE: the hand comes down to the chin as the head turns away and then down
                    to the side — it never stays up in the air (v04 1340–1344).

Each transit is ONE motion: a trapezoid speed profile over the whole path, split between the two legs by their
share of it (share_in / share_out), so the speed is continuous through MID. MID was found by a search under the
gate's geometry (twist bones on their own axis only; slice/measurements/shot_003_transit_2026-09-27.json).

Before A0 the arm follows the contractor's rest curve (his approach began at 1274 and folded the arm across the
chest through the fear peak); after R1 it holds RELEASE. Slerp on local rotations, no Euler interpolation; every
frame is written back as XYZ Euler (compatible with the previous frame) into a COPY of the file.

    blender -b SHOT_003_v04.blend --python-exit-code 2 -P slice/measurements/design_hand_transit.py -- \\
        --anim-script animate_shot_003.py --out <copy.blend> --json <table.json> [--a0 1287 --a1 1305 --r0 1335 --r1 1351]

Writes the per-frame Euler table (degrees) the contractor integrates, and prints TRANSIT_OK."""
import argparse
import json
import math
import runpy
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

BONES = ["upperarm01.L", "upperarm02.L", "lowerarm01.L", "lowerarm02.L", "wrist.L"]


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def window(t, t0, t1):
    """smoothstep of t mapped from [t0, t1] to [0, 1]."""
    return smoothstep((t - t0) / (t1 - t0))


# Stations of our own (degrees, XYZ; twist bones about their own axis only), found by searches under the gate's
# geometry on 1298-1301 (slice/measurements/shot_003_transit_2026-09-27.json):
#   FOLD  the elbow bent, the upper arm still down — the hand comes up in front of the belly first;
#   CHIN  the hand at the chin 35 mm off the face, the elbow 154 mm under the shoulder and 83 mm forward, in front
#         of the chest on its own side, the forearm near vertical;
#   NOSE  the hand in front of the nose 37 mm off the face, the elbow 57 mm under the shoulder, 70 out, 188 forward,
#         the forearm vertical (0.88) — the last station before the palm meets the eyes, so it never slides over the face.
FOLD = {"upperarm01.L": (9.6, -6.59, -36.3), "upperarm02.L": (0.0, -41.63, 0.0), "lowerarm01.L": (-110.0, 0.0, 0.0),
        "lowerarm02.L": (0.0, -10.08, 0.0), "wrist.L": (-6.22, -3.61, -8.55)}      # grid: the shortest rest -> FOLD -> CHIN
CHIN = {"upperarm01.L": (28.79, -37.56, -105.17), "upperarm02.L": (0.0, -41.63, 0.0), "lowerarm01.L": (-145.49, 0.0, 0.0),
        "lowerarm02.L": (0.0, -10.08, 0.0), "wrist.L": (-49.87, 0.0, 13.36)}
CHEST = {"upperarm01.L": (8.96, -17.64, -76.45), "upperarm02.L": (0.0, -59.57, 0.0), "lowerarm01.L": (-144.11, 0.0, 0.0),
         "lowerarm02.L": (0.0, 11.26, 0.0), "wrist.L": (-33.6, 0.0, -28.83)}   # the release: the hand drops to the chest first
NOSE = {"upperarm01.L": (103.56, -3.42, -162.93), "upperarm02.L": (0.0, -35.09, 0.0), "lowerarm01.L": (-149.76, 0.0, 0.0),
        "lowerarm02.L": (0.0, -10.96, 0.0), "wrist.L": (-38.63, 0.0, 19.97)}


def trapezoid(u, ramp=0.3):
    """Position along the path for a trapezoid speed profile (accelerate over `ramp`, cruise, decelerate)."""
    u = max(0.0, min(1.0, u))
    k = 1.0 / (2.0 * ramp * (1.0 - ramp))
    if u < ramp:
        return k * u * u
    if u <= 1.0 - ramp:
        return (u - ramp / 2.0) / (1.0 - ramp)
    return 1.0 - k * (1.0 - u) ** 2


def q(e_deg):
    return Euler([math.radians(v) for v in e_deg], "XYZ").to_quaternion()


class Path3:
    """A chain of stations (bone -> quaternion), slerped leg by leg and re-parametrised by the WRIST's arc length,
    so a trapezoid in time is a trapezoid in the hand's speed (slerp is uniform in angle, not in the hand's travel).
    measure="wrist+elbow" adds the elbow's arc: a leg that turns the arm a lot while the wrist moves little (v10's
    CHIN2 -> SLIDE: 63 mm of wrist, the elbow dropping 61 mm and the palm turning 40 deg) otherwise passes in one frame."""

    def __init__(self, stations, rig, samples=16, measure="wrist"):
        self.st, self.rig, self.measure = stations, rig, measure
        self.cum = [0.0]                              # cumulative wrist length at each sample, legs concatenated
        self.at = [(0, 0.0)]
        prev = self._wrist(0, 0.0)
        for leg in range(len(stations) - 1):
            for k in range(1, samples + 1):
                u = k / samples
                w = self._wrist(leg, u)
                self.cum.append(self.cum[-1] + (w - prev).length)
                self.at.append((leg, u))
                prev = w
        self.length = self.cum[-1]
        per = len(self.cum) // (len(stations) - 1) if len(stations) > 1 else 1
        self.legs = [round(1000 * (self.cum[(i + 1) * samples] - self.cum[i * samples])) for i in range(len(stations) - 1)]

    def pose(self, leg, u):
        a, b = self.st[leg], self.st[leg + 1]
        return {n: a[n].slerp(b[n], u) for n in a}

    def _wrist(self, leg, u):
        """The point whose travel measures the path: the wrist, or the wrist and the elbow stacked (6-D)."""
        pb = self.rig.pose.bones
        for n, qq in self.pose(leg, u).items():
            pb[n].rotation_mode = "XYZ"
            pb[n].rotation_euler = qq.to_euler("XYZ")
        bpy.context.view_layer.update()
        w = self.rig.matrix_world @ pb["wrist.L"].head
        if self.measure == "wrist":
            return w
        e = self.rig.matrix_world @ pb["lowerarm01.L"].head
        return Vector((*w, *e))

    def at_length(self, s):
        """The pose at fraction s of the wrist's path."""
        target = max(0.0, min(1.0, s)) * self.length
        for i in range(1, len(self.cum)):
            if self.cum[i] >= target:
                f = (target - self.cum[i - 1]) / max(self.cum[i] - self.cum[i - 1], 1e-12)
                (l0, u0), (l1, u1) = self.at[i - 1], self.at[i]
                if l1 != l0:
                    u0 = 0.0
                return self.pose(l1, u0 + (u1 - u0) * f)
        return self.pose(len(self.st) - 2, 1.0)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--anim-script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--a0", type=int, default=1281)
    ap.add_argument("--a1", type=int, default=1305)
    ap.add_argument("--r0", type=int, default=1335)
    ap.add_argument("--r1", type=int, default=1359)

    ap.add_argument("--approach-via", default="FOLD,CHIN,NOSE", help="stations of the approach between the rest curve and HOLD, comma-separated")
    ap.add_argument("--release-via", default="FOLD", help="stations of the release between HOLD and RELEASE, comma-separated")
    ap.add_argument("--stations", default=None, help="a JSON file of more named stations {name: {bone: [x, y, z] degrees}}")
    ap.add_argument("--measure", default="wrist", choices=("wrist", "wrist+elbow"), help="what the trapezoid's arc length measures")
    ap.add_argument("--hold-json", default=None, help="a JSON {bone: [x, y, z] degrees} replacing the script's HOLD (the v7 anatomical hold)")
    ap.add_argument("--palm-to-face", type=float, default=None, help="lowerarm02 twist at CHIN and NOSE on the APPROACH (the palm turned to the face early)")
    ap.add_argument("--from-frame", type=int, default=1274, help="the contractor's approach began here: the rest curve from here to A0")
    a = ap.parse_args(argv)
    ns = runpy.run_path(a.anim_script, run_name="transit_design")
    rest = lambda b, f: tuple(ns["_ARM"][b][i][f] for i in range(3))  # noqa: E731
    hold, release_pose, f_end = ns["HOLD"], ns["RELEASE"], ns["F1"]
    if a.hold_json:
        hold = {b: tuple(v) for b, v in json.loads(Path(a.hold_json).read_text()).items()}
    sc = bpy.data.scenes["SLICE"]
    rig = bpy.data.objects["RIG_HERO"]
    qd = lambda d: {n: q(d[n]) for n in BONES}  # noqa: E731 — the five arm bones; shoulder_l keeps the contractor's breath
    chin_in, nose_in = dict(CHIN), dict(NOSE)       # the approach's stations; the release keeps the searched twist
    if a.palm_to_face is not None:
        for st in (chin_in, nose_in):
            st["lowerarm02.L"] = (0.0, a.palm_to_face, 0.0)
    off = dict(hold)
    off["lowerarm01.L"] = (-122.0, 0.0, 0.0)   # OFF: the hold with the elbow opened 24 deg — the palm lifts off the face first
    named = {"FOLD": FOLD, "CHIN": CHIN, "NOSE": NOSE, "CHEST": CHEST, "OFF": off}
    if a.stations:
        named.update({k: {b: tuple(v[b]) for b in BONES} for k, v in json.loads(Path(a.stations).read_text()).items()})
    via_in = [{"CHIN": chin_in, "NOSE": nose_in}.get(v, named[v]) for v in a.approach_via.split(",") if v]
    via_out = [named[v] for v in a.release_via.split(",") if v]
    sc.frame_set(a.a0)
    path_in = Path3([qd({b: rest(b, a.a0) for b in BONES})] + [qd(v) for v in via_in] + [qd(hold)], rig, measure=a.measure)
    sc.frame_set(a.r0)
    path_out = Path3([qd(hold)] + [qd(v) for v in via_out] + [qd(release_pose)], rig, measure=a.measure)
    for nm, pth, n in (("approach", path_in, a.a1 - a.a0), ("release", path_out, a.r1 - a.r0)):
        print(f"PATH {nm}: {a.measure} travel {1000 * pth.length:.0f} mm over {n} frames — mean {1000 * pth.length / n:.0f}, "
              f"trapezoid peak {1000 * pth.length / n / 0.7:.0f} mm/frame (the body's own motion adds to it); legs {pth.legs} mm")
    table, prev = {}, {}
    for f in range(a.from_frame, f_end + 1):
        if a.a1 < f < a.r0:
            continue                                                    # the hold: the contractor's constants
        row = {}
        for b in BONES:
            if f < a.a0:
                e = rest(b, f)
                rot = q(e)
            elif f <= a.a1:
                rot = path_in.at_length(trapezoid((f - a.a0) / (a.a1 - a.a0)))[b]
            elif f <= a.r1:
                rot = path_out.at_length(trapezoid((f - a.r0) / (a.r1 - a.r0)))[b]
            else:
                rot = q(release_pose[b])
            ref = prev.get(b)
            eu = rot.to_euler("XYZ", ref) if ref is not None else rot.to_euler("XYZ")
            prev[b] = eu
            row[b] = [round(math.degrees(v), 3) for v in eu]
            pb = rig.pose.bones[b]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = eu
            pb.keyframe_insert("rotation_euler", frame=f)
        table[f] = row
    Path(a.json).write_text(json.dumps({"what": "the near arm's Euler XYZ (degrees) per frame on the approach and the release; the hold is the "
                                                "contractor's HOLD, untouched", "a0": a.a0, "a1": a.a1, "r0": a.r0, "r1": a.r1,
                                        "from_frame": a.from_frame,
                                        "stations": {k: named[k] for k in dict.fromkeys(a.approach_via.split(",") + a.release_via.split(",")) if k},
                                        "approach": "rest -> " + " -> ".join(a.approach_via.split(",")) + " -> HOLD",
                                        "release": "HOLD -> " + " -> ".join(a.release_via.split(",")) + " -> RELEASE",
                                        "timing": f"one trapezoid speed profile (ramp 0.3) over the arc length of the {a.measure} per transit",
                                        "frames": table}, indent=1) + "\n")
    sc.frame_set(a.a0)
    bpy.ops.wm.save_as_mainfile(filepath=a.out, copy=True)
    print(f"TRANSIT_OK approach {a.a0}-{a.a1}, release {a.r0}-{a.r1}, {len(table)} frames keyed -> {a.out}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
