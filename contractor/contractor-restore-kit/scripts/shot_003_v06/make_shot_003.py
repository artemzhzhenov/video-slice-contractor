"""make_shot_003.py — burst 2: SHOT_003 file from the accepted character_v04.1 (TASK §2).

    blender -b character_v04_1_SHOT_003.blend --python-exit-code 2 -P make_shot_003.py -- --out SHOT_003_v01.blend

Only shot-owned things: a neutral three-quarter key with a soft fill (static), environment, and the
camera — framed waist up (owner, Q38), drifting slowly and pulling back a little as the girl turns
away. Deterministic; no randomness."""
import argparse, math, sys
import bpy
from mathutils import Vector

LENS_MM = 62.0                                   # waist-up framing at ~1.6 m
AIM = Vector((0.0, -0.05, 1.19))                 # chest/head centre for a waist-up frame
# Three-quarter for the whole shot (TASK §6 rule 4, now in state_requirements v2): the camera sits to
# the side so the head reads 35–55° to it in sadness, fear and the hand window, with the character
# standing freely — turning the body 40° would make the pose mannered. The fast turn then starts from
# three-quarter, which reads better than from frontal.
CAM_PATH = [(1241, -43.0, 1.58, 1.24), (1290, -44.5, 1.60, 1.235),
            (1332, -46.0, 1.63, 1.23), (1360, -48.0, 1.68, 1.225)]   # (frame, azimuth°, radius m, height m)
KEY_COLOUR = (1.00, 0.94, 0.86)                  # neutral daylight, ratio 1.16
KEY_ENERGY = 150.0
KEY_SIZE_M = 0.9                                 # soft: no hard shadow edge, this shot is about acting
KEY_POS = Vector((0.95, -1.25, 2.00))
FILL_COLOUR = (0.80, 0.86, 1.00)
FILL_ENERGY = 45.0
FILL_POS = Vector((-1.05, -1.10, 1.35))
ENV_GREY = (0.40, 0.41, 0.44)
MIRROR_POINT = (0.0, 0.0)                        # the camera path's own symmetry plane x = 0 (AIM.x = 0);
                                                 # the owner's plane (−0.003,−0.020)/(0.994,−0.109) sits 6° off it and
                                                 # turns the −45° camera into +33°, which drops the ¾ angles to 25–35°
MIRROR_NORMAL = (1.0, 0.0)          # see above; Q44 states (0.875, 0.485), but the camera pair given there (−1.143,−1.186)→(0.865,−1.406)
                                   # reflects through THIS normal (perpendicular to the character's facing); the point is on both

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
    if sc.get("shot_id") != "SHOT_003" or (sc.frame_start, sc.frame_end) != (1241, 1360):
        fail(f"expected SHOT_003 1241-1360, got {sc.get('shot_id')} {sc.frame_start}-{sc.frame_end}")
    sc.render.filepath = "//renders/SHOT_003/"
    env, lights = bpy.data.collections["C_ENV"], bpy.data.collections["C_LIGHTS"]

    cam = bpy.data.objects["CAM_001"]
    cam.animation_data_clear(); cam.parent = None
    cam.data.lens = LENS_MM
    # Mirrored to the character's LEFT side (owner, Q44): the left arm cannot reach the right eye with the
    # elbow out, so the camera reflects through the character's median plane at frame 1241 — point
    # (−0.003, −0.020), normal (0.875, 0.485, 0) — height, tilt and target unchanged. The three-quarter
    # angles keep their magnitude; on screen everything looks the other way.
    MP, MN = Vector((MIRROR_POINT[0], MIRROR_POINT[1], 0.0)), Vector((MIRROR_NORMAL[0], MIRROR_NORMAL[1], 0.0)).normalized()
    def mirror_xy(p):
        d = (Vector((p.x, p.y, 0.0)) - MP).dot(MN)
        return Vector((p.x - 2 * d * MN.x, p.y - 2 * d * MN.y, p.z))
    for f, az, rad, z in CAM_PATH:
        a = math.radians(az)
        cam.location = mirror_xy(Vector((AIM.x + rad * math.sin(a), AIM.y - rad * math.cos(a), z)))
        aim(cam, mirror_xy(AIM))
        cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)

    key = bpy.data.objects.get("KEY_001") or fail("KEY_001 missing")
    key.animation_data_clear()
    key.data.type = "AREA"; key.data.shape = "DISK"; key.data.size = KEY_SIZE_M
    key.data.energy = KEY_ENERGY; key.data.color = KEY_COLOUR
    key.location = mirror_xy(KEY_POS); aim(key, mirror_xy(Vector((0.0, -0.05, 1.28))))
    fd = bpy.data.lights.get("FILL_003") or bpy.data.lights.new("FILL_003", "AREA")
    fd.shape = "DISK"; fd.size = 1.6; fd.energy = FILL_ENERGY; fd.color = FILL_COLOUR
    fill = bpy.data.objects.get("FILL_003") or bpy.data.objects.new("FILL_003", fd)
    if fill.name not in lights.objects: link(fill, lights)
    fill.location = mirror_xy(FILL_POS); aim(fill, mirror_xy(Vector((0.0, -0.05, 1.22))))
    for o in (key, fill):
        o.animation_data_clear()

    # The camera sits at ~45° in three-quarter, so a back wall alone ends inside the frame (a black band on
    # the right of the early checkpoint frames): the wall is wide and a side wall closes the corner.
    for name, verts in (("ENV_FLOOR", [(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)]),
                        ("ENV_WALL", [(-6, 1.2, 0), (6, 1.2, 0), (6, 1.2, 3.2), (-6, 1.2, 3.2)]),
                        ("ENV_WALL_SIDE", [(1.9, -6, 0), (1.9, 1.2, 0), (1.9, 1.2, 3.2), (1.9, -6, 3.2)])):
        if bpy.data.objects.get(name): continue
        mv = [mirror_xy(Vector(v))[:] for v in verts]          # walls reflected through the same plane (Q44.1)
        me = bpy.data.meshes.new(name); me.from_pydata(mv, [], [[0, 1, 2, 3]]); me.update()
        o = bpy.data.objects.new(name, me); me.materials.append(mat("ENV_GREY", ENV_GREY)); link(o, env)

    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=args.out, compress=True)
    sc.frame_set(1318); print("CAM_1318", [round(c, 3) for c in cam.matrix_world.translation])
    print(f"SHOT_OK {args.out} lens={LENS_MM} key_ratio={max(KEY_COLOUR)/min(KEY_COLOUR):.2f} lights={[o.name for o in lights.objects]}")

if __name__ == "__main__":
    main()
