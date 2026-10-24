"""Rigid accessories against the moving character (burst 3, the synthetic children): the hair and the glasses hang
rigidly on the socket while the face moves by its channels and the body and hand move by the rig. Our own measurement,
independent of the contractor's tools. Runs under Blender on a shot file built with a child:

    blender -b SHOT_00N_subject_NN.blend --python-exit-code 2 -P slice/measurements/accessory_clearance.py -- \
        --out clearance.json [--extremes] [--every 1]

Per frame (every frame of the shot unless --every): each object's evaluated mesh is taken to world space through its
own matrix on a fresh copy (never in place), and distances are point-to-surface by BVH:
- the smallest vertex-to-surface distance between the two meshes, both ways (unsigned), and
- the number of their triangle pairs that INTERSECT (BVH overlap) — the head shell is open at the neck, eyes and mouth,
  so an inside test by normals is not reliable; an intersection test is exact.
Pairs: hair→skin, hair→brows/eyes, hair→body, glasses→skin, glasses→brows/eyes, hand→hair, hand→glasses. Each pair's
worst frame and value are reported, with the frames under the threshold (3 mm, the contractor's own). With --extremes,
the rest frame is also measured at the channel extremes (FACE_CTRL animation cleared) — brows up / down, cheeks and
squint up, nose wrinkle, lids wide / shut, all up, all squeezed. The glasses' seat is reported once at the rest frame:
the gap from the bridge to the nose skin, and the lens plane's distance in front of each eye's front point."""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
THRESHOLD_MM = 3.0
EXTREMES = {
    "neutral": {},
    "brows_up": {"brow_inner_l": 1, "brow_inner_r": 1, "brow_outer_l": 1, "brow_outer_r": 1},
    "brows_down": {"brow_inner_l": -1, "brow_inner_r": -1, "brow_outer_l": -1, "brow_outer_r": -1},
    "cheeks_squint": {"cheek_raise_l": 1, "cheek_raise_r": 1, "squint_l": 1, "squint_r": 1},
    "nose_wrinkle": {"nose_wrinkle": 1, "upper_lip_raise_l": 1, "upper_lip_raise_r": 1},
    "lids_wide": {"lid_aperture_l": 1, "lid_aperture_r": 1},
    "lids_shut": {"lid_aperture_l": -1, "lid_aperture_r": -1},
    "all_up": {"brow_inner_l": 1, "brow_inner_r": 1, "brow_outer_l": 1, "brow_outer_r": 1, "lid_aperture_l": 1, "lid_aperture_r": 1, "jaw_open": 1},
    "all_squeezed": {"brow_inner_l": -1, "brow_inner_r": -1, "brow_outer_l": -1, "brow_outer_r": -1, "cheek_raise_l": 1, "cheek_raise_r": 1,
                     "squint_l": 1, "squint_r": 1, "nose_wrinkle": 1, "mouth_corner_l": 1, "mouth_corner_r": 1},
}


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


def group(objs, dg):
    vs, fs, off = [], [], 0
    for o in objs:
        v, f = world_mesh(o, dg)
        vs.append(v)
        fs += [[i + off for i in p] for p in f]
        off += len(v)
    return (np.concatenate(vs) if vs else np.zeros((0, 3))), fs


def dist(a, b):
    """(min vertex-to-surface distance between the two meshes, both ways; the number of their triangle pairs that
    intersect). Unsigned distance plus an exact intersection test — the head shell is open (neck, eyes, mouth) and an
    inside test by normals is not reliable on it."""
    (va, fa), (vb, fb) = a, b
    if len(va) == 0 or len(vb) == 0:
        return None, None
    ta, tb = BVHTree.FromPolygons(va.tolist(), fa), BVHTree.FromPolygons(vb.tolist(), fb)
    d = min(min(tb.find_nearest(Vector(p))[3] for p in va), min(ta.find_nearest(Vector(p))[3] for p in vb))
    return d, len(ta.overlap(tb))


def measure(dg, ob):
    head = ob["HERO_HEAD"]
    skin = world_mesh(head, dg)
    parts = group([ob[n] for n in ("HERO_BROWS", "HERO_EYE_L", "HERO_EYE_R") if n in ob], dg)
    hair = world_mesh(ob["HERO_HAIR"], dg)
    body = group([o for o in bpy.data.collections["C_BODY"].objects if o.type == "MESH"], dg)
    hand = group([o for o in bpy.data.collections["C_HAND_FG"].objects if o.type == "MESH"], dg) if "C_HAND_FG" in bpy.data.collections else (np.zeros((0, 3)), [])
    glasses = world_mesh(ob["HERO_GLASSES"], dg) if "HERO_GLASSES" in ob else None
    r = {"hair_skin": dist(hair, skin), "hair_brows_eyes": dist(hair, parts), "hair_body": dist(hair, body), "hand_hair": dist(hand, hair)}
    if glasses is not None:
        r.update({"glasses_skin": dist(glasses, skin), "glasses_brows_eyes": dist(glasses, parts), "hand_glasses": dist(hand, glasses)})
    return {k: (None if v[0] is None else {"mm": round(v[0] * 1e3, 2), "crossing": v[1]}) for k, v in r.items()}


def glasses_seat(dg, ob):
    """The bridge's gap to the nose and the lens plane in front of each eye, in the socket's contract frame
    (C·socket⁻¹: X the character's left, Y up, Z forward), at the current frame."""
    if "HERO_GLASSES" not in ob:
        return None
    C = np.array([[1.0, 0, 0, 0], [0, 0, 1.0, 0], [0, -1.0, 0, 0], [0, 0, 0, 1.0]])
    S = C @ np.linalg.inv(np.array(ob["SOCKET_HEAD"].evaluated_get(dg).matrix_world))
    loc = lambda v: v @ S[:3, :3].T + S[:3, 3]  # noqa: E731
    g = loc(world_mesh(ob["HERO_GLASSES"], dg)[0])
    skin_w, skin_f = world_mesh(ob["HERO_HEAD"], dg)
    skin = loc(skin_w)
    eyes = {s: loc(world_mesh(ob[f"HERO_EYE_{s}"], dg)[0]) for s in ("L", "R")}
    ec = {s: v.mean(0) for s, v in eyes.items()}
    mid = (ec["L"] + ec["R"]) / 2
    half = abs(ec["L"][0] - ec["R"][0]) / 2
    bridge = g[np.abs(g[:, 0] - mid[0]) < 0.25 * half]            # the middle quarter between the eyes: the bridge
    tree = BVHTree.FromPolygons(skin.tolist(), skin_f)
    gap = min(tree.find_nearest(Vector(p))[3] for p in bridge) if len(bridge) else None
    near_eyes = g[np.abs(g[:, 1] - mid[1]) < 0.01]
    lens_z = float(np.median(near_eyes[:, 2])) if len(near_eyes) else float("nan")
    front = {s: float(v[:, 2].max()) for s, v in eyes.items()}
    return {"bridge_to_nose_skin_mm": None if gap is None else round(gap * 1e3, 2),
            "lens_plane_in_front_of_eye_mm": {s: round((lens_z - front[s]) * 1e3, 2) for s in front},
            "nose_tip_in_front_of_lens_plane_mm": round((float(skin[:, 2].max()) - lens_z) * 1e3, 2),
            "note": "socket contract frame, +Z forward; a lens plane in front of the nose tip shows as a negative last value"}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--extremes", action="store_true")
    ap.add_argument("--every", type=int, default=1)
    a = ap.parse_args(argv)
    sc = bpy.data.scenes["SLICE"]
    ob = bpy.data.objects
    rows = []
    for f in range(sc.frame_start, sc.frame_end + 1, a.every):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        rows.append({"frame": f, **measure(dg, ob)})
    pairs = [k for k in rows[0] if k != "frame"]
    worst = {}
    for k in pairs:
        vals = [(r[k]["mm"], r["frame"], r[k]["crossing"]) for r in rows if r[k] is not None]
        if vals:
            v, fr, _ = min(vals)
            worst[k] = {"min_mm": v, "frame": fr, "frames_under_threshold": [x[1] for x in vals if x[0] < THRESHOLD_MM],
                        "frames_crossing": [x[1] for x in vals if x[2]], "max_crossing_pairs": max(x[2] for x in vals)}
    rec = {"rule": __doc__.split("\n\n")[1].replace("\n", " "), "source": bpy.data.filepath, "shot": sc.get("shot_id"),
           "frames": [sc.frame_start, sc.frame_end, a.every], "threshold_mm": THRESHOLD_MM, "worst": worst}
    ctrl = ob["FACE_CTRL"]
    if a.extremes:
        ctrl.animation_data_clear()
        ext = {}
        for name, vals in EXTREMES.items():
            for ch in CMAP["channels"]:
                ctrl[ch["channel"]] = float(vals.get(ch["channel"], 0.0))
            ctrl.update_tag()                  # a property set from Python does not tag the drivers; frame_set on the
            sc.frame_set(sc.frame_start)       # same frame would not re-evaluate them (measured: the brows did not move)
            bpy.context.view_layer.update()
            ext[name] = measure(bpy.context.evaluated_depsgraph_get(), ob)
        rec["extremes_at_rest_frame"] = ext
        for ch in CMAP["channels"]:
            ctrl[ch["channel"]] = 0.0
        ctrl.update_tag()
        sc.frame_set(sc.frame_start)
        bpy.context.view_layer.update()
        rec["glasses_seat"] = glasses_seat(bpy.context.evaluated_depsgraph_get(), ob)
    Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    print("ACCESSORY_CLEARANCE " + json.dumps({k: (v["min_mm"], v["frame"], len(v["frames_under_threshold"]), len(v["frames_crossing"])) for k, v in worst.items()}))


main(sys.argv[sys.argv.index("--") + 1:])
