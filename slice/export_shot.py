"""Export the HEAD_RENDER_BUNDLE data of one shot from the template/asset scene (ADR-0002 D5
rows 6, 7, 8, 11, 12; proposal §1, §3, §5):

    blender -b <scene.blend> --python-exit-code 2 -P slice/export_shot.py -- --shot SHOT_001 --out <pkg>/shots/SHOT_001/exports

Writes camera.json, socket.json, joints.json, socket_boundary.json, lighting_ref.json,
performance_track.json, proxies.abc (+ .meta.json), proxies_rest.obj, default_head_rest.obj,
default_head_deformed.npy (QC only — the D7 round-trip's per-sample head) and
export_manifest.json (sha256 of each file, plus the SOCKET_SPACE_ROOT world matrix every file is
relative to).

Transform conventions (conventions.json → exports.transform_conventions): the socket is converted
as a similarity (its local frame becomes socket-oriented); camera and joints are converted by
left-multiplication only, keeping their own local frames. Any scale or mirror violation, any
channel outside its range, any NaN, any animated light or intrinsic: raise and stop — nothing is
normalised, clamped or defaulted (CLAUDE.md §6)."""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Matrix
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import camera_model as cm  # noqa: E402
from slice import socketspace as ss  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
SMAP = json.loads((ROOT / "slice" / "state_map.json").read_text())
N = CONV["scene_naming"]
OFFSETS = CONV["exports"]["sub_frame_offsets_frames"]
GEOMETRY_TYPES = {"MESH", "CURVES", "CURVE", "SURFACE", "META", "FONT", "POINTCLOUD", "VOLUME"}
if 0.0 not in OFFSETS:
    raise RuntimeError("conventions.exports.sub_frame_offsets_frames must contain the centre sample 0.0")


class ExportError(RuntimeError):
    pass


def m4(mat):
    return [[float(mat[i][j]) for j in range(4)] for i in range(4)]


def finite(obj, where):
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ExportError(f"non-finite value in {where}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            finite(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            finite(v, f"{where}[{i}]")


def dump(out, name, obj):
    finite(obj, name)
    (out / name).write_text(json.dumps(obj, indent=1, allow_nan=False) + "\n")


def set_time(scene, frame, offset):
    """frame + offset with offset in (-1, 1); Blender wants subframe in [0, 1). For a CENTRED
    180° shutter the open instant is frame - 0.25 = (frame - 1) + 0.75 — verified against
    Cycles' sampling on 5.2.1 (review 2026-09-15)."""
    f, sub = frame, offset
    if sub < 0:
        f, sub = frame - 1, 1.0 + offset
    scene.frame_set(int(f), subframe=float(sub))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_scene_conventions(scene):
    if scene.unit_settings.system != "METRIC" or abs(scene.unit_settings.scale_length - 1.0) > 1e-9:
        raise ExportError(f"scene units are not 1 unit = 1 m ({scene.unit_settings.system}, scale {scene.unit_settings.scale_length})")
    if scene.render.fps != CONV["fps"] or scene.render.fps_base != 1.0:
        raise ExportError(f"fps {scene.render.fps}/{scene.render.fps_base} is not {CONV['fps']}")
    if scene.render.frame_map_old != scene.render.frame_map_new:
        raise ExportError(f"the scene remaps time ({scene.render.frame_map_old} → {scene.render.frame_map_new}): the shot's frames would not be "
                          "its own — render_passes.py stretches time itself for the vectors (ADR-0002 amendment 2026-09-25)")
    vp = CONV["render_profiles"]["video"]
    want_shutter = vp["shutter_angle_deg"] / 360.0
    if not scene.render.use_motion_blur or abs(scene.render.motion_blur_shutter - want_shutter) > 1e-9:
        raise ExportError(f"scene shutter {scene.render.motion_blur_shutter} frames ≠ conventions {want_shutter} — the sub-frame offsets {OFFSETS} would be wrong")
    pos = {"CENTER": "CENTRED", "START": "START", "END": "END"}[scene.render.motion_blur_position]
    if pos != vp["shutter_position"]:
        raise ExportError(f"shutter position {pos} ≠ conventions {vp['shutter_position']}")
    if scene.render.resolution_percentage != 100 or scene.render.pixel_aspect_x != 1.0 or scene.render.pixel_aspect_y != 1.0:
        raise ExportError("resolution_percentage must be 100 and pixel aspect 1:1 for the exported intrinsics to be pixel-true")


def intrinsics(scene, cam):
    """mm-level camera data plus pixel intrinsics for the scene's resolution AND for every
    render profile (`px_by_profile`): the still profile renders a different frame than the
    video profile, so one pixel principal point cannot serve both (found by the D7 round-trip
    on the still, 2026-09-15). Fit rules and shift signs: slice/camera_model.py."""
    d = cam.data
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    shift = (d.shift_x, d.shift_y)
    here = cm.px_intrinsics(d.lens, d.sensor_width, d.sensor_height, d.sensor_fit, shift, rx, ry)
    return {"focal_length_mm": d.lens, "filmback_mm": [d.sensor_width, d.sensor_height],
            "focal_length_px": here["focal_length_px"],
            "sensor_fit": d.sensor_fit,
            "principal_point_px": here["principal_point_px"],
            "shift": list(shift),
            "px_by_profile": {name: cm.px_intrinsics(d.lens, d.sensor_width, d.sensor_height, d.sensor_fit, shift, *prof["resolution"])
                              for name, prof in CONV["render_profiles"].items()},
            "near_m": d.clip_start, "far_m": d.clip_end,
            "focus_distance_m": d.dof.focus_distance if d.dof.use_dof else "NOT_APPLICABLE",
            "f_stop": d.dof.aperture_fstop if d.dof.use_dof else "NOT_APPLICABLE"}


def export_camera(scene, cam, root, frames, out):
    vp = CONV["render_profiles"]["video"]
    rec = {"schema_note": "camera per frame with sub-frame samples; proposal §1 row 6, ADR-0002 D7",
           "camera": cam.name, "local_convention": CONV["exports"]["transform_conventions"]["camera"],
           "resolution_px": [scene.render.resolution_x, scene.render.resolution_y],
           "shutter_angle_deg": vp["shutter_angle_deg"], "shutter_position": vp["shutter_position"],
           "sub_frame_offsets_frames": OFFSETS, "intrinsics_constant": True, "frames": []}
    first = None
    for frame in frames:
        set_time(scene, frame, 0.0)
        intr = intrinsics(scene, cam)
        if first is None:
            first = intr
        elif intr != first:
            rec["intrinsics_constant"] = False
        samples = []
        for off in OFFSETS:
            set_time(scene, frame, off)
            t = ss.convert_transform_keep_local(m4(cam.matrix_world), m4(root.matrix_world))
            dec = ss.decompose(t, name=f"camera f{frame}{off:+}")
            samples.append({"offset": off, "extrinsic_matrix_4x4": dec["matrix_4x4"], "position_m": dec["position_m"], "quaternion": dec["quaternion"], "scale": dec["scale"]})
        rec["frames"].append({"frame": frame, "intrinsics": intr, "samples": samples})
    dump(out, "camera.json", rec)


def export_socket(scene, socket, root, frames, out):
    rec = {"schema_note": "socket transform per frame with sub-frame samples; ADR-0002 D1/D7, proposal §3",
           "socket": socket.name, "space": CONV["socket_space"], "convention": CONV["exports"]["transform_conventions"]["socket"],
           "sub_frame_offsets_frames": OFFSETS, "frames": []}
    for frame in frames:
        samples = []
        for off in OFFSETS:
            set_time(scene, frame, off)
            t = ss.convert_transform(m4(socket.matrix_world), m4(root.matrix_world))
            dec = ss.decompose(t, name=f"socket f{frame}{off:+}")
            samples.append({"offset": off, "matrix_4x4": dec["matrix_4x4"], "quaternion": dec["quaternion"], "position_m": dec["position_m"], "scale": dec["scale"], "pivot_m": dec["position_m"]})
        rec["frames"].append({"frame": frame, "samples": samples})
    dump(out, "socket.json", rec)
    return rec


def export_joints(scene, rig, root, frames, out):
    spine = N["bones"]["spine"]
    names = spine + [N["bones"]["shoulder_l"], N["bones"]["shoulder_r"]]
    for b in names:
        if b not in rig.pose.bones:
            raise ExportError(f"bone {b} missing on {rig.name}")
    rec = {"schema_note": "spine[] and shoulder joints per frame with sub-frame samples, socket space; ADR-0002 D3/D7",
           "rig": rig.name, "convention": CONV["exports"]["transform_conventions"]["joints"], "sub_frame_offsets_frames": OFFSETS, "frames": []}
    for frame in frames:
        row = {"frame": frame, "samples": []}
        for off in OFFSETS:
            set_time(scene, frame, off)
            s = {"offset": off, "spine": [], "shoulder_l": None, "shoulder_r": None}
            for b in names:
                pb = rig.pose.bones[b]
                t = ss.convert_transform_keep_local(m4(rig.matrix_world @ pb.matrix), m4(root.matrix_world))
                dec = ss.decompose(t, name=f"{b} f{frame}{off:+}")
                entry = {"bone": b, "matrix_4x4": dec["matrix_4x4"], "scale": dec["scale"]}
                if b in spine:
                    s["spine"].append(entry)
                else:
                    s[b] = entry
            row["samples"].append(s)
        rec["frames"].append(row)
    dump(out, "joints.json", rec)


def ring_polyline(obj, depsgraph, root):
    """Ordered SOCKET_BOUNDARY polyline of a mesh in socket space (root-relative) at the current time."""
    vg = obj.vertex_groups.get(N["vertex_group_socket_boundary"])
    if vg is None:
        raise ExportError(f"{obj.name}: no {N['vertex_group_socket_boundary']} vertex group")
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.data
    members = []
    for v in mesh.vertices:
        for g in v.groups:
            if g.group == vg.index:
                members.append((g.weight, v.index))
    if not members:
        raise ExportError(f"{obj.name}: {vg.name} is empty")
    weights = [w for w, _ in members]
    if len(set(round(w, 6) for w in weights)) != len(weights):
        raise ExportError(f"{obj.name}: {vg.name} weights are not distinct — the ring order is undefined")
    members.sort()
    mw = ev.matrix_world
    return [ss.convert_point(list(mw @ mesh.vertices[i].co), m4(root.matrix_world)) for _, i in members]


def export_socket_boundary(scene, head, body, root, frames, out):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    set_time(scene, frames[0], 0.0)
    head_ring = ring_polyline(head, depsgraph, root)
    body_ring = ring_polyline(body, depsgraph, root)
    if len(head_ring) != len(body_ring):
        raise ExportError(f"SOCKET_BOUNDARY count mismatch: head {len(head_ring)} vs body {len(body_ring)}")
    gaps = [math.dist(a, b) for a, b in zip(head_ring, body_ring)]
    # Envelope (ADR-0002 D1): the default head's REST bounding box in the socket's local frame,
    # from exactly the geometry default_head_rest.obj carries (evaluated meshes of C_HEAD ∪
    # C_HAIR) so the two agree by construction (check_exports asserts it).
    pts = head_rest_points(scene, bpy.data.objects["SOCKET_HEAD"], frames)
    envelope = {"min_m": [min(p[i] for p in pts) for i in range(3)], "max_m": [max(p[i] for p in pts) for i in range(3)],
                "status": "PROVISIONAL — placeholder head; the rigger's default head sets the real value"}
    rec = {"schema_note": "SOCKET_BOUNDARY ring on head and body, ordered polylines in socket space; proposal §3, ADR-0002 D1",
           "count": len(head_ring), "rest_frame": frames[0], "head_ring_rest": head_ring, "body_ring_rest": body_ring,
           "rest_gap_m": {"max": max(gaps), "mean": sum(gaps) / len(gaps)}, "envelope_socket_local": envelope,
           "body_ring_per_frame": []}
    for frame in frames:
        set_time(scene, frame, 0.0)
        rec["body_ring_per_frame"].append({"frame": frame, "points_m": ring_polyline(body, depsgraph, root)})
    dump(out, "socket_boundary.json", rec)


def export_lighting(scene, root, frames, out):
    lights = [o for o in bpy.data.collections["C_LIGHTS"].all_objects if o.type == "LIGHT"]
    for o in lights:
        if (o.animation_data and o.animation_data.action) or (o.data.animation_data and o.data.animation_data.action):
            raise ExportError(f"light {o.name} is animated; the lighting reference is per shot, not per frame (ADR-0002 D5 row 8)")
    set_time(scene, frames[0], 0.0)
    rows = []
    for obj in lights:
        ld = obj.data
        direction = (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
        rows.append({"name": obj.name, "type": ld.type, "power_w": ld.energy, "colour_rgb_linear": list(ld.color),
                     "size_m": getattr(ld, "size", "NOT_APPLICABLE"), "position_m": ss.convert_point(list(obj.matrix_world.translation), m4(root.matrix_world)),
                     "direction_socket_space": ss.convert_direction(list(direction), m4(root.matrix_world))})
    hdri = "NONE"
    world = scene.world
    if world and world.use_nodes:
        for node in world.node_tree.nodes:
            if node.type == "TEX_ENVIRONMENT" and node.image and node.image.filepath:
                p = Path(bpy.path.abspath(node.image.filepath))
                hdri = {"file": p.name, "sha256": sha256(p) if p.exists() else "UNKNOWN"}
    if not rows and hdri == "NONE":
        raise ExportError("no light and no HDRI — a lighting reference with nothing in it is not a reference")
    dump(out, "lighting_ref.json", {"schema_note": "lighting reference; ADR-0002 D5 row 8, sampled at the first frame, lights asserted static. The probe-ball render is produced by render_passes.py",
                                    "shot_id": scene.get("shot_id"), "sampled_at_frame": frames[0], "lights": rows, "hdri": hdri, "world_background": "NONE" if world is None else world.name})


def export_performance_track(scene, ctrl, socket_rec, frames, out, shot):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    windows = [w for w in SMAP["windows"] if w["shot_id"] == shot and "editorial" in w]
    width = lambda w: sum(b - a + 1 for a, b in w["frames"])  # noqa: E731
    windows.sort(key=width, reverse=True)  # widest first → narrowest wins on overlap
    centre = {f["frame"]: next(s for s in f["samples"] if s["offset"] == 0.0) for f in socket_rec["frames"]}
    track = {"schema_version": 1, "shot": {"master_id": CONV["master_id"], "master_version": CONV["master_version"], "shot_id": shot},
             "channel_vocabulary_version": CMAP["channel_vocabulary_version"], "fps": CONV["fps"], "frames": []}
    for frame in frames:
        set_time(scene, frame, 0.0)
        ev = ctrl.evaluated_get(depsgraph)
        channels = {}
        for ch in CMAP["channels"]:
            prop = ch["control"]["property"]
            if prop not in ev.keys():
                raise ExportError(f"FACE_CTRL has no property {prop}")
            raw = float(ev[prop])
            lo_i, hi_i = ch["input_range"]; lo_o, hi_o = ch["output_range"]
            if not math.isfinite(raw) or raw < lo_i - 1e-9 or raw > hi_i + 1e-9:
                raise ExportError(f"{ch['channel']} = {raw} outside input range {ch['input_range']} at frame {frame} — not clamped")
            channels[ch["channel"]] = round(lo_o + (raw - lo_i) * (hi_o - lo_o) / (hi_i - lo_i), 6)
        sock = centre[frame]
        row = {"frame": frame, "socket": {"position_m": sock["position_m"], "quaternion": sock["quaternion"], "scale": sock["scale"]}, "channels": channels}
        ed = {}
        for w in windows:
            if any(a <= frame <= b for a, b in w["frames"]):
                ed.update(w["editorial"])
        if ed:
            row["editorial"] = ed
        track["frames"].append(row)
    dump(out, "performance_track.json", track)


def head_rest_meshes(scene, frames):
    """(object, evaluated mesh, collection) for every renderable mesh of C_HEAD ∪ C_HAIR at the
    rest frame; a hair Curves object with points is an explicit error. Caller clears the meshes."""
    set_time(scene, frames[0], 0.0)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found = []
    for coll in ("C_HEAD", "C_HAIR"):
        for o in bpy.data.collections[coll].all_objects:
            if o.hide_render:
                continue
            if o.type == "CURVES" and len(o.data.points) > 0:
                raise ExportError(f"{o.name}: hair Curves with points cannot be re-projected as a mesh — deliver a mesh hair proxy in {coll} or exclude it by contract")
            if o.type == "CURVES":
                continue  # an empty hair Curves object (the template's placeholder) has nothing to re-project
            if o.type != "MESH":
                if o.type in GEOMETRY_TYPES:
                    # it would be in the rendered matte (export_manifest head_objects) but not in the
                    # re-projected head — an explicit error, not a silent omission (review 2026-09-17)
                    raise ExportError(f"{o.name}: render-visible {o.type} in {coll} cannot be re-projected — convert it to a mesh")
                continue
            ev = o.evaluated_get(depsgraph)
            found.append((o, ev, ev.to_mesh(), coll))
    return found


def head_rest_points(scene, socket, frames):
    """Socket-local rest points of the default head (C · socket⁻¹ · object · v)."""
    meshes = head_rest_meshes(scene, frames)  # sets the rest frame — the socket must be read AFTER it
    to_local = Matrix(ss.C) @ socket.matrix_world.inverted()
    pts = []
    for o, ev, mesh, coll in meshes:
        m = to_local @ ev.matrix_world
        pts.extend([list(m @ v.co) for v in mesh.vertices])
        ev.to_mesh_clear()
    if not pts:
        raise ExportError("default head: no renderable mesh in C_HEAD / C_HAIR")
    return pts


def export_default_head(scene, socket, frames, out):
    """The default head's geometry in the socket's LOCAL frame at the rest frame — every mesh
    object of C_HEAD and C_HAIR, evaluated, vertices as C · socket⁻¹ · object · v (root-free by
    construction: the socket transform in socket.json places it). Written by hand as a minimal
    OBJ (v / f lines only) so no axis option of any exporter can rotate it silently. This is what
    the D7 round-trip re-projects; a hair Curves object with points cannot be re-projected as a
    mesh and is an explicit error, not a silent omission."""
    meshes = head_rest_meshes(scene, frames)  # sets the rest frame first: the proxies' geometry
    # hash leaves the scene on the last frame, and a socket read before set_time exported the
    # head 44 px off (caught by check_exports' envelope check and the round-trip, 2026-09-15)
    to_local = Matrix(ss.C) @ socket.matrix_world.inverted()
    lines, objects, n_v, n_f = [], [], 0, 0
    for o, ev, mesh, coll in meshes:
        m = to_local @ ev.matrix_world
        base = n_v
        for v in mesh.vertices:
            x, y, z = m @ v.co
            lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
        n_v += len(mesh.vertices)
        # Faces in a canonical order: bmesh leaves polygon order unspecified across runs
        # (measured 2026-09-15: two rebuilds differed only in face order), and the rebuild
        # test requires the export to be byte-reproducible.
        faces = sorted(tuple(base + i + 1 for i in poly.vertices) for poly in mesh.polygons)
        lines.extend("f " + " ".join(map(str, f)) for f in faces)
        n_f += len(faces)
        objects.append({"object": o.name, "collection": coll, "vertices": len(mesh.vertices), "faces": len(faces)})
        ev.to_mesh_clear()
    if n_f == 0:
        raise ExportError("default head: no renderable mesh in C_HEAD / C_HAIR")
    (out / "default_head_rest.obj").write_text("# default head, socket-local frame (Y up, Z forward), rest frame %d\n" % frames[0] + "\n".join(lines) + "\n")
    return {"file": "default_head_rest.obj", "space": "socket-local: C · socket⁻¹ · object; identity at rest — place with socket.json matrix_4x4", "frame": frames[0],
            "objects": objects, "vertices": n_v, "faces": n_f, "hair": "mesh objects of C_HAIR only; Curves hair is not re-projectable (exporter raises if present with points)"}


def export_default_head_deformed(scene, socket, frames, out, head_rec):
    """The default head as the renderer saw it at every frame and sub-frame sample: every mesh of
    C_HEAD evaluated (shape keys, drivers from FACE_CTRL, eye rotation), in the socket's local
    frame, vertices in exactly the order of default_head_rest.obj (whose first vertices are the
    C_HEAD objects). float32 array [frames, sub-frame offsets, vertices, 3] as .npy. The D7
    round-trip re-projects THIS head, so it compares transforms and not facial deformation — the
    rest head fails a correct export on an open jaw (measured on contractor v01, frame 1100,
    2026-09-16). C_HAIR is not stored: the contract hangs the hair rigidly on the socket (TASK §4,
    no skinning, no simulation), so its socket-local vertices must equal the rest OBJ at every
    sample; a hair mesh that moves beyond the rigid tolerance is an error, not a silent use of the
    rest geometry. QC only: not a HEAD_RENDER plus file — a head technology receives the
    performance track, never the default head's deformation (identity and performance stay apart)."""
    import numpy as np
    rigid_tol = CONV["exports"]["default_head_deformed"]["rigid_tolerance_m"]
    objs = head_rec["objects"]
    head_objs = [o for o in objs if o["collection"] == "C_HEAD"]
    if objs[:len(head_objs)] != head_objs:
        raise ExportError("default head: C_HEAD objects are not the first objects of default_head_rest.obj — the deformed array could not share its vertex order")
    hair_objs = objs[len(head_objs):]
    n = sum(o["vertices"] for o in head_objs)
    arr = np.empty((len(frames), len(OFFSETS), n, 3), dtype="<f4")
    C = np.array(ss.C, dtype=np.float64)
    hair_dev = {o["object"]: 0.0 for o in hair_objs}
    obj_rest = np.array([[float(t) for t in l.split()[1:4]] for l in (out / "default_head_rest.obj").read_text().splitlines() if l.startswith("v ")], dtype=np.float64)
    hair_rest, start = {}, n
    for o in hair_objs:  # the hair's rest vertices as written to the OBJ (rest frame, centre sample)
        hair_rest[o["object"]] = obj_rest[start:start + o["vertices"]]
        start += o["vertices"]

    def local_vertices(o, depsgraph, expected):
        ev = bpy.data.objects[o].evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        try:
            if len(mesh.vertices) != expected:
                raise ExportError(f"{o}: {len(mesh.vertices)} evaluated vertices at this sample, {expected} in default_head_rest.obj — topology must not change over the shot")
            co = np.empty(expected * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", co)
        finally:
            ev.to_mesh_clear()
        m = C @ np.array(socket.matrix_world.inverted(), dtype=np.float64) @ np.array(ev.matrix_world, dtype=np.float64)
        return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]

    for fi, frame in enumerate(frames):
        for si, off in enumerate(OFFSETS):
            set_time(scene, frame, off)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            start = 0
            for o in head_objs:
                arr[fi, si, start:start + o["vertices"]] = local_vertices(o["object"], depsgraph, o["vertices"])
                start += o["vertices"]
            for o in hair_objs:
                v = local_vertices(o["object"], depsgraph, o["vertices"])
                hair_dev[o["object"]] = max(hair_dev[o["object"]], float(np.abs(v - hair_rest[o["object"]]).max()))
    if not np.isfinite(arr).all():
        raise ExportError("default_head_deformed: non-finite vertex")
    moving = {o: d for o, d in hair_dev.items() if d > rigid_tol}
    if moving:
        raise ExportError(f"C_HAIR must hang rigidly on SOCKET_HEAD (no skinning, no shape keys, no simulation): {', '.join(f'{o} moves {d:.2e} m' for o, d in sorted(moving.items()))} in socket space > {rigid_tol} m")
    np.save(out / "default_head_deformed.npy", arr, allow_pickle=False)
    # No measured floats in this record: the manifest is compared field by field across machines.
    return {"file": "default_head_deformed.npy", "dtype": "float32 little-endian", "shape": list(arr.shape),
            "axes": ["frame (the shot range in order)", "sub-frame offset (exports.sub_frame_offsets_frames)", "vertex (the first vertices of default_head_rest.obj, same order)", "xyz"],
            "space": "socket-local, as default_head_rest.obj — place with socket.json matrix_4x4 of the same sample",
            "objects": [{"object": o["object"], "vertices": o["vertices"]} for o in head_objs],
            "rigid_objects": [o["object"] for o in hair_objs], "rigid_tolerance_m": rigid_tol,
            "consumer": "QC only (D7 round-trip); not a HEAD_RENDER plus file"}


def export_proxies(scene, root, frames, out):
    prox = bpy.data.collections.get(N["proxies_collection"])
    if prox is None or not prox.objects:
        raise ExportError("C_PROXIES missing or empty")
    path = out / "proxies.abc"
    bpy.ops.wm.alembic_export(filepath=str(path), collection=prox.name, start=frames[0], end=frames[-1],
                              xsamples=len(OFFSETS), gsamples=len(OFFSETS), sh_open=OFFSETS[0], sh_close=OFFSETS[-1],
                              evaluation_mode="VIEWPORT", export_custom_properties=True, global_scale=1.0,
                              flatten=False, uvs=False, normals=True, vcolors=False, face_sets=False, triangulate=False,
                              apply_subdiv=False, curves_as_mesh=False, export_hair=False, export_particles=False,
                              use_instancing=False, packuv=False, as_background_job=False, init_scene_frame_range=False)
    if not path.exists() or path.stat().st_size == 0:
        raise ExportError("proxies.abc not written")
    # Rest-pose OBJ of the proxies (proposal §3), Blender world at the first frame.
    set_time(scene, frames[0], 0.0)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in prox.objects:
        o.select_set(True)
    # Identity axes on purpose: Blender's OBJ writer defaults (forward -Z, up +Y) apply exactly
    # the C rotation and would silently make this file socket-oriented while the ABC is not.
    bpy.ops.wm.obj_export(filepath=str(out / "proxies_rest.obj"), export_selected_objects=True, export_materials=False, export_uv=False, export_normals=True, apply_modifiers=True, forward_axis="Y", up_axis="Z")
    abc_to_socket = ss.mat_mul(ss.C, ss.mat_inv(m4(root.matrix_world)))
    # The Alembic file is not byte-reproducible by construction (its header carries the write
    # date and the source .blend path — measured 2026-09-15), so the meta file carries a hash
    # of the geometry that went into it: evaluated proxy vertices at every frame and offset,
    # rounded to 1 µm. The rebuild test compares this, not the .abc bytes.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    h = hashlib.sha256()
    for frame in frames:
        for off in OFFSETS:
            set_time(scene, frame, off)
            for o in sorted(prox.objects, key=lambda o: o.name):
                ev = o.evaluated_get(depsgraph)
                mw = ev.matrix_world
                for v in ev.data.vertices:
                    x, y, z = mw @ v.co
                    h.update(f"{o.name} {round(x, 6):.6f} {round(y, 6):.6f} {round(z, 6):.6f}\n".encode())
    proxies_geometry_sha256 = h.hexdigest()
    dump(out, "proxies.abc.meta.json", {
        "proxies_geometry_sha256": proxies_geometry_sha256,
        "proxies_geometry_sha256_rule": "sha256 over 'name x y z' of every evaluated proxy vertex (Blender world, 1e-6 m) at every frame and sub-frame offset — the reproducibility token for proxies.abc, whose bytes carry a write date and the source path",
        "collection": prox.name, "proxy_objects": [o.name for o in prox.objects],
        "note": "Alembic also carries the transform parents of the proxies (the rig and the socket root) as empty transforms",
        "frames": [frames[0], frames[-1]], "samples_per_frame": len(OFFSETS), "shutter": [OFFSETS[0], OFFSETS[-1]],
        "evaluation_mode": "VIEWPORT (proxies are hide_render; RENDER evaluation would drop them)",
        "space": "Blender world as written by Blender", "abc_to_socket_matrix_4x4": abc_to_socket,
        "abc_to_socket_rule": "apply abc_to_socket_matrix_4x4 to every point and transform to obtain socket space relative to SOCKET_SPACE_ROOT",
        "rest_obj": {"file": "proxies_rest.obj", "space": "Blender world at the first frame (exported with identity axes forward +Y, up +Z); apply abc_to_socket_matrix_4x4 exactly as for the Alembic", "frame": frames[0]},
        "alembic_version_in_blender": ".".join(str(x) for x in bpy.app.alembic.version)})


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--shot", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    scene = bpy.data.scenes["SLICE"]
    if args.shot not in CONV["shots"]:
        raise ExportError(f"unknown shot {args.shot}")
    fr = CONV["shots"][args.shot]["frame_range"]
    frames = list(range(fr["start"], fr["end"] + 1))
    if scene.get("shot_id") != args.shot:
        raise ExportError(f"scene shot_id {scene.get('shot_id')!r} is not {args.shot} — the file is another shot's scene")
    if (scene.frame_start, scene.frame_end) != (fr["start"], fr["end"]):
        raise ExportError(f"scene frame range {scene.frame_start}-{scene.frame_end} is not {args.shot}'s {fr}")
    assert_scene_conventions(scene)
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)  # never hash stale files into the manifest
    out.mkdir(parents=True)
    root = bpy.data.objects["SOCKET_SPACE_ROOT"]
    socket = bpy.data.objects["SOCKET_HEAD"]
    rig = bpy.data.objects[N["rig"]]
    ctrl = bpy.data.objects[N["face_ctrl"]]
    # Head shell rule (conventions → scene_naming.head_shell_rule): the ring lives on exactly one
    # render-visible mesh of C_HEAD; eyes, teeth, tongue, brows are further meshes there and go
    # into default_head_rest.obj, not into the ring. hide_render objects are ignored.
    heads = [o for o in bpy.data.collections["C_HEAD"].all_objects if o.type == "MESH" and not o.hide_render and N["vertex_group_socket_boundary"] in o.vertex_groups]
    bodies = [o for o in bpy.data.collections["C_BODY"].all_objects if o.type == "MESH" and not o.hide_render and N["vertex_group_socket_boundary"] in o.vertex_groups]
    if len(heads) != 1 or len(bodies) != 1:
        raise ExportError(f"expected exactly one render-visible head mesh and one body mesh carrying {N['vertex_group_socket_boundary']}; got head {[o.name for o in heads]} / body {[o.name for o in bodies]}")
    cam = scene.camera
    if cam is None or cam.name != N["camera"]:
        raise ExportError("scene camera is not CAM_001")
    export_camera(scene, cam, root, frames, out)
    socket_rec = export_socket(scene, socket, root, frames, out)
    export_joints(scene, rig, root, frames, out)
    export_socket_boundary(scene, heads[0], bodies[0], root, frames, out)
    export_lighting(scene, root, frames, out)
    export_performance_track(scene, ctrl, socket_rec, frames, out, args.shot)
    export_proxies(scene, root, frames, out)
    head_rec = export_default_head(scene, socket, frames, out)
    deformed_rec = export_default_head_deformed(scene, socket, frames, out, head_rec)
    files = sorted(f.name for f in out.iterdir() if f.name != "export_manifest.json")
    expected = set(CONV["exports"]["files"]) - {"export_manifest.json"}
    if set(files) != expected:
        raise ExportError(f"export directory {sorted(set(files) ^ expected)} differs from conventions.exports.files")
    set_time(scene, frames[0], 0.0)
    manifest = {"shot_id": args.shot, "experiment_id": CONV["experiment_id"], "master_id": CONV["master_id"], "master_version": CONV["master_version"],
                "blender": bpy.app.version_string, "channel_vocabulary_version": CMAP["channel_vocabulary_version"],
                "frames": [frames[0], frames[-1]], "sub_frame_offsets_frames": OFFSETS,
                "socket_space_root_world_matrix_4x4_blender": m4(root.matrix_world),
                "transform_conventions": CONV["exports"]["transform_conventions"], "default_head_rest": head_rec,
                "default_head_deformed": deformed_rec,
                # Object classes for the round-trip's cryptomatte reading (conventions → roundtrip.body_over_head):
                # the head's own objects (any type, C_HEAD ∪ C_HAIR), the shadow-only occluders (C_HAND_FG),
                # and the objects that hold the head out in L_HEAD (C_BODY ∪ C_ENV). Render-visible geometry only.
                "head_objects": sorted(o.name for c in ("C_HEAD", "C_HAIR") for o in bpy.data.collections[c].all_objects if o.type in GEOMETRY_TYPES and not o.hide_render),
                "occluder_objects": sorted(o.name for o in bpy.data.collections["C_HAND_FG"].all_objects if o.type in GEOMETRY_TYPES and not o.hide_render),
                "holdout_objects": sorted(o.name for c in ("C_BODY", "C_ENV") for o in bpy.data.collections[c].all_objects if o.type in GEOMETRY_TYPES and not o.hide_render),
                "files": {f: sha256(out / f) for f in files},
                # The OCIO config is identified by content; its path differs between machines and
                # rebuild directories and is not part of what the rebuild compares.
                "ocio_config_sha256": sha256(os.environ["OCIO"]) if os.environ.get("OCIO") and Path(os.environ["OCIO"]).exists() else "NOT_VERIFIED",
                "ocio_config_file": Path(os.environ["OCIO"]).name if os.environ.get("OCIO") else "NOT_VERIFIED"}  # by name and hash only: an absolute path would make the manifest machine-dependent
    dump(out, "export_manifest.json", manifest)
    print(f"EXPORT_OK {args.shot} {len(frames)} frames -> {out}")


if __name__ == "__main__":
    try:
        main()
    except (ExportError, ss.SocketExportError) as e:
        print(f"EXPORT_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
