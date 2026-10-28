"""The mouth row of burst 3's acceptance (owner, 2026-10-28, Q65/Q66): on any frame of a shot, no part of the teeth or the
tongue that the shot camera sees lies outside the lips. Found 2026-10-28 on our expression sheet — the lower teeth out
through both mouth corners at the SHOT_001 laughter peak, the upper teeth ahead of the lip in the SHOT_002 profile, on the
default head and every child — while every gate passed. Our own measurement. Runs under Blender on a shot file:

    blender -b SHOT_00N_subject_NN.blend --python-exit-code 2 -P slice/measurements/mouth_check.py -- --out mouth.json \
        [--frames a-b] [--every 1] [--control-forward-mm 15]

Samples: the surfaces of the evaluated HERO_TEETH_UPPER, HERO_TEETH_LOWER and HERO_TONGUE in world space, on a grid of
1 mm over every triangle (their vertices are 5-10 mm apart; a corner showing 2 mm of tooth would fall between them).
Seen: inside the camera's frame, and the ray from the camera reaches the sample first — no triangle of a render-visible
mesh (head, hair, hand, body, glasses, set; the proxies excepted), nor another part of the teeth, more than 0.3 mm short
of it. Outside the lips: a seen sample whose ray, carried on beyond it, meets the head skin (HERO_HEAD) on its OUTER side,
or meets nothing. A skin face is outer when the ray along its normal escapes the head at rest (the base mesh, the mouth
shut); it is met on its outer side when struck from the front. A tooth seen through an open mouth has the inside of the
mouth behind it — the mouth's own faces, which never escape at rest, or the shell from within; a tooth out through a mouth
corner or ahead of the lip has the face's outer skin or the air behind it. Not caught: a tooth floating straight in front
of an open mouth, the mouth's inside behind it — the close-ups are for that. Validated 2026-10-28 on the default head's
accepted shots (`slice/measurements/mouth_check_2026-10-28/`): SHOT_001 fails on the laughter 1088-1120 and SHOT_002 on
the profile 1172-1240, the marks on the teeth out through the corners and ahead of the lip on our renders; the open mouth
(SHOT_001 1066, SHOT_002 1165) and SHOT_003 pass, unmarked; the teeth moved 10 mm forward at rest fail on 18 of 18
frames, unmoved pass.

MOUTH_OK when no seen sample is outside on any frame; MOUTH_FAIL (exit 2) otherwise, with the frames and the counts per
part; every outside sample's place in the frame is kept (`outside_ndc`, 0-1 from the lower left) for a look on the
render. --control-forward-mm moves the samples and the teeth's own triangles that far forward in the head socket's frame —
a positive control: teeth set ahead of the lips must fail."""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PARTS = ("HERO_TEETH_UPPER", "HERO_TEETH_LOWER", "HERO_TONGUE")
NEAR_M = 3e-4                                    # 0.3 mm: a hit this close to the sample is the sample itself
GRID_M = 1e-3                                    # sample spacing on the teeth's surface
FORWARD_LOCAL = Vector((0.0, -1.0, 0.0))         # the socket's forward in its own Blender axes (contract +Z = −Y_b)


def world_mesh(obj, dg):
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        n = len(me.vertices)
        co = np.empty(n * 3, np.float64)
        me.vertices.foreach_get("co", co)
        M = np.array(ev.matrix_world)
        v = co.reshape(n, 3) @ M[:3, :3].T + M[:3, 3]
        faces = [list(p.vertices) for p in me.polygons]
    finally:
        ev.to_mesh_clear()
    return v, faces


def surface_samples(v, faces):
    """Points on every triangle (polygons fanned) at about GRID_M spacing, vertices included."""
    pts = []
    for p in faces:
        for t in range(1, len(p) - 1):
            a, b, c = v[p[0]], v[p[t]], v[p[t + 1]]
            n = max(1, int(np.ceil(max(np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(c - b)) / GRID_M)))
            for i in range(n + 1):
                for j in range(n + 1 - i):
                    pts.append(a + (b - a) * (i / n) + (c - a) * (j / n))
    return pts


def outer_faces(head):
    """The skin faces whose normal-ray escapes the head at rest (base mesh, object space)."""
    me = head.data
    tree = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [list(p.vertices) for p in me.polygons])
    out = set()
    for p in me.polygons:
        if tree.ray_cast(p.center + p.normal * 1e-5, p.normal)[0] is None:
            out.add(p.index)
    return out, len(me.polygons)


def occluders(sc):
    return [o for o in sc.objects if o.type == "MESH" and o.name not in PARTS and not o.hide_render and o.visible_get()
            and not any(c.name == "C_PROXIES" or c.hide_render for c in o.users_collection)]


def measure(sc, dg, outer, shift):
    cam = sc.camera
    S = bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world.inverted()
    origin = cam.matrix_world.translation.copy()
    others_v, others_f, off = [], [], 0
    for o in occluders(sc):
        v, f = world_mesh(o, dg)
        others_v.append(v); others_f += [[i + off for i in p] for p in f]; off += len(v)
    others = BVHTree.FromPolygons(np.concatenate(others_v).tolist(), others_f) if others_v else None
    head_v, head_f = world_mesh(bpy.data.objects["HERO_HEAD"], dg)
    head = BVHTree.FromPolygons(head_v.tolist(), head_f)
    parts = {}
    for n in PARTS:
        if n in bpy.data.objects:
            v, f = world_mesh(bpy.data.objects[n], dg)
            parts[n] = (v + shift, f)
    mouth_v = np.concatenate([v for v, _ in parts.values()])
    mouth_f, off = [], 0
    for v, f in parts.values():
        mouth_f += [[i + off for i in p] for p in f]; off += len(v)
    mouth = BVHTree.FromPolygons(mouth_v.tolist(), mouth_f)
    seen, outside, where, marks = 0, {n: 0 for n in parts}, [], []
    for n, (v, f) in parts.items():
        for s in surface_samples(v, f):
            p = Vector(s)
            ndc = world_to_camera_view(sc, cam, p)
            if not (0.0 <= ndc.x <= 1.0 and 0.0 <= ndc.y <= 1.0 and ndc.z > 0.0):
                continue
            d = p - origin
            dist = d.length
            d.normalize()
            hit = others.ray_cast(origin, d, dist - NEAR_M)[0] if others else None
            if hit is not None:
                continue
            h = mouth.ray_cast(origin, d, dist - NEAR_M)[0]
            if h is not None and (h - p).length > NEAR_M:
                continue
            seen += 1
            loc, nrm, idx, _ = head.ray_cast(p + d * NEAR_M, d)
            if loc is None or (idx in outer and nrm.dot(d) < 0.0):
                outside[n] += 1
                marks.append([round(ndc.x, 4), round(ndc.y, 4)])
                if len(where) < 12:
                    q = S @ p                     # the socket's contract frame: X the character's left, Y up, Z forward
                    where.append({"part": n, "socket_mm": [round(q.x * 1e3, 1), round(q.z * 1e3, 1), round(-q.y * 1e3, 1)],
                                  "behind": "nothing" if loc is None else f"outer skin face {idx}"})
    return {"seen": seen, "outside": outside, "examples": where, "outside_ndc": marks}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", help="a-b (default: the shot's range)")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--control-forward-mm", type=float, default=0.0)
    a = ap.parse_args(argv)
    sc = bpy.data.scenes["SLICE"]
    f0, f1 = map(int, a.frames.split("-")) if a.frames else (sc.frame_start, sc.frame_end)
    head = bpy.data.objects["HERO_HEAD"]
    outer, nfaces = outer_faces(head)
    rows = []
    for f in range(f0, f1 + 1, a.every):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        if len(head.evaluated_get(dg).data.polygons) != nfaces:
            print("MOUTH_ERROR the evaluated head's faces differ from its base mesh", file=sys.stderr)
            sys.exit(3)
        shift = np.zeros(3)
        if a.control_forward_mm:
            R = bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world.to_3x3()
            shift = np.array(R @ FORWARD_LOCAL) * a.control_forward_mm * 1e-3
        rows.append({"frame": f, **measure(sc, dg, outer, shift)})
    bad = [r for r in rows if any(r["outside"].values())]
    runs = []
    for r in bad:
        n = sum(r["outside"].values())
        if runs and r["frame"] == runs[-1][1] + a.every:
            runs[-1][1] = r["frame"]; runs[-1][2] = max(runs[-1][2], n)
        else:
            runs.append([r["frame"], r["frame"], n])
    rec = {"rule": __doc__.split("\n\n")[0].replace("\n", " "), "method": __doc__.split("\n\n")[2].replace("\n", " "),
           "source": bpy.data.filepath, "shot": sc.get("shot_id"), "frames": [f0, f1, a.every],
           "control_forward_mm": a.control_forward_mm, "outer_skin_faces_at_rest": len(outer), "skin_faces": nfaces,
           "frames_outside": [r["frame"] for r in bad], "runs_first_last_max_samples": runs,
           "status": "FAIL" if bad else "PASS", "rows": rows}
    Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    seen = [r["seen"] for r in rows]
    if bad:
        worst = max(bad, key=lambda r: sum(r["outside"].values()))
        print(f"MOUTH_FAIL teeth or tongue seen outside the lips on {len(bad)} of {len(rows)} frame(s), runs {runs[:6]}; "
              f"worst {worst['frame']}: {worst['outside']}", file=sys.stderr)
        sys.exit(2)
    print(f"MOUTH_OK nothing of the teeth or tongue seen outside the lips on {len(rows)} frame(s) "
          f"(seen samples per frame {min(seen)}-{max(seen)})")


main(sys.argv[sys.argv.index("--") + 1:])
