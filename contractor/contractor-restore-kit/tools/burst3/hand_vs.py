import bpy, bmesh
from mathutils.bvhtree import BVHTree
sc = bpy.data.scenes["SLICE"]
def tree(dg, names):
    bm = bmesh.new()
    for n in names:
        oe = bpy.data.objects[n].evaluated_get(dg); tmp = bpy.data.meshes.new_from_object(oe); tmp.transform(oe.matrix_world); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    tr = BVHTree.FromBMesh(bm); bm.free(); return tr
def dmin(dg, src, tr, step=2):
    oe = bpy.data.objects[src].evaluated_get(dg); M = oe.matrix_world; d = 1.0
    for v in list(oe.data.vertices)[::step]:
        h = tr.find_nearest(M @ v.co, 0.06)
        if h[0] is not None and h[3] < d: d = h[3]
    return d
res = {"hair_vs_body": (1.0, None), "hand_vs_hair": (1.0, None), "hand_vs_glasses": (1.0, None)}
for f in range(sc.frame_start, sc.frame_end + 1):
    sc.frame_set(f); dg = bpy.context.evaluated_depsgraph_get()
    body = tree(dg, ["HERO_BODY", "HERO_DRESS", "HERO_SLEEVE_L", "HERO_SLEEVE_R"]); hair = tree(dg, ["HERO_HAIR"]); gl = tree(dg, ["HERO_GLASSES"])
    for k, (src, tr) in {"hair_vs_body": ("HERO_HAIR", body), "hand_vs_hair": ("HERO_HAND_FG", hair), "hand_vs_glasses": ("HERO_HAND_FG", gl)}.items():
        d = dmin(dg, src, tr)
        if d < res[k][0]: res[k] = (d, f)
print("DIST " + "; ".join(f"{k}: min {v[0]*1000:.1f} mm on frame {v[1]}" for k, v in res.items()))
