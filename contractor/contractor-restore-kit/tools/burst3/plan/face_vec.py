"""Basis extractor (contractor, burst 3, 2026-10-24): HERO_HEAD vertices with every FACE_CTRL channel at 0 at the first
frame, in the socket's contract frame — the same way as the owner's slice/measurements/face_shape_distance.py head() —
saved as .npy (float64, n×3, metres) with the normals; plus face_width and interocular as face_measure.py.
    blender -b file.blend -P face_vec.py -- --out file.npz"""
import sys, json
from pathlib import Path
import bpy, numpy as np
from mathutils import Matrix
ROOT = Path("/home/claude/vsc"); sys.path.insert(0, str(ROOT))
from slice import socketspace as ss
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
out = sys.argv[sys.argv.index("--") + 1:][1]
ctrl = bpy.data.objects.get("FACE_CTRL")
if ctrl is not None:
    ctrl.animation_data_clear()
    for ch in CMAP["channels"]:
        ctrl[ch["channel"]] = 0.0
    ctrl.update_tag()
sc = bpy.data.scenes["SLICE"]; sc.frame_set(sc.frame_start); bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
T = Matrix(ss.C) @ bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world.inverted()
o = bpy.data.objects["HERO_HEAD"].evaluated_get(dg); me = o.to_mesh(); M = T @ o.matrix_world
v = np.array([(M @ x.co)[:] for x in me.vertices]); n = np.array([(M.to_3x3() @ x.normal).normalized()[:] for x in me.vertices])
o.to_mesh_clear()
eyes = [T @ bpy.data.objects[k].evaluated_get(dg).matrix_world.translation for k in ("HERO_EYE_L", "HERO_EYE_R")]
# face_measure.py v1 numbers (world space): face width at the cheekbones, interocular
head = bpy.data.objects["HERO_HEAD"]; P = [head.matrix_world @ x.co for x in head.data.vertices]
eL = bpy.data.objects["HERO_EYE_L"].matrix_world.translation; eR = bpy.data.objects["HERO_EYE_R"].matrix_world.translation
ez = (eL.z + eR.z) / 2; ey = (eL.y + eR.y) / 2
cheek = [p for p in P if abs(p.z - (ez - 0.020)) < 0.004 and p.y < ey + 0.05]
fw = max(p.x for p in cheek) - min(p.x for p in cheek); io = (eL - eR).length
np.savez(out, v=v, n=n, eye_y=(eyes[0].y + eyes[1].y) / 2, fw=fw, io=io)
print("FACEVEC", out, len(v), "fw %.1f io %.1f" % (fw * 1000, io * 1000))
