"""Is there hair lying on the right cheek (the default head's cheek strand)? Smallest distance from any hair
vertex to the cheek skin region under the right eye (socket frame), and the count of hair vertices within 4 mm."""
import bpy, bmesh
from mathutils.bvhtree import BVHTree
dg = bpy.context.evaluated_depsgraph_get()
head = bpy.data.objects["HERO_HEAD"].evaluated_get(dg); Mh = head.matrix_world
eR = bpy.data.objects["HERO_EYE_R"].matrix_world.translation
cheek = [Mh @ v.co for v in head.data.vertices if (Mh @ v.co).x < eR.x + 0.005 and (Mh @ v.co).x > eR.x - 0.055 and eR.z - 0.070 < (Mh @ v.co).z < eR.z - 0.012 and (Mh @ v.co).y < eR.y + 0.04]
bm = bmesh.new()
for p in cheek: bm.verts.new(p)
hair = bpy.data.objects["HERO_HAIR"].evaluated_get(dg); M = hair.matrix_world
import numpy as np
C = np.array([p[:] for p in cheek]); H = np.array([(M @ v.co)[:] for v in hair.data.vertices])
d = np.sqrt(((H[:, None, :] - C[None, :, :]) ** 2).sum(-1)).min(1)
print(f"CHEEK {bpy.data.filepath.split('/')[-1]}: cheek region {len(cheek)} skin verts; nearest hair {d.min()*1000:.1f} mm; hair verts within 4 mm of the cheek: {(d < 0.004).sum()}")
