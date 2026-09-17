"""See-through holes in the character's silhouette — the measured form of contractor ACCEPTANCE
item 2в ("the body under the clothing is removed and the turn shows no hole at the collar, the
sleeves or the hem"). Until 2026-09-17 that criterion was judged by eye on the previews the
contractor chose; this is the gate.

    blender -b <scene.blend> --python-exit-code 2 -P slice/check_silhouette.py -- --out <dir>

What it does, from conventions.json → silhouette: links the character collections into a fresh
scene WITHOUT C_ENV (an environment behind the character fills every opening and hides the
defect), gives every render-visible object an opaque emission material of its own colour, poses
the rig at the declared poses (rest and the slice's maximum head turn), renders the declared
views with a transparent film at one sample and a 0.01 px box filter (geometry only, no noise),
and counts the connected background regions that do NOT reach the image border. Such a region is
a line of sight that enters the silhouette and leaves it again: a hole. The objects bordering it
are read from the same render, so the verdict names them.

Every view is written as a PNG beside silhouette_report.json — the evidence, not just a number.
Exit 0 with SILHOUETTE_OK; exit 2 with SILHOUETTE_ERROR and the offending views listed."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
N = CONV["scene_naming"]
S = CONV["silhouette"]


class SilhouetteError(Exception):
    pass


def fail(msg):
    print(f"SILHOUETTE_ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def palette(n):
    """n visually separated opaque colours, deterministic in the object order."""
    out = []
    for i in range(n):
        h = (i * 0.61803398875) % 1.0
        v = 1.0 if i % 2 == 0 else 0.72
        r, g, b = [max(0.0, min(1.0, abs(((h + k / 3.0) % 1.0) * 6.0 - 3.0) - 1.0)) for k in (0, 1, 2)]
        out.append((r * v, g * v, b * v))
    return out


def render_visible(colls):
    objs = []
    for c in colls:
        coll = bpy.data.collections.get(c)
        if coll is None:
            raise SilhouetteError(f"collection {c} missing — this is not a slice scene")
        for o in coll.all_objects:
            if o.type == "MESH" and not o.hide_render and o.visible_camera:
                objs.append(o)
    return sorted(set(objs), key=lambda o: o.name)


def id_materials(objs):
    """One opaque emission material per object. A transparent garment material would otherwise
    read as a hole; the colour is what makes the neighbours of a hole nameable."""
    cols = palette(len(objs))
    by_colour = {}
    for o, col in zip(objs, cols):
        m = bpy.data.materials.new(f"SILHOUETTE_ID_{o.name}")
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs[0].default_value = (*col, 1.0)
        em.inputs[1].default_value = 1.0
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs[0], out.inputs[0])
        o.data.materials.clear()
        o.data.materials.append(m)
        for p in o.data.polygons:
            p.material_index = 0
        by_colour[o.name] = col
    if len({tuple(round(c, 4) for c in v) for v in by_colour.values()}) != len(by_colour):
        raise SilhouetteError("two objects share an id colour — meshes are shared between objects")
    return by_colour


def pose_rig(rig, bones):
    rig.animation_data_clear()
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
    for name, axis, deg in bones:
        bone = N["bones"].get(name, name)
        pb = rig.pose.bones.get(bone)
        if pb is None:
            raise SilhouetteError(f"bone {bone} missing from {rig.name} — the pose of conventions → silhouette cannot be set")
        r = list(pb.rotation_euler)
        r["xyz".index(axis)] = math.radians(deg)
        pb.rotation_euler = r
    bpy.context.view_layer.update()


def figure_bounds(objs, depsgraph):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        ev = o.evaluated_get(depsgraph)
        for corner in ev.bound_box:
            p = ev.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], p[i]) for i in range(3)))
            hi = Vector((max(hi[i], p[i]) for i in range(3)))
    return lo, hi


def place_camera(cam, scene, view, socket, bounds):
    """Views are declared in conventions → silhouette.views. 'socket' views orbit the head socket
    at a fixed distance; 'figure' views frame the whole character from its measured bounds, so the
    check does not depend on how tall the asset is."""
    yaw, pitch = math.radians(view["yaw_deg"]), math.radians(view["pitch_deg"])
    d = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch)))
    cam.data.lens = view["lens_mm"]
    if view["anchor"] == "socket":
        target = socket + Vector(view.get("target_offset_m", [0.0, 0.0, 0.0]))
        dist = view["distance_m"]
    elif view["anchor"] == "figure":
        lo, hi = bounds
        target = (lo + hi) / 2.0
        height = max(hi.z - lo.z, 1e-3)
        sensor_v = cam.data.sensor_width * scene.render.resolution_y / scene.render.resolution_x
        dist = height * view["margin"] * cam.data.lens / sensor_v
    else:
        raise SilhouetteError(f"view {view['name']}: unknown anchor {view['anchor']}")
    cam.location = target + d * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


def enclosed_components(alpha):
    """Connected background regions that do not touch the image border: 4-connected labelling in
    one pass with union-find, then the roots that never reached a border pixel."""
    bg = alpha < 0.5
    h, w = bg.shape
    label = np.zeros((h, w), np.int32)
    parent = [0]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for y in range(h):
        xs = np.nonzero(bg[y])[0]
        for x in xs:
            up = label[y - 1, x] if y else 0
            left = label[y, x - 1] if x else 0
            if up and left:
                label[y, x] = min(up, left)
                union(int(up), int(left))
            elif up or left:
                label[y, x] = up or left
            else:
                parent.append(len(parent))
                label[y, x] = len(parent) - 1
    roots = np.array([find(i) for i in range(len(parent))], dtype=np.int32)
    label = roots[label]
    border = set(label[0].tolist()) | set(label[h - 1].tolist()) | set(label[:, 0].tolist()) | set(label[:, w - 1].tolist())
    sizes = np.bincount(label.ravel())
    return label, [int(r) for r in np.nonzero(sizes)[0] if r and r not in border]


def neighbours_of(label, root, rgba, by_colour):
    m = label == root
    ring = np.zeros_like(m)
    for sy, sx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ring |= np.roll(np.roll(m, sy, axis=0), sx, axis=1)
    ring &= ~m & (rgba[..., 3] > 0.9)
    names, cols = list(by_colour), np.array(list(by_colour.values()), dtype=np.float32)
    got = {}
    px = rgba[ring][:, :3]
    if len(px):
        idx = np.abs(px[:, None, :] - cols[None, :, :]).sum(axis=2).argmin(axis=1)
        for i, c in zip(*np.unique(idx, return_counts=True)):
            got[names[int(i)]] = int(c)
    return dict(sorted(got.items(), key=lambda kv: -kv[1]))


def ray_geometry(scene, cam, socket):
    """A pixel → the distance in metres between SOCKET_HEAD and the line of sight through it.
    The region of interest is measured on the ray, not on the projection: a line of sight that
    slips past the neck passes within centimetres of the socket, while the gap between a hanging
    arm and the torso passes a quarter of a metre away from it, however close the two look in a
    close-up view."""
    m = cam.matrix_world
    TR, BR, BL, TL = [m @ v for v in cam.data.view_frame(scene=scene)]
    o = m.translation.copy()
    w, h = scene.render.resolution_x, scene.render.resolution_y

    def distance(px, py):
        u, v = (px + 0.5) / w, (py + 0.5) / h
        p = BL.lerp(BR, u).lerp(TL.lerp(TR, u), v)
        d = (p - o).normalized()
        return (socket - o).cross(d).length

    return distance


def analyse(path, by_colour, rule, ray_distance, radius_m):
    img = bpy.data.images.load(str(path))
    w, h = img.size
    rgba = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    label, roots = enclosed_components(rgba[..., 3])
    found = []
    for r in roots:
        ys, xs = np.nonzero(label == r)
        if len(ys) < rule["reported_min_px"]:
            continue
        near = min(ray_distance(float(x), float(y)) for x, y in zip(xs, ys))
        found.append({"pixels": int(len(ys)),
                      "centre_px": [int(xs.mean()), int(ys.mean())],
                      "bbox_px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                      "nearest_ray_to_socket_m": round(float(near), 4),
                      "in_region_of_interest": bool(near <= radius_m),
                      "bordered_by": neighbours_of(label, r, rgba, by_colour)})
    found.sort(key=lambda c: -c["pixels"])
    return found


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--json", default="")
    args = p.parse_args(argv)
    out = Path(args.out)
    (out / "views").mkdir(parents=True, exist_ok=True)

    src = bpy.data.scenes.get("SLICE")
    if src is None:
        fail("scene SLICE missing — this is not a slice scene")
    scene = bpy.data.scenes.new("SILHOUETTE")
    linked = []
    for c in S["collections"]:
        coll = bpy.data.collections.get(c)
        if coll is None:
            fail(f"collection {c} missing — this is not a slice scene")
        scene.collection.children.link(coll)
        linked.append(c)
    bpy.context.window.scene = scene
    scene.frame_set(src.frame_start)

    r = S["render"]
    scene.render.engine = "CYCLES"
    scene.cycles.samples = r["samples"]
    scene.cycles.use_denoising = False
    scene.cycles.pixel_filter_type = "BOX"
    scene.cycles.filter_width = r["pixel_filter_px"]
    scene.render.film_transparent = r["film_transparent"]
    scene.render.resolution_x, scene.render.resolution_y = r["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Raw"

    try:
        objs = render_visible(S["collections"])
        if not objs:
            raise SilhouetteError("no render-visible mesh in the character collections")
        by_colour = id_materials(objs)
        rig = bpy.data.objects.get(N["rig"])
        if rig is None:
            raise SilhouetteError(f"{N['rig']} missing — the declared poses cannot be set")
        cam = bpy.data.objects.get(N["camera"])
        if cam is None:
            raise SilhouetteError(f"{N['camera']} missing")
        cam.animation_data_clear()
        cam.parent = None
        scene.camera = cam
        socket_obj = bpy.data.objects.get("SOCKET_HEAD")
        if socket_obj is None:
            raise SilhouetteError("SOCKET_HEAD missing")

        report = {"schema_note": "see-through holes in the character silhouette; conventions.json → silhouette",
                  "criterion": S["criterion"], "collections": linked, "excluded": S["excluded"],
                  "render": r, "pose_status": S["pose"]["status"], "pass_rule": S["pass_rule"],
                  "objects": by_colour, "views": []}
        failed = []
        for pose_name, bones in S["pose"]["poses"].items():
            pose_rig(rig, bones)
            dg = bpy.context.evaluated_depsgraph_get()
            socket = socket_obj.evaluated_get(dg).matrix_world.translation.copy()
            bounds = figure_bounds(objs, dg)
            for view in S["views"]:
                place_camera(cam, scene, view, socket, bounds)
                png = out / "views" / f"{pose_name}.{view['name']}.png"
                scene.render.filepath = str(png)
                bpy.ops.render.render(write_still=True)
                holes = analyse(png, by_colour, S["pass_rule"], ray_geometry(scene, cam, socket),
                                S["region_of_interest"]["radius_m"])
                gated = [c for c in holes if c["in_region_of_interest"]]
                worst = max([c["pixels"] for c in gated], default=0)
                bad = worst >= S["pass_rule"]["max_enclosed_component_px"]
                row = {"pose": pose_name, "view": view["name"], "image": png.name,
                       "largest_hole_px": worst, "largest_reported_px": max([c["pixels"] for c in holes], default=0),
                       "status": "FAIL" if bad else "PASS", "holes": holes}
                report["views"].append(row)
                if bad:
                    row["worst"] = gated[0]
                    failed.append(row)
                print(f"SILHOUETTE_VIEW {pose_name}.{view['name']} {row['status']} seam={worst}px"
                      f" outside_seam={max([c['pixels'] for c in holes if not c['in_region_of_interest']], default=0)}px"
                      f" nearest={min([c['nearest_ray_to_socket_m'] for c in holes], default=-1)}m"
                      + (f" bordered_by={list(gated[0]['bordered_by'])} at {gated[0]['centre_px']}" if bad else ""))
        report["status"] = "FAIL" if failed else "PASS"
        report["failed_views"] = [f"{f['pose']}.{f['view']}" for f in failed]
        (out / "silhouette_report.json").write_text(json.dumps(report, indent=1))
        if args.json:
            Path(args.json).write_text(json.dumps(report, indent=1))
        if failed:
            w = max(failed, key=lambda f: f["largest_hole_px"])
            fail(f"see-through hole at the head↔body seam in {report['failed_views']}: "
                 f"{w['largest_hole_px']} px in {w['pose']}.{w['view']}, bordered by {list(w['worst']['bordered_by'])} "
                 f"(threshold {S['pass_rule']['max_enclosed_component_px']} px, {S['pass_rule']['status']}) "
                 f"— see {out / 'views'}")
        print(f"SILHOUETTE_OK {len(report['views'])} views, no enclosed background region "
              f"≥ {S['pass_rule']['max_enclosed_component_px']} px within {S['region_of_interest']['radius_m']} m "
              f"of SOCKET_HEAD -> {out / 'silhouette_report.json'}")
    except SilhouetteError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
