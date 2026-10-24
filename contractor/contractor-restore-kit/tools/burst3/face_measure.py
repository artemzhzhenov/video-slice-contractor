"""Face numbers on the head mesh, rest pose, world metres: face width at the cheekbones, interocular distance
(eye centres), nose width at the alae, face height (brow line to chin)."""
import bpy, json, sys
head = bpy.data.objects["HERO_HEAD"]
P = [head.matrix_world @ v.co for v in head.data.vertices]
eL = bpy.data.objects["HERO_EYE_L"].matrix_world.translation; eR = bpy.data.objects["HERO_EYE_R"].matrix_world.translation
ez = (eL.z + eR.z) / 2; ey = (eL.y + eR.y) / 2
cheek = [p for p in P if abs(p.z - (ez - 0.020)) < 0.004 and p.y < ey + 0.05]
front = min(p.y for p in P)
nose = [p for p in P if ez - 0.060 < p.z < ez - 0.040 and p.y < front + 0.022 and abs(p.x) < 0.035]
chin = min(p.z for p in P if abs(p.x) < 0.01 and p.y < ey + 0.01)
brows = bpy.data.objects["HERO_BROWS"]; bz = min((brows.matrix_world @ v.co).z for v in brows.data.vertices)
out = {"face_width_m": round(max(p.x for p in cheek) - min(p.x for p in cheek), 4),
       "interocular_m": round((eL - eR).length, 4),
       "nose_width_m": round(max(p.x for p in nose) - min(p.x for p in nose), 4),
       "face_height_brow_to_chin_m": round(bz - chin, 4)}
print("FACE", json.dumps(out))
