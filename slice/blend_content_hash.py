"""Content hash of a .blend scene — what the file MEANS, not its bytes (which carry pointers,
timestamps and paths and never reproduce, like an Alembic header). Two builds of the same
scene from the same scripts give the same hash; a moved vertex, a renamed bone, a changed
weight, a different keyframe or material colour changes it. Used by the contractor acceptance
(ACCEPTANCE.md item 5) and by the package to identify archived scenes.

    blender -b <scene.blend> --python-exit-code 2 -P slice/blend_content_hash.py -- [--json <out.json>]

Prints `BLEND_CONTENT_HASH <sha256>` and, with --json, writes the per-object hashes so a
difference can be located. Vertices are canonicalised by sorting on their rounded coordinates
and faces on their remapped indices, so the hash does not depend on the order a modeller or a
script happened to create them in. Rounding: 1e-6 m for positions, 1e-4 for weights and
values. Covered: objects (type, parent, bone parent, collections, world matrix, custom
properties with their hard and soft limits, modifiers with their RNA parameters, constraints
with their RNA parameters, materials, ray visibility, hide_render), meshes (canonical
geometry, material index per face, vertex groups, shape keys, data-block properties),
armatures (bones: parent, head, tail, full local orientation 3×3, deform flags; pose-bone
constraints and IK settings), cameras, lights, empties, curves point counts, materials (node
types, every input default, Image Texture images by name, size, colour space and sha256 of the
packed data), animation (fcurves and keyframes of objects, actions and shape keys) and DRIVERS
(objects, shape keys, pose bones: path, index, type, expression, variables with their targets).
Vertex order: sorted on rounded coordinates, ties broken by the sorted coordinates of the
edge neighbours; vertices that are still indistinguishable after that are interchangeable, so
the hash cannot depend on which of them came first (contractor Q12, 2026-09-16).

The JSON also carries `mesh_data`: per-mesh entries {hash, collections, objects, materials}
where the hash covers the mesh data-block (geometry, shape keys) AND every user object's vertex
groups — skin weights are part of the accepted binding, a re-bind is a character change — but
not the object's transform, parent or pose, for the burst-2 rule that the accepted character's meshes are
untouched while the rig is animated; `collections` lets that rule select the character's
collections and ignore the environment. Hash rule version: 2026-09-16.
"""
import argparse
import hashlib
import json
import sys

import bpy

R = 6


def r(x, nd=R):
    return round(float(x), nd) + 0.0  # +0.0 folds -0.0 into 0.0


def vec(v, nd=R):
    return [r(c, nd) for c in v]


def mat(m):
    return [vec(row) for row in m]


def props(idblock):
    """Custom properties with their UI limits: a hard min/max on an animated property clamps
    the animation silently, so the limits are part of what the scene means."""
    out = {}
    for k in sorted(idblock.keys()):
        if k.startswith("_"):
            continue
        v = idblock[k]
        try:
            val = r(v, 4) if isinstance(v, (int, float)) else (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else str(v))
        except TypeError:
            val = str(v)
        limits = None
        try:
            ui = idblock.id_properties_ui(k).as_dict()
            limits = {kk: (r(ui[kk], 4) if isinstance(ui[kk], float) else ui[kk]) for kk in ("min", "max", "soft_min", "soft_max") if kk in ui}
        except (TypeError, KeyError, AttributeError):
            pass
        out[k] = {"value": val, "limits": limits}
    return out


def action_fcurves(action):
    """Blender 5 actions are layered (layers → strips → channelbags → fcurves); the legacy
    `action.fcurves` is gone. Every channelbag is read, tagged by its slot."""
    if hasattr(action, "fcurves"):
        return [(None, fc) for fc in action.fcurves]
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                slot = getattr(cb.slot, "identifier", None) if getattr(cb, "slot", None) else None
                out.extend((slot, fc) for fc in cb.fcurves)
    return out


SKIP_RNA = {"rna_type", "name", "is_override_data", "is_active", "show_expanded", "error_location", "error_rotation", "is_valid", "active", "show_in_editmode", "show_on_cage", "show_viewport", "show_render", "is_proxy_local", "persistent_uid", "execution_time", "has_error"}


def rna_props(struct):
    """Every numeric / boolean / string / enum RNA property of a struct, pointers by name —
    a generic dump for constraints, modifiers and driver variables."""
    out = {}
    for prop in struct.bl_rna.properties:
        pid = prop.identifier
        if pid in SKIP_RNA:
            continue
        try:
            v = getattr(struct, pid)
        except AttributeError:
            continue
        if prop.type == "POINTER":
            out[pid] = getattr(v, "name", None) if v is not None else None
        elif prop.type == "COLLECTION":
            continue
        elif prop.type == "FLOAT":
            out[pid] = vec(v, 4) if getattr(prop, "array_length", 0) else r(v, 4)
        elif prop.type in ("INT", "BOOLEAN"):
            out[pid] = [int(x) for x in v] if getattr(prop, "array_length", 0) else (int(v) if isinstance(v, (bool, int)) else v)
        elif prop.type == "ENUM":
            out[pid] = sorted(v) if isinstance(v, set) else v
        elif prop.type == "STRING":
            out[pid] = v
    return out


def drivers(anim):
    if anim is None:
        return None
    out = []
    for fc in anim.drivers:
        d = fc.driver
        variables = []
        for var in d.variables:
            variables.append({"name": var.name, "type": var.type,
                              "targets": [{"id": getattr(t.id, "name", None) if t.id else None, "id_type": t.id_type, "data_path": t.data_path,
                                           "bone_target": t.bone_target, "transform_type": t.transform_type, "transform_space": t.transform_space,
                                           "rotation_mode": t.rotation_mode} for t in var.targets]})
        out.append({"path": fc.data_path, "index": fc.array_index, "type": d.type, "expression": d.expression, "use_self": d.use_self,
                    "variables": sorted(variables, key=lambda v: v["name"]), "keys": [[r(k.co[0], 4), r(k.co[1], 4)] for k in fc.keyframe_points]})
    return sorted(out, key=lambda c: (c["path"], c["index"])) or None


def image_content(img):
    if img is None:
        return None
    d = {"name": img.name, "size": list(img.size), "colorspace": img.colorspace_settings.name, "source": img.source, "channels": img.channels}
    if img.packed_file is not None:
        d["sha256"] = hashlib.sha256(img.packed_file.data).hexdigest()
        d["packed"] = True
    else:
        d["packed"] = False
        path = bpy.path.abspath(img.filepath) if img.filepath else ""
        try:
            with open(path, "rb") as f:
                d["sha256"] = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            d["sha256"] = "UNPACKED_FILE_MISSING"
        d["file"] = bpy.path.basename(img.filepath)
    return d


def fcurves(anim):
    if anim is None or anim.action is None:
        return None
    curves = []
    for slot, fc in action_fcurves(anim.action):
        curves.append({"slot": slot, "path": fc.data_path, "index": fc.array_index, "keys": [[r(k.co[0], 4), r(k.co[1], 4), k.interpolation] for k in fc.keyframe_points]})
    return sorted(curves, key=lambda c: (str(c["slot"]), c["path"], c["index"]))


def mesh_content(obj):
    me = obj.data
    verts = [vec(v.co) for v in me.vertices]
    neighbours = [[] for _ in verts]
    for e in me.edges:
        a, b = e.vertices
        neighbours[a].append(verts[b])
        neighbours[b].append(verts[a])
    keys = [(verts[i], sorted(neighbours[i])) for i in range(len(verts))]
    order = sorted(range(len(verts)), key=lambda i: keys[i])
    remap = {old: new for new, old in enumerate(order)}
    faces = sorted((tuple(sorted(remap[i] for i in p.vertices)), p.material_index) for p in me.polygons)
    groups = {}
    for g in obj.vertex_groups:
        weights = []
        for v in me.vertices:
            for ge in v.groups:
                if ge.group == g.index:
                    weights.append([remap[v.index], r(ge.weight, 4)])
        groups[g.name] = sorted(weights)
    shape_keys = None
    if me.shape_keys:
        shape_keys = {kb.name: sorted(vec(kb.data[i].co) for i in range(len(kb.data))) for kb in me.shape_keys.key_blocks}
    return {"vertices": [verts[i] for i in order], "faces": faces, "materials": [m.name if m else None for m in me.materials],
            "vertex_groups": groups, "shape_keys": shape_keys, "shape_key_anim": fcurves(me.shape_keys.animation_data) if me.shape_keys else None,
            "shape_key_drivers": drivers(me.shape_keys.animation_data) if me.shape_keys else None, "data_props": props(me)}


def armature_content(obj):
    bones = {}
    for b in obj.data.bones:
        bones[b.name] = {"parent": b.parent.name if b.parent else None, "head": vec(b.head_local), "tail": vec(b.tail_local),
                         "orientation": [vec(row) for row in b.matrix_local.to_3x3()], "use_deform": b.use_deform, "use_connect": b.use_connect,
                         "inherit_rotation": b.use_inherit_rotation, "inherit_scale": b.inherit_scale}
    pose = {}
    for pb in obj.pose.bones:
        pose[pb.name] = {"constraints": [{"type": c.type, "name": c.name, **rna_props(c)} for c in pb.constraints],
                         "ik": {"lock": [pb.lock_ik_x, pb.lock_ik_y, pb.lock_ik_z], "stiffness": vec([pb.ik_stiffness_x, pb.ik_stiffness_y, pb.ik_stiffness_z], 4),
                                "limits": [pb.use_ik_limit_x, pb.use_ik_limit_y, pb.use_ik_limit_z], "stretch": r(pb.ik_stretch, 4)},
                         "rotation_mode": pb.rotation_mode, "props": props(pb)}
    return {"bones": bones, "pose": pose, "data_props": props(obj.data)}


def material_content(m):
    nodes = []
    if m.node_tree:
        for n in m.node_tree.nodes:
            inputs = {}
            for i in n.inputs:
                if hasattr(i, "default_value"):
                    dv = i.default_value
                    try:
                        inputs[i.name] = vec(dv, 4) if hasattr(dv, "__len__") else r(dv, 4)
                    except TypeError:
                        inputs[i.name] = str(dv)
            node = {"type": n.bl_idname, "name": n.name, "inputs": inputs}
            if n.bl_idname == "ShaderNodeTexImage":
                node["image"] = image_content(n.image)
                node["interpolation"], node["projection"], node["extension"] = n.interpolation, n.projection, n.extension
            nodes.append(node)
        nodes.sort(key=lambda n: (n["type"], n["name"]))
    return {"nodes": nodes, "blend_method": getattr(m, "blend_method", None)}


def object_content(obj):
    d = {"type": obj.type, "parent": obj.parent.name if obj.parent else None, "parent_type": obj.parent_type,
         "parent_bone": obj.parent_bone, "collections": sorted(c.name for c in obj.users_collection),
         "matrix_world": mat(obj.matrix_world), "hide_render": obj.hide_render,
         "ray_visibility": [obj.visible_camera, obj.visible_shadow, obj.visible_diffuse, obj.visible_glossy, obj.visible_transmission, obj.visible_volume_scatter],
         "modifiers": [{"type": m.type, "name": m.name, **rna_props(m)} for m in obj.modifiers],
         "constraints": [{"type": c.type, "name": c.name, **rna_props(c)} for c in obj.constraints],
         "props": props(obj), "anim": fcurves(obj.animation_data), "drivers": drivers(obj.animation_data)}
    if obj.type == "MESH":
        d["mesh"] = mesh_content(obj)
    elif obj.type == "ARMATURE":
        d["armature"] = armature_content(obj)
        d["pose_anim"] = fcurves(obj.animation_data)
    elif obj.type == "CAMERA":
        c = obj.data
        d["camera"] = {"lens": r(c.lens, 4), "sensor": [r(c.sensor_width, 4), r(c.sensor_height, 4)], "fit": c.sensor_fit, "shift": [r(c.shift_x, 4), r(c.shift_y, 4)],
                       "clip": [r(c.clip_start, 4), r(c.clip_end, 4)], "dof": [c.dof.use_dof, r(c.dof.focus_distance, 4), r(c.dof.aperture_fstop, 4)]}
    elif obj.type == "LIGHT":
        L = obj.data
        d["light"] = {"type": L.type, "energy": r(L.energy, 4), "color": vec(L.color, 4), "size": r(getattr(L, "size", 0.0), 4)}
    elif obj.type == "EMPTY":
        d["empty"] = {"display": obj.empty_display_type, "size": r(obj.empty_display_size, 4)}
    elif obj.type == "CURVES":
        d["curves"] = {"points": len(obj.data.points), "curves": len(obj.data.curves)}
    return d


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--json", default="")
    args = p.parse_args(argv)
    scene = bpy.data.scenes.get("SLICE") or bpy.context.scene
    scene.frame_set(scene.frame_start)
    report = {"scene": {"name": scene.name, "frame_range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps, "props": props(scene)},
              "objects": {}, "materials": {}, "mesh_data": {}}
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        content = object_content(obj)
        report["objects"][obj.name] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    for m in sorted(bpy.data.materials, key=lambda m: m.name):
        report["materials"][m.name] = hashlib.sha256(json.dumps(material_content(m), sort_keys=True).encode()).hexdigest()
    # Data-block hashes of meshes, independent of the object's transform, parent and pose: burst 2
    # animates the character, which changes every object hash below SOCKET_HEAD and the rig, while
    # the meshes and materials must be the accepted burst-1 ones (contractor/burst-2/ACCEPTANCE.md).
    users = {}
    for obj in sorted((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: (o.data.name, o.name)):
        users.setdefault(obj.data.name, []).append(obj)
    for name, objs in users.items():
        # One entry per data-block; the hash folds mesh_content of EVERY user, so a re-bind of any
        # user (vertex groups live on the object) changes it.
        content = [mesh_content(o) for o in objs]
        report["mesh_data"][name] = {"hash": hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest(),
                                     "collections": sorted({c.name for o in objs for c in o.users_collection}), "objects": [o.name for o in objs],
                                     "materials": sorted({sl.material.name for o in objs for sl in o.material_slots if sl.material})}
    total = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    report["content_hash"] = total
    report["rule"] = "sha256 over the canonical JSON of scene settings, per-object content hashes, per-material hashes and per-mesh data-block hashes (mesh_data, added 2026-09-16 — hashes recorded before that date are of the previous rule and do not reproduce); see the module docstring for what is covered and the rounding"
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    print(f"BLEND_CONTENT_HASH {total} objects={len(report['objects'])} materials={len(report['materials'])}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(argv)
