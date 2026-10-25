"""Eyes and lids of a character build — burst 3, the synthetic children (found 2026-10-25: five of the nine children's
lids failed on the eye while every other gate passed — an open eye under a "closed" lid, the eyeball through the lower
lid at rest, lids blown up into a pillow; the default head closes cleanly). Our own measurement; runs under Blender on
a character or shot file:

    blender -b <file.blend> --python-exit-code 2 -P slice/measurements/eye_lid_check.py -- --out <dir> \
        [--sheet] [--samples 32] [--res 1200]

FACE_CTRL's animation is cleared, every channel set to 0, then each lid state in turn (STATES: rest; blink; lid_aperture
−1 and +1; squint; cheek_raise — both sides together), at the file's first frame, the head's own pose kept. Per eye:
THE EYEBALL is the evaluated HERO_EYE_* mesh with a sphere fitted to it (least squares; a build's eye is a sphere, the fit
residual is reported); THE LID is every HERO_HEAD vertex that a closure key (fc_lid_close_full_* / fc_lid_close_mid_*)
moves by more than 0.1 mm, assigned to the nearer eye. Measured, all in metres in the scene's world:
1. inside — the deepest lid vertex inside the eyeball sphere, in every state (negative = inside): the skin never goes
   through the eye, open or shut.
2. visible — the fraction of the eyeball's points facing a camera that the camera sees past HERO_HEAD (a ray from the
   point to the camera that hits no head face), from the front and from 35° to each side, 0.4 m away along the head's
   forward axis (SOCKET_HEAD −Y). At rest the open eye must be visible (the measurement's own positive control); shut
   (blink, lid_aperture −1) nothing of it may be.
3. standoff — shut, the median over the eyeball's front points (within FRONT_DEG of its forward axis) of the distance
   along the ray to the front camera to the skin that covers the point: a closed lid lies on the eye; a pillow, or a lid
   torn at its corner, stands off it. (The lid vertices' own distance from the eye does not tell: the closure moves the
   fold up to the brow, which stands 8–10 mm off the eye on the clean default head too — measured 2026-10-25.)
   Reported, not gated: the shut lid's self-intersections (pairs of faces at the lid that cross and share no vertex) —
   16 on the default head, 37 on a child whose shut lid is clean to the eye: they do not separate.
Hair, brows and glasses are not occluders: the lid has to cover the eye by itself. Writes <out>/eye_lid_report.json;
with --sheet, <out>/sheet/<state>_<view>.png — a close-up of the eyes per state (hair hidden), for the eye. Exit 0 PASS,
2 FAIL or NOT_VERIFIED (never a pass on missing evidence)."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
STATES = {"rest": {}, "blink": {"blink_l": 1.0, "blink_r": 1.0}, "lid_aperture_-1": {"lid_aperture_l": -1.0, "lid_aperture_r": -1.0},
          "lid_aperture_+1": {"lid_aperture_l": 1.0, "lid_aperture_r": 1.0}, "squint": {"squint_l": 1.0, "squint_r": 1.0},
          "cheek_raise": {"cheek_raise_l": 1.0, "cheek_raise_r": 1.0}}
SHUT = ("blink", "lid_aperture_-1")
LID_KEYS = ("fc_lid_close_full_", "fc_lid_close_mid_")
LID_MOVE_M = 1e-4
VIEWS_DEG = {"front": 0.0, "left35": 35.0, "right35": -35.0}
CAM_DIST_M, FRONT_DEG, N_POINTS = 0.4, 50.0, 2000
# PROVISIONAL (2026-10-25), calibrated on the default head v04.1, the nine children as built and the same nine with the
# eye centre fixed — slice/measurements/eye_lid_2026-10-25/: inside never below this (contact within 0.05 mm is not a
# cut); shut, nothing of the eye visible; shut, the median standoff not above this (clean ≤ 2.56 mm, a pillow or a lid
# torn at its corner ≥ 3.01 mm)
INSIDE_MIN_M, VISIBLE_SHUT_MAX, STANDOFF_MAX_M = -5e-5, 0.0, 0.0028


def fit_sphere(p):
    """Least-squares sphere through points p (n×3): centre, radius, the largest |distance − radius|."""
    A = np.c_[2 * p, np.ones(len(p))]
    b = (p ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = x[:3]
    r = float(math.sqrt(x[3] + c @ c))
    return c, r, float(np.abs(np.linalg.norm(p - c, axis=1) - r).max())


def sphere_points(n):
    """n points spread evenly over the unit sphere (Fibonacci lattice) — deterministic."""
    k = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * k / n)
    th = math.pi * (1 + 5 ** 0.5) * k
    return np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]


def set_state(ctrl, sc, values):
    for ch in CMAP["channels"]:
        ctrl[ch["channel"]] = float(values.get(ch["channel"], 0.0))
    ctrl.update_tag()                  # a property set from Python does not tag the drivers, and frame_set on the same
    sc.frame_set(sc.frame_start)       # frame would not re-evaluate them (accessory_clearance.py, measured)
    bpy.context.view_layer.update()


def world_mesh(name):
    dg = bpy.context.evaluated_depsgraph_get()
    o = bpy.data.objects[name].evaluated_get(dg)
    me = o.to_mesh()
    M = o.matrix_world.copy()
    v = np.array([(M @ x.co)[:] for x in me.vertices])
    f = [tuple(p.vertices) for p in me.polygons]
    o.to_mesh_clear()
    return v, f


def lid_vertices(head):
    """HERO_HEAD vertex indices that the closure keys move by more than LID_MOVE_M, per side (l / r)."""
    keys = head.data.shape_keys
    if keys is None:
        return {}
    basis = np.array([kb.co[:] for kb in keys.key_blocks[0].data])
    out = {}
    for kb in keys.key_blocks[1:]:
        if kb.name.startswith(LID_KEYS):
            d = np.linalg.norm(np.array([x.co[:] for x in kb.data]) - basis, axis=1)
            out.setdefault(kb.name[-1], set()).update(np.where(d > LID_MOVE_M)[0].tolist())
    return {s: np.array(sorted(i)) for s, i in out.items()}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--res", type=int, default=1200)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc = bpy.data.scenes["SLICE"] if "SLICE" in bpy.data.scenes else bpy.context.scene
    rec = {"rule": __doc__.split("\n\n")[2].replace("\n", " "), "source": bpy.data.filepath,
           "gates": {"inside_min_m": INSIDE_MIN_M, "visible_shut_max": VISIBLE_SHUT_MAX, "standoff_max_m": STANDOFF_MAX_M,
                     "status": "PROVISIONAL — calibrated 2026-10-25, slice/measurements/eye_lid_2026-10-25/"},
           "states": {}, "failed": [], "status": "NOT_VERIFIED"}
    missing = [n for n in ("FACE_CTRL", "SOCKET_HEAD", "HERO_HEAD", "HERO_EYE_L", "HERO_EYE_R") if n not in bpy.data.objects]
    head = bpy.data.objects.get("HERO_HEAD")
    lids = lid_vertices(head) if head is not None else {}
    if missing or set(lids) != {"l", "r"}:
        rec["reason"] = f"missing objects {missing}" if missing else f"no closure keys on HERO_HEAD for both eyes (found {sorted(lids)})"
        return finish(out, rec)
    ctrl = bpy.data.objects["FACE_CTRL"]
    ctrl.animation_data_clear()        # its keys would overwrite the channels on frame_set (measured 2026-10-25)
    eye_side = {"l": "HERO_EYE_L", "r": "HERO_EYE_R"}   # fc_*_l is the anatomical left, as HERO_EYE_L
    unit = sphere_points(N_POINTS)
    for state, values in STATES.items():
        set_state(ctrl, sc, values)
        hv, hf = world_mesh("HERO_HEAD")
        tree = BVHTree.FromPolygons([Vector(p) for p in hv], hf)
        sock = bpy.data.objects["SOCKET_HEAD"].matrix_world
        fwd = np.array((sock.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized())
        up = np.array((sock.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized())
        row = {}
        for side, ename in eye_side.items():
            ev, _ = world_mesh(ename)
            c, r, resid = fit_sphere(ev)
            lid = hv[lids[side]]
            # each lid vertex belongs to the nearer eye; keep the ones nearer this one
            other = fit_sphere(world_mesh(eye_side["r" if side == "l" else "l"])[0])[0]
            lid = lid[np.linalg.norm(lid - c, axis=1) <= np.linalg.norm(lid - other, axis=1)]
            dist = np.linalg.norm(lid - c, axis=1) - r
            vis = {}
            for vname, deg in VIEWS_DEG.items():
                d = np.array(Matrix.Rotation(math.radians(deg), 3, Vector(up)) @ Vector(fwd))
                cam = c + d * CAM_DIST_M
                pts = c + unit * r
                facing = ((cam - pts) * unit).sum(1) > 0.05 * np.linalg.norm(cam - pts, axis=1)
                seen = 0
                for p in pts[facing]:
                    to = cam - p
                    L = float(np.linalg.norm(to))
                    hit = tree.ray_cast(Vector(p + to / L * 1e-5), Vector(to / L), L)
                    seen += hit[0] is None
                vis[vname] = round(seen / max(1, int(facing.sum())), 5)
            standoff = None
            if state in SHUT:
                cam = c + fwd * CAM_DIST_M
                ts = []
                for u in unit[unit @ fwd > math.cos(math.radians(FRONT_DEG))]:
                    p = c + u * r
                    to = cam - p
                    L = float(np.linalg.norm(to))
                    hit = tree.ray_cast(Vector(p + to / L * 1e-5), Vector(to / L), L)
                    if hit[0] is not None:
                        ts.append(hit[3])
                standoff = float(np.median(ts)) if ts else None
            row[ename] = {"sphere_radius_mm": round(r * 1e3, 3), "sphere_fit_residual_mm": round(resid * 1e3, 4),
                          "lid_vertices": int(len(lid)), "inside_mm": round(float(dist.min()) * 1e3, 3),
                          "visible": vis, "standoff_mm": round(standoff * 1e3, 3) if standoff is not None else None}
            if dist.min() < INSIDE_MIN_M:
                rec["failed"].append(f"{state} {ename}: a lid vertex {dist.min() * 1e3:.2f} mm inside the eyeball")
            if state in SHUT and max(vis.values()) > VISIBLE_SHUT_MAX:
                rec["failed"].append(f"{state} {ename}: {max(vis.values()) * 100:.1f} % of the eye visible through the shut lid")
            if state in SHUT and standoff is not None and standoff > STANDOFF_MAX_M:
                rec["failed"].append(f"{state} {ename}: the shut lid stands {standoff * 1e3:.2f} mm off the eye (median)")
            if state == "rest" and min(vis.values()) <= 0.0:
                rec["reason"] = f"the open eye {ename} is not visible at rest — the measurement cannot tell open from shut"
                rec["states"][state] = row
                return finish(out, rec)
        if state in SHUT:
            ids = set(lids["l"].tolist()) | set(lids["r"].tolist())
            lf = [f for f in hf if any(i in ids for i in f)]
            sub = BVHTree.FromPolygons([Vector(p) for p in hv], lf)
            row["lid_self_intersections"] = sum(1 for x, y in sub.overlap(sub) if x < y and not set(lf[x]) & set(lf[y]))
        rec["states"][state] = row
        print(f"EYE_LID_STATE {state} " + json.dumps({k: (v["inside_mm"], max(v["visible"].values()), v["standoff_mm"]) if isinstance(v, dict) else v
                                                     for k, v in row.items()}), flush=True)
    rec["status"] = "FAIL" if rec["failed"] else "PASS"
    if a.sheet:
        rec["sheet"] = render_sheet(sc, ctrl, out / "sheet", a.samples, a.res)
    return finish(out, rec)


def render_sheet(src, ctrl, out, samples, res):
    """Close-ups of both eyes per state, front and 35° to the left: our camera on the head's forward axis, the file's
    lights plus a soft fill at the camera, hair hidden. A scene of its own (the slice scene has many view layers)."""
    out.mkdir(parents=True, exist_ok=True)
    sc = bpy.data.scenes.new("EYE_LID_SHEET")
    for c in src.collection.children:
        if c.name in ("C_HEAD", "C_BODY", "C_LIGHTS"):
            sc.collection.children.link(c)
    sc.view_settings.view_transform = src.view_settings.view_transform
    sc.display_settings.display_device = src.display_settings.display_device
    camd = bpy.data.cameras.new("EYE_LID_CAM")
    camd.lens, camd.sensor_width = 100.0, 36.0
    cam = bpy.data.objects.new("EYE_LID_CAM", camd)
    sc.collection.objects.link(cam)
    ld = bpy.data.lights.new("EYE_LID_FILL", "AREA")
    ld.energy, ld.size = 3.0, 0.3
    li = bpy.data.objects.new("EYE_LID_FILL", ld)
    sc.collection.objects.link(li)
    sc.camera = cam
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception:  # noqa: BLE001 — no Metal (the contractor's Linux): CPU, same picture, slower
        sc.cycles.device = "CPU"
    sc.cycles.samples, sc.cycles.use_denoising, sc.cycles.seed = samples, True, 0
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = res, int(res * 7 / 16), 100
    sc.render.use_motion_blur = False
    if hasattr(sc.render.image_settings, "media_type"):
        sc.render.image_settings.media_type = "IMAGE"
    sc.render.image_settings.file_format = "PNG"
    files = []
    for state in ("rest", "blink", "squint", "cheek_raise"):
        set_state(ctrl, src, STATES[state])
        sc.frame_set(src.frame_start)
        mid = (bpy.data.objects["HERO_EYE_L"].matrix_world.translation + bpy.data.objects["HERO_EYE_R"].matrix_world.translation) / 2
        sock = bpy.data.objects["SOCKET_HEAD"].matrix_world
        fwd = (sock.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
        up = (sock.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        for view in ("front", "left35"):
            d = Matrix.Rotation(math.radians(VIEWS_DEG[view]), 3, up) @ fwd
            pos = mid + d * 0.42
            z = (pos - mid).normalized()
            x = up.cross(z).normalized()
            y = z.cross(x)
            cam.matrix_world = Matrix(((x[0], y[0], z[0], pos[0]), (x[1], y[1], z[1], pos[1]), (x[2], y[2], z[2], pos[2]), (0, 0, 0, 1)))
            li.matrix_world = cam.matrix_world @ Matrix.Translation((0.0, 0.05, 0.05))
            sc.render.filepath = str(out / f"{state}_{view}.png")
            bpy.ops.render.render(write_still=True, scene=sc.name)
            files.append(f"sheet/{state}_{view}.png")
    set_state(ctrl, src, {})
    return files


def finish(out, rec):
    (out / "eye_lid_report.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    if rec["status"] == "PASS":
        print(f"EYE_LID_OK {len(rec['states'])} states, both eyes -> {out / 'eye_lid_report.json'}")
        return 0
    print(f"EYE_LID_{rec['status']} " + ("; ".join(rec["failed"][:6]) or rec.get("reason", "")), file=sys.stderr)
    return 2


sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
