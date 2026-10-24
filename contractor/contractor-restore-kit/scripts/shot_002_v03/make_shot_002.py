"""make_shot_002.py — burst 2: SHOT_002 file from the accepted character (TASK §2).

    blender -b character_SHOT_002_base.blend --python-exit-code 2 -P make_shot_002.py -- --out SHOT_002_v01.blend

The character comes from build_character.py run on a SHOT_002 template, so its meshes and materials
are hash-identical to the accepted v03. This script only adds what belongs to the shot: a hard
coloured key light (static, C_LIGHTS), environment and the camera, which slowly orbits from the
three-quarter side to the profile side. Deterministic; no randomness."""
import argparse, math, sys
import bpy
from mathutils import Vector

LENS_MM = 85.0
HEAD_AIM = Vector((0.0, -0.05, 1.285))                # between the eyes of the v03 head
CAM_RADIUS_M = 1.30
# (frame, camera azimuth in degrees around the head: 0 = straight in front (−Y), + = toward the
# character's left; height in metres). The camera keeps drifting on every frame (TASK §3).
CAM_PATH = [(1121, -24.0, 1.300), (1152, -25.5, 1.296), (1176, -27.0, 1.292), (1240, -29.0, 1.286)]
KEY_COLOUR = (1.00, 0.52, 0.22)                       # hard warm key, max/min = 4.5 ≥ 1.5 (strong_light)
KEY_ENERGY = 320.0
KEY_SIZE_M = 0.10                                     # small source → hard shadow of the head on the neck
# The key sits well to the side of the head's facing direction and high, so its shadow edge crosses the
# FACE: in three-quarter about half the face is lit, in profile the nose and brow throw shadows onto the
# cheek (Q30.1). Small source (10 cm) keeps those edges hard.
KEY_POS = Vector((1.22, -0.58, 2.00))
KEY_AIM = Vector((0.02, -0.07, 1.30))
RIM_COLOUR = (0.22, 0.42, 1.00)                       # cold rim from behind the other side
RIM_ENERGY = 85.0
RIM_POS = Vector((-1.20, 0.60, 1.62))                 # cold rim from behind the other side
FILL_COLOUR = (0.35, 0.50, 1.00)                      # dim cold fill: keeps the shadow side readable
FILL_ENERGY = 40.0                                    # without softening the key's shadow edge
FILL_POS = Vector((-0.95, -1.05, 1.35))
ENV_GREY = (0.34, 0.35, 0.40)

def fail(m):
    print(f"SHOT_ERROR {m}"); sys.exit(2)

def mat(name, rgb, rough=0.9):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*rgb, 1.0); p.inputs["Roughness"].default_value = rough
    return m

def link(obj, coll):
    for c in list(obj.users_collection): c.objects.unlink(obj)
    coll.objects.link(obj)

def aim(obj, target):
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); args = ap.parse_args(argv)
    sc = bpy.data.scenes.get("SLICE") or fail("scene SLICE missing")
    if sc.get("shot_id") != "SHOT_002" or (sc.frame_start, sc.frame_end) != (1121, 1240):
        fail(f"expected SHOT_002 1121-1240, got {sc.get('shot_id')} {sc.frame_start}-{sc.frame_end}")
    sc.render.filepath = "//renders/SHOT_002/"
    env, lights = bpy.data.collections["C_ENV"], bpy.data.collections["C_LIGHTS"]

    cam = bpy.data.objects["CAM_001"]
    cam.animation_data_clear(); cam.parent = None
    cam.data.lens = LENS_MM
    for f, az, z in CAM_PATH:
        a = math.radians(az)
        cam.location = Vector((HEAD_AIM.x + CAM_RADIUS_M * math.sin(a), HEAD_AIM.y - CAM_RADIUS_M * math.cos(a), z))
        aim(cam, HEAD_AIM)
        cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)

    key = bpy.data.objects.get("KEY_001") or fail("KEY_001 missing")
    key.animation_data_clear()
    key.data.type = "AREA"; key.data.shape = "DISK"; key.data.size = KEY_SIZE_M
    key.data.energy = KEY_ENERGY; key.data.color = KEY_COLOUR
    key.location = KEY_POS; aim(key, KEY_AIM)
    rim_d = bpy.data.lights.get("RIM_001") or bpy.data.lights.new("RIM_001", "AREA")
    rim_d.shape = "DISK"; rim_d.size = 0.5; rim_d.energy = RIM_ENERGY; rim_d.color = RIM_COLOUR
    rim = bpy.data.objects.get("RIM_001") or bpy.data.objects.new("RIM_001", rim_d)
    if rim.name not in lights.objects: link(rim, lights)
    rim.location = RIM_POS; aim(rim, Vector((0.0, -0.05, 1.28)))
    fill_d = bpy.data.lights.get("FILL_002") or bpy.data.lights.new("FILL_002", "AREA")
    fill_d.shape = "DISK"; fill_d.size = 1.4; fill_d.energy = FILL_ENERGY; fill_d.color = FILL_COLOUR
    fill = bpy.data.objects.get("FILL_002") or bpy.data.objects.new("FILL_002", fill_d)
    if fill.name not in lights.objects: link(fill, lights)
    fill.location = FILL_POS; aim(fill, Vector((0.0, -0.05, 1.30)))
    for o in (key, rim, fill):                             # lights are static in the shot (TASK §3)
        o.animation_data_clear()

    for name, verts in (("ENV_FLOOR", [(-2.5, -2.5, 0), (2.5, -2.5, 0), (2.5, 2.5, 0), (-2.5, 2.5, 0)]),
                        ("ENV_WALL", [(-2.5, 1.1, 0), (2.5, 1.1, 0), (2.5, 1.1, 2.6), (-2.5, 1.1, 2.6)])):
        if bpy.data.objects.get(name): continue
        me = bpy.data.meshes.new(name); me.from_pydata(verts, [], [[0, 1, 2, 3]]); me.update()
        o = bpy.data.objects.new(name, me); me.materials.append(mat("ENV_GREY", ENV_GREY)); link(o, env)

    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=args.out, compress=True)
    ratio = max(KEY_COLOUR) / min(KEY_COLOUR)
    print(f"SHOT_OK {args.out} lens={LENS_MM} key_colour_ratio={ratio:.2f} lights={[o.name for o in lights.objects]} env={[o.name for o in env.objects]}")

if __name__ == "__main__":
    main()
