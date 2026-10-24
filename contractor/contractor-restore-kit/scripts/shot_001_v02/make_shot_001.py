"""make_shot_001.py — burst 2: SHOT_001 file from the accepted character_v03 (TASK §2, recommended path).

    blender -b character_v03.blend --python-exit-code 2 -P make_shot_001.py -- --out SHOT_001_v01.blend

Changes only what belongs to the shot: camera (close-up, constant focal length, slow drift over the
whole shot), lights (soft white key + fill, static), environment and PROP_A in C_ENV. Character
meshes, materials, rig structure, ring and proxies are untouched. Deterministic, no randomness."""
import argparse, math, sys
import bpy
from mathutils import Vector

LENS_MM = 85.0
CAM_TARGET = Vector((0.0, -0.05, 1.285))          # between the eyes, v03 head
CAM_PATH = [(1001, Vector((0.030, -1.34, 1.300))), # (frame, position): a slow push-in and drift,
            (1060, Vector((0.000, -1.31, 1.292))), # ~4 cm over 120 frames — visible sub-frames,
            (1120, Vector((-0.025, -1.29, 1.288)))]# never a hold (TASK §3); head + top of shoulders
PROP_A_POS = Vector((0.15, -0.34, 1.225))        # ball fully in frame on every frame (owner, 21.09), clear of the head, ~27° from the eye
PROP_A_RADIUS = 0.028
ENV_GREY = (0.46, 0.47, 0.50)

def fail(m):
    print(f"SHOT_ERROR {m}"); sys.exit(2)

def mat(name, rgb, rough=0.6):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1.0); p.inputs["Roughness"].default_value = rough
    return m

def link(obj, coll):
    for c in list(obj.users_collection): c.objects.unlink(obj)
    coll.objects.link(obj)

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); args = ap.parse_args(argv)
    sc = bpy.data.scenes.get("SLICE") or fail("scene SLICE missing")
    if sc.get("shot_id") != "SHOT_001" or (sc.frame_start, sc.frame_end) != (1001, 1120):
        fail(f"expected SHOT_001 1001-1120, got {sc.get('shot_id')} {sc.frame_start}-{sc.frame_end}")
    sc.render.filepath = "//renders/SHOT_001/"
    env, lights = bpy.data.collections["C_ENV"], bpy.data.collections["C_LIGHTS"]

    # camera: constant focal length, keyed transform, Bezier, drift on every frame
    cam = bpy.data.objects["CAM_001"]
    cam.animation_data_clear(); cam.parent = None
    cam.data.lens = LENS_MM
    for f, pos in CAM_PATH:
        cam.location = pos
        cam.rotation_mode = "XYZ"
        cam.rotation_euler = (CAM_TARGET - pos).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)
    for fc in cam.animation_data.action.layers[0].strips[0].channelbag(cam.animation_data.action.slots[0]).fcurves if hasattr(cam.animation_data.action, "layers") and cam.animation_data.action.layers else []:
        for k in fc.keyframe_points: k.interpolation = "BEZIER"

    # lights: soft white key from the front-left above, weaker fill from the right — static
    key = bpy.data.objects.get("KEY_001")
    if key is None or key.type != "LIGHT": fail("KEY_001 missing")
    key.animation_data_clear()
    key.data.type = "AREA"; key.data.shape = "DISK"; key.data.size = 1.2
    key.data.energy = 120.0; key.data.color = (1.0, 1.0, 1.0)
    key.location = (0.85, -1.05, 1.95)
    key.rotation_euler = (Vector((0, -0.05, 1.30)) - key.location).to_track_quat("-Z", "Y").to_euler()
    fill_d = bpy.data.lights.get("FILL_001") or bpy.data.lights.new("FILL_001", "AREA")
    fill_d.shape = "DISK"; fill_d.size = 1.6; fill_d.energy = 45.0; fill_d.color = (1.0, 1.0, 1.0)
    fill = bpy.data.objects.get("FILL_001") or bpy.data.objects.new("FILL_001", fill_d)
    if fill.name not in lights.objects: link(fill, lights)
    fill.location = (-1.1, -0.85, 1.45)
    fill.rotation_euler = (Vector((0, -0.05, 1.30)) - fill.location).to_track_quat("-Z", "Y").to_euler()

    # environment: floor and a back wall, neutral grey — simple, in C_ENV
    for name, verts in (("ENV_FLOOR", [(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)]),
                        ("ENV_WALL", [(-2, 0.9, 0), (2, 0.9, 0), (2, 0.9, 2.6), (-2, 0.9, 2.6)])):
        if bpy.data.objects.get(name): continue
        me = bpy.data.meshes.new(name); me.from_pydata(verts, [], [[0, 1, 2, 3]]); me.update()
        o = bpy.data.objects.new(name, me); me.materials.append(mat("ENV_GREY", ENV_GREY, 0.9)); link(o, env)

    # PROP_A: a small toy — a ball on a short peg, the gaze target of the gaze_shift window
    if not bpy.data.objects.get("PROP_A"):
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=PROP_A_RADIUS)
        peg = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.008, radius2=0.008, depth=0.12)
        for v in peg["verts"]: v.co.z -= PROP_A_RADIUS + 0.06
        me = bpy.data.meshes.new("PROP_A"); bm.to_mesh(me); bm.free()
        o = bpy.data.objects.new("PROP_A", me); me.materials.append(mat("PROP_A_RED", (0.75, 0.10, 0.08), 0.35))
        for p in me.polygons: p.use_smooth = True
        o.location = PROP_A_POS; link(o, env)

    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=args.out, compress=True)
    print(f"SHOT_OK {args.out} lens={LENS_MM} env={[o.name for o in env.objects]} lights={[o.name for o in lights.objects]}")

if __name__ == "__main__":
    main()
