"""Face numbers on the head mesh, rest pose, world metres — v2 (burst 3, 2026-10-24).
face_width_m and interocular_m exactly as in face_measure.py v1. nose_width_m is new: the ALAR width, measured by
ray casting — v1's band (40-60 mm below the eyes, within 22 mm of the nose tip's depth) lay below the nose, on the
upper lip and cheeks, and its width was set by the depth threshold (nose targets did not move it, cheek targets
did); it is still printed as nose_band_v1_m for traceability.
Alar width: the evaluated head mesh in world space (a fresh copy), a BVH; rays along +Y from in front of the face on
a grid x = 0..35 mm (0.25 mm) on each side, at heights from 6 mm above to 2 mm below the nose tip (0.5 mm). On each
row, the alar edge is the x of the steepest rise of the depth profile over 1 mm, searched outward from x = 5 mm;
the side's half-width is the outermost edge over the rows; nose_width = left + right."""
import bpy, json
from mathutils import Vector
from mathutils.bvhtree import BVHTree
head = bpy.data.objects["HERO_HEAD"]
P = [head.matrix_world @ v.co for v in head.data.vertices]
eL = bpy.data.objects["HERO_EYE_L"].matrix_world.translation; eR = bpy.data.objects["HERO_EYE_R"].matrix_world.translation
ez = (eL.z + eR.z) / 2; ey = (eL.y + eR.y) / 2
cheek = [p for p in P if abs(p.z - (ez - 0.020)) < 0.004 and p.y < ey + 0.05]
front = min(p.y for p in P)
band = [p for p in P if ez - 0.060 < p.z < ez - 0.040 and p.y < front + 0.022 and abs(p.x) < 0.035]
dg = bpy.context.evaluated_depsgraph_get()
me = bpy.data.meshes.new_from_object(head.evaluated_get(dg)); me.transform(head.matrix_world)
bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
tip = min(me.vertices, key=lambda v: v.co.y).co.copy()
def depth(x, z):
    hit = bvh.ray_cast(Vector((x, front - 0.05, z)), Vector((0, 1, 0)), 0.3)
    return hit[0].y - front if hit[0] else None
half = {}
for sgn, side in ((1, "L"), (-1, "R")):
    best = 0.0
    for k in range(-4, 13):                       # tip − 2 mm … tip + 6 mm
        z = tip.z + k * 0.0005
        xs = [i * 0.00025 for i in range(0, 141)]
        d = [depth(sgn * x, z) for x in xs]
        top, xe = -1.0, None
        for i in range(20, len(xs) - 4):           # from 5 mm outward; slope over 1 mm
            if d[i] is None or d[i + 4] is None:
                continue
            s = d[i + 4] - d[i]
            if s > top:
                top, xe = s, xs[i + 2]
        if xe is not None:
            best = max(best, xe)
    half[side] = best
bpy.data.meshes.remove(me)
brows = bpy.data.objects["HERO_BROWS"]; bz = min((brows.matrix_world @ v.co).z for v in brows.data.vertices)
chin = min(p.z for p in P if abs(p.x) < 0.01 and p.y < ey + 0.01)
out = {"face_width_m": round(max(p.x for p in cheek) - min(p.x for p in cheek), 4),
       "interocular_m": round((eL - eR).length, 4),
       "nose_width_m": round(half["L"] + half["R"], 4),
       "nose_half_l_m": round(half["L"], 4), "nose_half_r_m": round(half["R"], 4),
       "nose_band_v1_m": round(max(p.x for p in band) - min(p.x for p in band), 4),
       "face_height_brow_to_chin_m": round(bz - chin, 4)}
print("FACE", json.dumps(out))
