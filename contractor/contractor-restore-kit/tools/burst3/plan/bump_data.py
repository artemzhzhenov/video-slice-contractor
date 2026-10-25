"""Data for the analytic sculpt-bump field (contractor, burst 3): the default head's build-time vertex positions
(HERO_HEAD mesh data = build_character.py's co for head vertices), the SOCKET_BOUNDARY ring, the matrix to the
socket's contract frame used by face_shape_distance.py (channels at 0, first frame), and face landmarks."""
import sys, json
from pathlib import Path
import bpy, numpy as np
from mathutils import Matrix
ROOT = Path("/home/claude/vsc"); sys.path.insert(0, str(ROOT))
from slice import socketspace as ss
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
out = sys.argv[sys.argv.index("--") + 1:][1]
ctrl = bpy.data.objects["FACE_CTRL"]; ctrl.animation_data_clear()
for ch in CMAP["channels"]: ctrl[ch["channel"]] = 0.0
ctrl.update_tag()
sc = bpy.data.scenes["SLICE"]; sc.frame_set(sc.frame_start); bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
T = Matrix(ss.C) @ bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world.inverted()
h = bpy.data.objects["HERO_HEAD"]; M = T @ h.evaluated_get(dg).matrix_world
co = np.array([v.co[:] for v in h.data.vertices])
vg = h.vertex_groups["SOCKET_BOUNDARY"].index
ring = np.array([v.co[:] for v in h.data.vertices if any(g.group == vg for g in v.groups)])
# landmarks in build space (head data coordinates)
mwi = h.matrix_world.inverted()
eyes = [mwi @ bpy.data.objects[k].matrix_world.translation for k in ("HERO_EYE_L", "HERO_EYE_R")]
np.savez(out, co=co, ring=ring, M=np.array(M), eyeL=np.array(eyes[0][:]), eyeR=np.array(eyes[1][:]), head_mw=np.array(h.matrix_world))
print("BUMPDATA", co.shape, "ring", ring.shape, "eyeL", [round(x, 4) for x in eyes[0]], "head_mw identity", np.allclose(np.array(h.matrix_world), np.eye(4), atol=1e-6))
