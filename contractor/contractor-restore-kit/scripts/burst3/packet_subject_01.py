"""packet_subject_01.py — burst 3: a "parent photo" of a synthetic child (TASK §3.4).

    blender -b subject_01_character.blend --python-exit-code 2 -P packet_subject_01.py -- \
        --scene window_day --subject subject_01.json --out packet_subject_01_window_day.blend

Opens the child's character file (master look) and saves a SEPARATE scene file; the character file is not
changed. In the photo scene:
  - the child's own simple clothes: a mustard long-sleeved tunic over the master dress (other colour, other cut:
    tunic length, long sleeves to the wrist). Built as copies of HERO_DRESS / HERO_SLEEVE_* and of the forearm skin,
    pushed out along their normals and skinned to the same rig, so they follow the body;
  - a simple home: floor, back wall, a side wall with a window opening, a sofa, a low table, a shelf (forms);
  - daylight through the window: a sun through the opening, a sky-coloured area light filling the opening, a dim
    sky world;
  - a phone-like camera: 26 mm full-frame equivalent (36 mm sensor width), portrait 3:4, ~0.7 m from the face,
    slightly above eye level and tilted down, head almost frontal; a light smile on FACE_CTRL;
  - photoreal materials switched on the same geometry: skin with subsurface scattering and procedural pore/
    roughness detail, glossy coat on the eyes (highlights), hair and brows with sheen and colour variation.
Noise, softness and phone compression are added by the client at render time. Deterministic; no randomness."""
import argparse
import json
import math
import sys

import bpy
from mathutils import Vector

CAM_LENS_MM = 26.0
CAM_SENSOR_MM = 36.0
CAM_DIST_M = 0.55
CAM_AZIMUTH_DEG = -8.0          # almost frontal
CAM_ABOVE_EYES_M = 0.07         # a parent holding the phone a little above the child's eyes
RES = (1536, 2048)              # portrait 3:4
PHONE_EXPOSURE = 1.1            # a phone meters on the face
SMILE = {"mouth_corner_l": 0.34, "mouth_corner_r": 0.30, "cheek_raise_l": 0.20, "cheek_raise_r": 0.17,
         "squint_l": 0.08, "squint_r": 0.07, "mouth_width": 0.10, "lid_aperture_l": 0.04, "lid_aperture_r": 0.04}
ARM_REST = {"upperarm01.L": (6, 0, -30), "upperarm01.R": (6, 0, 30), "lowerarm01.L": (-12, 0, 0), "lowerarm01.R": (-12, 0, 0)}
TOP_COLOUR = (0.58, 0.40, 0.07)             # mustard cotton
TOP_HEM_Z_M = 0.74                          # tunic length
CLOTH_PUSH_M = 0.008
SLEEVE_PUSH_M = 0.006
WINDOW = {"x": 1.60, "y_from": -1.05, "y_to": 0.15, "z_from": 0.85, "z_to": 2.05}   # opening in the side wall


def fail(m):
    print(f"PACKET_ERROR {m}")
    sys.exit(2)


def principled(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf


def noise(nt, scale, detail=6.0, roughness=0.55):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nz.inputs["Roughness"].default_value = roughness
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    return nz


def photo_skin(tone):
    m, nt, b = principled("PHOTO_SKIN")
    b.inputs["Base Color"].default_value = (*tone, 1.0)
    b.inputs["Subsurface Weight"].default_value = 0.35
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.25)
    b.inputs["Subsurface Scale"].default_value = 0.004
    b.inputs["Coat Weight"].default_value = 0.08                     # a faint skin sheen
    b.inputs["Coat Roughness"].default_value = 0.35
    pores = noise(nt, 900.0, 4.0, 0.6)                                 # pores / micro relief
    blotch = noise(nt, 40.0, 3.0, 0.5)                                 # roughness variation across the face
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(pores.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.38
    mr.inputs["To Max"].default_value = 0.55
    nt.links.new(blotch.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    return m


def photo_hair(colour, name):
    m, nt, b = principled(name)
    b.inputs["Base Color"].default_value = (*colour, 1.0)
    b.inputs["Roughness"].default_value = 0.46
    b.inputs["Sheen Weight"].default_value = 0.08
    b.inputs["Coat Weight"].default_value = 0.05
    b.inputs["Coat Roughness"].default_value = 0.3
    var = noise(nt, 120.0, 2.0, 0.5)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*[c * 0.75 for c in colour], 1.0)
    mix.inputs[7].default_value = (*[min(1.0, c * 1.35) for c in colour], 1.0)
    nt.links.new(var.outputs["Fac"], mix.inputs[0])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m


def glossy_coat(mat_name):
    m = bpy.data.materials.get(mat_name)
    if m is None or not m.use_nodes:
        return
    b = m.node_tree.nodes.get("Principled BSDF")
    if b is not None:
        b.inputs["Coat Weight"].default_value = 1.0                    # the cornea: sharp highlights in the eyes
        b.inputs["Coat Roughness"].default_value = 0.02
        b.inputs["Coat IOR"].default_value = 1.376


def cloth(colour):
    m, nt, b = principled("PHOTO_TOP_COTTON")
    b.inputs["Base Color"].default_value = (*colour, 1.0)
    b.inputs["Roughness"].default_value = 0.88
    b.inputs["Sheen Weight"].default_value = 0.4
    weave = noise(nt, 600.0, 2.0, 0.5)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(weave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def inflated_copy(src, name, push, keep_face, radial=False):
    """Copy of a skinned mesh, faces filtered by keep_face(world centre) and pushed out along normals."""
    me = src.data.copy()
    me.name = name
    obj = src.copy()
    obj.data = me
    obj.name = name
    obj.animation_data_clear()
    bpy.context.scene.collection.objects.link(obj)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    M = src.matrix_world
    drop = [f for f in bm.faces if not keep_face(M @ f.calc_center_median())]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bm.normal_update()
    if radial:                     # the dress normals face the body: use each normal, turned to point AWAY from
        yc = sum(v.co.y for v in bm.verts) / max(1, len(bm.verts))       # the torso axis (on the shoulder tops the
        zc = sum(v.co.z for v in bm.verts) / max(1, len(bm.verts))       # push goes up, on the sides out)
        for v in bm.verts:
            away = Vector((v.co.x, v.co.y - yc, v.co.z - zc))
            n = v.normal if v.normal.dot(away) >= 0 else -v.normal
            v.co = v.co + n * push
    else:
        for v in bm.verts:
            v.co = v.co + v.normal * push
    bm.to_mesh(me)
    bm.free()
    me.update()
    return obj


def box(name, lo, hi, mat, coll):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
    o.scale = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    me.materials.append(mat)
    coll.objects.link(o)
    return o


def flat(name, rgb, rough=0.8):
    m, nt, b = principled(name)
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=["window_day"])
    ap.add_argument("--subject", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    subj = json.load(open(a.subject))
    sc = bpy.data.scenes["SLICE"]
    rig = bpy.data.objects.get("RIG_HERO") or fail("RIG_HERO missing — run on the child's character file")
    ctrl = bpy.data.objects["FACE_CTRL"]

    # ---- pose: rest body, arms down, a light smile; a still, so no animation ----
    rig.animation_data_clear()
    ctrl.animation_data_clear()
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    for b_, r_ in ARM_REST.items():
        rig.pose.bones[b_].rotation_euler = [math.radians(v) for v in r_]
    for k in list(ctrl.keys()):
        if isinstance(ctrl[k], float):
            ctrl[k] = 0.0
    for k, v in SMILE.items():
        ctrl[k] = v
    sc.frame_start = sc.frame_end = sc.frame_current = 1
    bpy.context.view_layer.update()

    # ---- own clothes: mustard long-sleeved tunic over the dress ----
    top_mat = cloth(TOP_COLOUR)
    clothes = []
    dress = bpy.data.objects["HERO_DRESS"]
    clothes.append(inflated_copy(dress, "PHOTO_TOP_BODY", CLOTH_PUSH_M, lambda c: c.z > TOP_HEM_Z_M, radial=True))
    for s in ("L", "R"):
        clothes.append(inflated_copy(bpy.data.objects[f"HERO_SLEEVE_{s}"], f"PHOTO_TOP_SLEEVE_{s}", CLOTH_PUSH_M + 0.001, lambda c: True))
    body = bpy.data.objects["HERO_BODY"]
    fore = {s: [b.name for b in rig.data.bones if b.name.startswith(("lowerarm01." + s, "lowerarm02." + s))] for s in ("L", "R")}
    vg_idx = {g.index: g.name for g in body.vertex_groups}
    fore_verts = {v.index for v in body.data.vertices
                  if max(((vg_idx[g.group], g.weight) for g in v.groups), key=lambda t: t[1], default=("", 0))[0] in fore["L"] + fore["R"]}
    keep = {p.index for p in body.data.polygons if all(i in fore_verts for i in p.vertices)}
    centres = {p.index: (body.matrix_world @ p.center) for p in body.data.polygons if p.index in keep}
    fset = set(tuple(round(x, 5) for x in c) for c in centres.values())
    sleeve_fore = inflated_copy(body, "PHOTO_TOP_FOREARM", SLEEVE_PUSH_M, lambda c: tuple(round(x, 5) for x in c) in fset)
    clothes.append(sleeve_fore)
    for o in clothes:
        o.data.materials.clear()
        o.data.materials.append(top_mat)
        for p in o.data.polygons:
            p.material_index = 0
            p.use_smooth = True
        for coll in list(o.users_collection):
            coll.objects.unlink(o)
        bpy.data.collections["C_BODY"].objects.link(o)

    # ---- photoreal materials on the same geometry (the character file keeps the master look) ----
    skin = photo_skin(tuple(subj["tone_albedo_linear"]))
    for name in ("HERO_HEAD", "HERO_BODY", "HERO_HAND_FG"):
        o = bpy.data.objects.get(name)
        if o is None:
            continue
        for i, slot in enumerate(o.material_slots):
            if slot.material is not None and slot.material.name.startswith("HERO_SKIN"):
                o.material_slots[i].material = skin
    hair_m = photo_hair(tuple(subj["hair"]["color_linear"]), "PHOTO_HAIR")
    brow_m = photo_hair(tuple(subj["brow_color_linear"]), "PHOTO_BROW")
    for name, m in (("HERO_HAIR", hair_m), ("HERO_BROWS", brow_m)):
        o = bpy.data.objects[name]
        for i in range(len(o.material_slots)):
            o.material_slots[i].material = m
    for mn in ("HERO_EYE_SCLERA", "HERO_EYE_IRIS", "HERO_EYE_PUPIL"):
        glossy_coat(mn)

    # ---- the room: floor, back wall, side wall with a window opening, sofa, table, shelf ----
    for o in list(bpy.data.collections["C_ENV"].objects):
        bpy.data.objects.remove(o, do_unlink=True)
    env = bpy.data.collections["C_ENV"]
    wall = flat("PHOTO_WALL_PAINT", (0.62, 0.58, 0.50), 0.9)
    floor_m = flat("PHOTO_FLOOR_WOOD", (0.32, 0.20, 0.11), 0.55)
    sofa_m = flat("PHOTO_SOFA_FABRIC", (0.16, 0.22, 0.30), 0.95)
    wood = flat("PHOTO_TABLE_WOOD", (0.40, 0.26, 0.14), 0.5)
    box("ROOM_FLOOR", (-3, -3, -0.02), (3, 3, 0.0), floor_m, env)
    box("ROOM_WALL_BACK", (-3, 1.6, 0.0), (3, 1.68, 2.7), wall, env)
    W = WINDOW
    x0, x1 = W["x"], W["x"] + 0.08
    box("ROOM_WALL_SIDE_A", (x0, -3, 0), (x1, W["y_from"], 2.7), wall, env)
    box("ROOM_WALL_SIDE_B", (x0, W["y_to"], 0), (x1, 1.68, 2.7), wall, env)
    box("ROOM_WALL_SIDE_SILL", (x0, W["y_from"], 0), (x1, W["y_to"], W["z_from"]), wall, env)
    box("ROOM_WALL_SIDE_TOP", (x0, W["y_from"], W["z_to"]), (x1, W["y_to"], 2.7), wall, env)
    box("ROOM_SOFA_SEAT", (-1.3, 0.75, 0.0), (0.6, 1.45, 0.42), sofa_m, env)
    box("ROOM_SOFA_BACK", (-1.3, 1.25, 0.42), (0.6, 1.5, 0.95), sofa_m, env)
    box("ROOM_TABLE", (-0.9, -0.2, 0.0), (-0.35, 0.25, 0.40), wood, env)
    box("ROOM_SHELF", (0.9, 1.35, 0.0), (1.45, 1.6, 1.6), wood, env)

    # ---- daylight through the window ----
    lights = bpy.data.collections["C_LIGHTS"]
    for o in list(lights.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sun_d = bpy.data.lights.new("WINDOW_SUN", "SUN")
    sun_d.energy = 3.2
    sun_d.color = (1.0, 0.96, 0.90)
    sun_d.angle = math.radians(1.5)
    sun = bpy.data.objects.new("WINDOW_SUN", sun_d)
    lights.objects.link(sun)
    sun.rotation_euler = (Vector((-1.0, 0.25, -0.55))).to_track_quat("-Z", "Y").to_euler()
    sky_d = bpy.data.lights.new("WINDOW_SKY", "AREA")
    sky_d.shape = "RECTANGLE"
    sky_d.size = W["y_to"] - W["y_from"]
    sky_d.size_y = W["z_to"] - W["z_from"]
    sky_d.energy = 650.0
    sky_d.color = (0.82, 0.90, 1.0)
    sky = bpy.data.objects.new("WINDOW_SKY", sky_d)
    lights.objects.link(sky)
    sky.location = (x0 - 0.01, (W["y_from"] + W["y_to"]) / 2, (W["z_from"] + W["z_to"]) / 2)
    sky.rotation_euler = (0.0, math.radians(-90.0), 0.0)            # facing −X, into the room
    world = bpy.data.worlds.new("PHOTO_SKY")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.55, 0.68, 0.90, 1.0)
    bg.inputs[1].default_value = 0.6

    # ---- the phone camera ----
    eyes = (bpy.data.objects["HERO_EYE_L"].matrix_world.translation + bpy.data.objects["HERO_EYE_R"].matrix_world.translation) / 2
    cam = bpy.data.objects["CAM_001"]
    cam.animation_data_clear()
    cam.parent = None
    cam.data.lens = CAM_LENS_MM
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = CAM_SENSOR_MM
    az = math.radians(CAM_AZIMUTH_DEG)
    cam.location = eyes + Vector((CAM_DIST_M * math.sin(az), -CAM_DIST_M * math.cos(az), CAM_ABOVE_EYES_M))
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (eyes + Vector((0, 0, -0.10)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.view_settings.exposure = PHONE_EXPOSURE        # a phone meters on the face
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"
    sc.render.filepath = "//renders/packet_subject_01_window_day/"
    sc["packet_scene"] = a.scene
    sc["packet_subject"] = subj["subject"]

    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    tilt = math.degrees(math.atan2(CAM_ABOVE_EYES_M + 0.10, CAM_DIST_M))
    print(f"PACKET_OK {a.out} scene={a.scene} camera {CAM_LENS_MM:.0f} mm / {CAM_SENSOR_MM:.0f} mm sensor, "
          f"{CAM_DIST_M} m, azimuth {CAM_AZIMUTH_DEG}°, tilt down ≈{tilt:.0f}°, portrait {RES[0]}x{RES[1]}; "
          f"clothes {[o.name for o in clothes]}")


if __name__ == "__main__":
    main()
