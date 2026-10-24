"""Per frame: the smallest distance from any hair vertex to the body, dress, sleeves and hand surfaces (unsigned,
evaluated meshes). Frames where it drops under the threshold are listed."""
import bpy, bmesh, sys
from mathutils.bvhtree import BVHTree
sc = bpy.data.scenes["SLICE"]; thr = 0.003
hair = bpy.data.objects["HERO_HAIR"]; bodies = [bpy.data.objects[n] for n in ("HERO_BODY", "HERO_DRESS", "HERO_SLEEVE_L", "HERO_SLEEVE_R", "HERO_HAND_FG") if n in bpy.data.objects]
worst = (1.0, None); bad = []
for f in range(sc.frame_start, sc.frame_end + 1):
    sc.frame_set(f); dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for o in bodies:
        oe = o.evaluated_get(dg); tmp = bpy.data.meshes.new_from_object(oe); tmp.transform(oe.matrix_world); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    tree = BVHTree.FromBMesh(bm); bm.free()
    he = hair.evaluated_get(dg); M = he.matrix_world
    dmin = 1.0
    for v in list(he.data.vertices)[::2]:
        hit = tree.find_nearest(M @ v.co, 0.05)
        if hit[0] is not None and hit[3] < dmin: dmin = hit[3]
    if dmin < worst[0]: worst = (dmin, f)
    if dmin < thr: bad.append((f, round(dmin * 1000, 1)))
print(f"HAIR_BODY_CLEARANCE {sc['shot_id'] if 'shot_id' in sc else ''}: min {worst[0]*1000:.1f} mm on frame {worst[1]}; frames under {thr*1000:.0f} mm: {bad if bad else 'none'}")
