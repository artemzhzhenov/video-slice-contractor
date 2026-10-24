"""Clearance of the rigid-on-socket accessories (hair/bangs, glasses) against the moving face.
Mode 'extremes' (character file): FACE_CTRL channel extremes and their combinations. Mode 'frames' (shot file):
every frame. Distance = signed distance of accessory vertices to the head skin (sign from the skin normal; the
face region is far from the open neck edge, so the sign is reliable) and unsigned distance to the brows and eyes.
Reported: the smallest skin distance (negative = inside the skin) and the smallest brow/eye distance."""
import bpy, bmesh, sys, json
from mathutils.bvhtree import BVHTree
mode = sys.argv[sys.argv.index("--") + 1]
sc = bpy.data.scenes["SLICE"]; ctrl = bpy.data.objects["FACE_CTRL"]
acc = [n for n in ("HERO_HAIR", "HERO_GLASSES") if n in bpy.data.objects]
def tree(dg, names):
    bm = bmesh.new()
    for n in names:
        oe = bpy.data.objects[n].evaluated_get(dg); tmp = bpy.data.meshes.new_from_object(oe); tmp.transform(oe.matrix_world); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    bm.normal_update(); tr = BVHTree.FromBMesh(bm); bm.free(); return tr
def measure(dg, name):
    skin = tree(dg, ["HERO_HEAD"]); feat = tree(dg, ["HERO_BROWS", "HERO_EYE_L", "HERO_EYE_R"])
    oe = bpy.data.objects[name].evaluated_get(dg); M = oe.matrix_world
    s_min, f_min = 1.0, 1.0
    sockM = bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world; inv = sockM.inverted()
    eL = inv @ bpy.data.objects["HERO_EYE_L"].evaluated_get(dg).matrix_world.translation
    eR = inv @ bpy.data.objects["HERO_EYE_R"].evaluated_get(dg).matrix_world.translation
    for v in list(oe.data.vertices)[::2]:
        p = M @ v.co; q = inv @ p                       # the face region in the head's own (socket) frame
        if q.y > (eL.y + eR.y) / 2 + 0.025 or abs(q.x - (eL.x + eR.x) / 2) > 0.065 or q.z < (eL.z + eR.z) / 2 - 0.03:
            continue                                    # forehead, brows, eyes, nose bridge (no ears), at any head turn
        h = skin.find_nearest(p, 0.04)
        if h[0] is not None:
            s = (p - h[0]).dot(h[1]) if name == "HERO_HAIR" else h[3]   # glasses: unsigned (the eye-socket openings flip the sign)
            s_min = min(s_min, s)
        g = feat.find_nearest(p, 0.04)
        if g[0] is not None: f_min = min(f_min, g[3])
    return s_min, f_min
rows = []
if mode == "extremes":
    base = {k: 0.0 for k in ctrl.keys() if isinstance(ctrl[k], float)}
    poses = {"neutral": {}, "brows_up": {"brow_inner_l": 1, "brow_inner_r": 1, "brow_outer_l": 1, "brow_outer_r": 1},
             "brows_down": {"brow_inner_l": -1, "brow_inner_r": -1, "brow_outer_l": -1, "brow_outer_r": -1},
             "cheeks_squint": {"cheek_raise_l": 1, "cheek_raise_r": 1, "squint_l": 1, "squint_r": 1},
             "nose_wrinkle": {"nose_wrinkle": 1}, "lids_wide": {"lid_aperture_l": 1, "lid_aperture_r": 1},
             "lids_shut": {"lid_aperture_l": -1, "lid_aperture_r": -1, "blink_l": 1, "blink_r": 1},
             "all_up": {"brow_inner_l": 1, "brow_inner_r": 1, "brow_outer_l": 1, "brow_outer_r": 1, "lid_aperture_l": 1, "lid_aperture_r": 1, "nostril_flare": 1},
             "all_squeezed": {"brow_inner_l": -1, "brow_inner_r": -1, "brow_outer_l": -1, "brow_outer_r": -1, "cheek_raise_l": 1, "cheek_raise_r": 1, "squint_l": 1, "squint_r": 1, "nose_wrinkle": 1, "upper_lip_raise_l": 1, "upper_lip_raise_r": 1}}
    for pname, vals in poses.items():
        for k in base: ctrl[k] = 0.0
        for k, v in vals.items(): ctrl[k] = float(v)
        ctrl.update_tag(); bpy.data.objects["HERO_HEAD"].update_tag()
        sc.frame_set(sc.frame_current + 1); sc.frame_set(sc.frame_current - 1)   # drivers re-evaluate on a frame change
        dg = bpy.context.evaluated_depsgraph_get()
        hb = bpy.data.objects["HERO_BROWS"].evaluated_get(dg); bz = max((hb.matrix_world @ v.co).z for v in hb.data.vertices)
        rows.append(("(brow top z)", pname, bz - 1.0, 0.0))
        for name in acc:
            s, f = measure(dg, name); rows.append((name, pname, s, f))
else:
    worst = {name: [1.0, None, 1.0, None] for name in acc}
    import os
    rng = os.environ.get("FRAMES")
    frs = range(sc.frame_start, sc.frame_end + 1) if not rng else range(int(rng.split("-")[0]), int(rng.split("-")[1]) + 1)
    for fr in frs:
        sc.frame_set(fr); dg = bpy.context.evaluated_depsgraph_get()
        for name in acc:
            s, f = measure(dg, name)
            if rng: print(f"  frame {fr} {name}: skin {s*1000:+.1f} brows/eyes {f*1000:.1f}")
            if s < worst[name][0]: worst[name][0], worst[name][1] = s, fr
            if f < worst[name][2]: worst[name][2], worst[name][3] = f, fr
    for name, w in worst.items(): rows.append((name, f"{sc.get('shot_id','')} all frames (worst at {w[1]}/{w[3]})", w[0], w[2]))
for name, pname, s, f in rows:
    print(f"CLEAR {name:13s} {pname:42s} skin {s*1000:+6.1f} mm   brows/eyes {f*1000:5.1f} mm")
