"""truth_subject_01.py — burst 3: the ground-truth turntable of a synthetic child (TASK §3.5).

    blender -b subject_01_character.blend --python-exit-code 2 -P truth_subject_01.py -- --out truth_subject_01.blend

Head and shoulders in the MASTER look (the character file's own materials), SHOT_001's light (its KEY_001 and
FILL_001, same type, size, energy, colour and placement as make_shot_001.py), a neutral face and a rest pose.
One camera per view, and the same views bound to frames 1..9 through timeline markers, so one animation
render gives every view. Camera azimuth around the head: 0 = straight in front (−Y); + puts the camera on +X.
Deterministic; no randomness."""
import argparse, math, sys
import bpy
from mathutils import Vector

VIEWS = [("Y+000_P+00", 0, 0), ("Y+030_P+00", 30, 0), ("Y-030_P+00", -30, 0), ("Y+060_P+00", 60, 0),
         ("Y-060_P+00", -60, 0), ("Y+090_P+00", 90, 0), ("Y-090_P+00", -90, 0), ("Y+000_P+20", 0, 20),
         ("Y+000_P-20", 0, -20)]
DIST_M = 1.05
LENS_MM = 70.0

def aim(o, t):
    o.rotation_mode = "XYZ"; o.rotation_euler = (t - o.location).to_track_quat("-Z", "Y").to_euler()

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args(argv)
    sc = bpy.data.scenes["SLICE"]
    rig = bpy.data.objects["RIG_HERO"]; ctrl = bpy.data.objects["FACE_CTRL"]
    rig.animation_data_clear(); ctrl.animation_data_clear()               # rest pose, neutral face
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0); pb.rotation_euler = (0, 0, 0)
    for k in list(ctrl.keys()):
        if isinstance(ctrl[k], float):
            ctrl[k] = 0.0
    bpy.context.view_layer.update()
    eyes = (bpy.data.objects["HERO_EYE_L"].matrix_world.translation + bpy.data.objects["HERO_EYE_R"].matrix_world.translation) / 2
    target = eyes + Vector((0.0, 0.02, -0.03))                             # between the eyes, a touch toward the head centre
    lights = bpy.data.collections["C_LIGHTS"]
    key = bpy.data.objects["KEY_001"]; key.animation_data_clear()        # SHOT_001's KEY_001 and FILL_001
    key.data.type = "AREA"; key.data.shape = "DISK"; key.data.size = 1.2; key.data.energy = 120.0; key.data.color = (1, 1, 1)
    key.location = (0.85, -1.05, 1.95); aim(key, Vector((0, -0.05, 1.30)))
    fd = bpy.data.lights.get("FILL_001") or bpy.data.lights.new("FILL_001", "AREA")
    fd.shape = "DISK"; fd.size = 1.6; fd.energy = 45.0; fd.color = (1, 1, 1)
    fill = bpy.data.objects.get("FILL_001") or bpy.data.objects.new("FILL_001", fd)
    if fill.name not in lights.objects: lights.objects.link(fill)
    fill.location = (-1.1, -0.85, 1.45); aim(fill, Vector((0, -0.05, 1.30)))
    base_cam = bpy.data.objects["CAM_001"]; base_cam.animation_data_clear(); base_cam.parent = None
    sc.timeline_markers.clear()
    sc.frame_start, sc.frame_end = 1, len(VIEWS)
    for n, (name, az, el) in enumerate(VIEWS, start=1):
        cd = bpy.data.cameras.new(f"TRUTH_{name}"); cd.lens = LENS_MM
        cam = bpy.data.objects.new(f"TRUTH_{name}", cd); sc.collection.objects.link(cam)
        a_, e_ = math.radians(az), math.radians(el)
        cam.location = target + Vector((DIST_M * math.cos(e_) * math.sin(a_), -DIST_M * math.cos(e_) * math.cos(a_), DIST_M * math.sin(e_)))
        aim(cam, target)
        m = sc.timeline_markers.new(name, frame=n); m.camera = cam
    sc.camera = bpy.data.objects[f"TRUTH_{VIEWS[0][0]}"]
    sc["truth_views"] = ",".join(v[0] for v in VIEWS)
    sc.render.filepath = "//renders/truth_subject_01/"
    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    print(f"TRUTH_OK {a.out} views={len(VIEWS)} (frames 1-{len(VIEWS)}), target {[round(c, 3) for c in target]}, distance {DIST_M} m, lens {LENS_MM} mm")

if __name__ == "__main__":
    main()
