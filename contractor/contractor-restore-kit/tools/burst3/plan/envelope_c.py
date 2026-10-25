"""Rest bounding box of C_HEAD ∪ C_HAIR (evaluated, channels at 0, first frame) in SOCKET_HEAD's local frame —
the envelope of slice/export_shot.py — printed for comparison with the default head's."""
import bpy, json, sys
from pathlib import Path
ROOT = Path("/home/claude/vsc"); CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
ctrl = bpy.data.objects["FACE_CTRL"]; ctrl.animation_data_clear()
for ch in CMAP["channels"]: ctrl[ch["channel"]] = 0.0
sc = bpy.data.scenes["SLICE"]; sc.frame_set(sc.frame_start); bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get(); S = bpy.data.objects["SOCKET_HEAD"].evaluated_get(dg).matrix_world.inverted()
lo, hi = [1e9] * 3, [-1e9] * 3
for cn in (sys.argv[sys.argv.index("--") + 1:] or ["C_HEAD", "C_HAIR"]):
    for o in bpy.data.collections[cn].all_objects:
        if o.type != "MESH": continue
        e = o.evaluated_get(dg); me = bpy.data.meshes.new_from_object(e); mw = S @ e.matrix_world
        for v in me.vertices:
            p = mw @ v.co
            for i in range(3): lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
        bpy.data.meshes.remove(me)
print("ENVELOPE", json.dumps({"min": lo, "max": hi}))
