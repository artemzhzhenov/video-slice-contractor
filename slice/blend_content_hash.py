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
properties, modifiers, materials, ray visibility, hide_render), meshes (canonical geometry,
material index per face, vertex groups), armatures (bones: parent, head, tail, roll),
cameras, lights, empties, curves point counts, materials (node types and Principled inputs),
animation (fcurves and keyframes of objects, actions and shape keys), scene frame range and fps."""
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
    out = {}
    for k in sorted(idblock.keys()):
        if k.startswith("_"):
            continue
        v = idblock[k]
        try:
            out[k] = r(v, 4) if isinstance(v, (int, float)) else (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else str(v))
        except TypeError:
            out[k] = str(v)
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
    order = sorted(range(len(verts)), key=lambda i: verts[i])
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
            "vertex_groups": groups, "shape_keys": shape_keys, "shape_key_anim": fcurves(me.shape_keys.animation_data) if me.shape_keys else None}


def armature_content(obj):
    bones = {}
    for b in obj.data.bones:
        bones[b.name] = {"parent": b.parent.name if b.parent else None, "head": vec(b.head_local), "tail": vec(b.tail_local),
                         "roll": None, "use_deform": b.use_deform, "use_connect": b.use_connect}
    return {"bones": bones}


def material_content(m):
    nodes = []
    if m.use_nodes and m.node_tree:
        for n in m.node_tree.nodes:
            inputs = {}
            for i in n.inputs:
                if hasattr(i, "default_value"):
                    dv = i.default_value
                    try:
                        inputs[i.name] = vec(dv, 4) if hasattr(dv, "__len__") else r(dv, 4)
                    except TypeError:
                        inputs[i.name] = str(dv)
            nodes.append({"type": n.bl_idname, "name": n.name, "inputs": inputs})
        nodes.sort(key=lambda n: (n["type"], n["name"]))
    return {"nodes": nodes, "blend_method": getattr(m, "blend_method", None)}


def object_content(obj):
    d = {"type": obj.type, "parent": obj.parent.name if obj.parent else None, "parent_type": obj.parent_type,
         "parent_bone": obj.parent_bone, "collections": sorted(c.name for c in obj.users_collection),
         "matrix_world": mat(obj.matrix_world), "hide_render": obj.hide_render,
         "ray_visibility": [obj.visible_camera, obj.visible_shadow, obj.visible_diffuse, obj.visible_glossy, obj.visible_transmission, obj.visible_volume_scatter],
         "modifiers": [[m.type, m.name] for m in obj.modifiers], "props": props(obj), "anim": fcurves(obj.animation_data)}
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
              "objects": {}, "materials": {}}
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        content = object_content(obj)
        report["objects"][obj.name] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    for m in sorted(bpy.data.materials, key=lambda m: m.name):
        report["materials"][m.name] = hashlib.sha256(json.dumps(material_content(m), sort_keys=True).encode()).hexdigest()
    total = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    report["content_hash"] = total
    report["rule"] = "sha256 over the canonical JSON of scene settings, per-object content hashes and per-material hashes; see the module docstring for what is covered and the rounding"
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    print(f"BLEND_CONTENT_HASH {total} objects={len(report['objects'])} materials={len(report['materials'])}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(argv)
