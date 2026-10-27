"""packet_subject.py — burst 3: the "parent photos" of a synthetic child (spec item 4; TASK §3.4; Q63).

    blender -b subject_NN_character.blend --python-exit-code 2 -P packet_subject.py -- \
        --scene window_day|warm_indoor|overhead|open_shade --subject subject_NN.json --out packet_subject_NN_<scene>.blend

Generalised from packet_subject_01.py (the accepted pilot): subject_01 in window_day is the pilot's scene exactly (camera,
smile, the mustard tunic); every other child / scene takes its camera (24-28 mm, 0.45-0.75 m — within the spec's 0.4-1.2 m, the face large enough, height, tilt, azimuth) and
its clothes (tunic / t-shirt / sweater, a cotton colour) deterministically from the child's seed and the scene name.
Scenes: window_day — daylight through a side window (the pilot); warm_indoor — evening, warm ceiling lamp + table lamp,
the window dark; overhead — a ceiling panel straight above, little fill (top-down shadows); open_shade — outdoors in the
shade of a wall: sky light only, no direct sun on the child. Expressions: smile in window_day and overhead, neutral in
warm_indoor and open_shade (spec: neutral and smiling).
--- the pilot's notes follow ---

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


SCENES = ("window_day", "warm_indoor", "overhead", "open_shade")
SCENE_SMILE = {"window_day": True, "warm_indoor": False, "overhead": True, "open_shade": False}
SCENE_EXPOSURE = {"window_day": PHONE_EXPOSURE, "warm_indoor": 0.7, "overhead": 0.3, "open_shade": 0.6}
TOPS = {"tunic": TOP_HEM_Z_M, "tshirt": 0.80, "sweater": 0.76}           # hem height of the top (m)
COTTON = [(0.58, 0.40, 0.07), (0.10, 0.25, 0.45), (0.45, 0.08, 0.10), (0.12, 0.33, 0.18), (0.55, 0.30, 0.42),
          (0.70, 0.66, 0.58), (0.06, 0.06, 0.07), (0.62, 0.22, 0.06), (0.28, 0.45, 0.55)]


def scene_rng(subj, scene):
    import random
    return random.Random(int(subj.get("seed", 0)) * 1000 + SCENES.index(scene) * 37 + 11)


def camera_for(subj, scene):
    """(lens mm, distance m, azimuth deg, above-eyes m); the pilot's for subject_01 / window_day."""
    if subj["subject"] == "subject_01" and scene == "window_day":
        return CAM_LENS_MM, CAM_DIST_M, CAM_AZIMUTH_DEG, CAM_ABOVE_EYES_M
    r = scene_rng(subj, scene)
    return round(r.uniform(24.0, 28.0), 1), round(r.uniform(0.45, 0.75), 2), round(r.uniform(-22.0, 22.0), 1), round(r.uniform(-0.04, 0.16), 3)


def clothes_for(subj):
    if subj["subject"] == "subject_01":
        return "tunic", TOP_COLOUR
    import random
    r = random.Random(int(subj.get("seed", 0)) * 7 + 3)
    return r.choice(sorted(TOPS)), r.choice(COTTON)


def area(name, size, size_y, energy, colour, loc, aim, coll):
    d = bpy.data.lights.new(name, "AREA"); d.shape = "RECTANGLE"; d.size, d.size_y = size, size_y
    d.energy = energy; d.color = colour
    o = bpy.data.objects.new(name, d); coll.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def point(name, radius, energy, colour, loc, coll):
    d = bpy.data.lights.new(name, "POINT"); d.shadow_soft_size = radius; d.energy = energy; d.color = colour
    o = bpy.data.objects.new(name, d); coll.objects.link(o); o.location = loc
    return o


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=list(SCENES))
    ap.add_argument("--subject", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    subj = json.load(open(a.subject))
    sc = bpy.data.scenes["SLICE"]
    rig = bpy.data.objects.get("RIG_HERO") or fail("RIG_HERO missing — run on the child's character file")
    ctrl = bpy.data.objects["FACE_CTRL"]
    lens, dist, az_deg, above = camera_for(subj, a.scene)
    top_kind, top_colour = clothes_for(subj)

    # ---- pose: rest body, arms down, smile or neutral; a still, so no animation ----
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
    if SCENE_SMILE[a.scene]:
        for k, v in SMILE.items():
            ctrl[k] = v
    sc.frame_start = sc.frame_end = sc.frame_current = 1
    bpy.context.view_layer.update()

    # ---- own clothes: a top over the dress (tunic / t-shirt / sweater), the child's cotton colour ----
    top_mat = cloth(top_colour)
    clothes = []
    dress = bpy.data.objects["HERO_DRESS"]
    hem = TOPS[top_kind]
    clothes.append(inflated_copy(dress, "PHOTO_TOP_BODY", CLOTH_PUSH_M, lambda c: c.z > hem, radial=True))
    for s in ("L", "R"):
        clothes.append(inflated_copy(bpy.data.objects[f"HERO_SLEEVE_{s}"], f"PHOTO_TOP_SLEEVE_{s}", CLOTH_PUSH_M + 0.001, lambda c: True))
    if top_kind != "tshirt":                       # long sleeves: the forearms covered too
        body = bpy.data.objects["HERO_BODY"]
        fore = {s: [b.name for b in rig.data.bones if b.name.startswith(("lowerarm01." + s, "lowerarm02." + s))] for s in ("L", "R")}
        vg_idx = {g.index: g.name for g in body.vertex_groups}
        fore_verts = {v.index for v in body.data.vertices
                      if max(((vg_idx[g.group], g.weight) for g in v.groups), key=lambda t: t[1], default=("", 0))[0] in fore["L"] + fore["R"]}
        keep = {p.index for p in body.data.polygons if all(i in fore_verts for i in p.vertices)}
        centres = {p.index: (body.matrix_world @ p.center) for p in body.data.polygons if p.index in keep}
        fset = set(tuple(round(x, 5) for x in c) for c in centres.values())
        clothes.append(inflated_copy(body, "PHOTO_TOP_FOREARM", SLEEVE_PUSH_M + (0.002 if top_kind == "sweater" else 0.0),
                                     lambda c: tuple(round(x, 5) for x in c) in fset))
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

    # ---- the set ----
    for o in list(bpy.data.collections["C_ENV"].objects):
        bpy.data.objects.remove(o, do_unlink=True)
    env = bpy.data.collections["C_ENV"]
    lights = bpy.data.collections["C_LIGHTS"]
    for o in list(lights.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    world = bpy.data.worlds.new("PHOTO_WORLD")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    W = WINDOW
    x0, x1 = W["x"], W["x"] + 0.08
    eyes = (bpy.data.objects["HERO_EYE_L"].matrix_world.translation + bpy.data.objects["HERO_EYE_R"].matrix_world.translation) / 2
    if a.scene in ("window_day", "warm_indoor", "overhead"):
        wall = flat("PHOTO_WALL_PAINT", (0.62, 0.58, 0.50), 0.9)
        floor_m = flat("PHOTO_FLOOR_WOOD", (0.32, 0.20, 0.11), 0.55)
        sofa_m = flat("PHOTO_SOFA_FABRIC", (0.16, 0.22, 0.30), 0.95)
        wood = flat("PHOTO_TABLE_WOOD", (0.40, 0.26, 0.14), 0.5)
        box("ROOM_FLOOR", (-3, -3, -0.02), (3, 3, 0.0), floor_m, env)
        box("ROOM_WALL_BACK", (-3, 1.6, 0.0), (3, 1.68, 2.7), wall, env)
        box("ROOM_WALL_SIDE_A", (x0, -3, 0), (x1, W["y_from"], 2.7), wall, env)
        box("ROOM_WALL_SIDE_B", (x0, W["y_to"], 0), (x1, 1.68, 2.7), wall, env)
        box("ROOM_WALL_SIDE_SILL", (x0, W["y_from"], 0), (x1, W["y_to"], W["z_from"]), wall, env)
        box("ROOM_WALL_SIDE_TOP", (x0, W["y_from"], W["z_to"]), (x1, W["y_to"], 2.7), wall, env)
        box("ROOM_SOFA_SEAT", (-1.3, 0.75, 0.0), (0.6, 1.45, 0.42), sofa_m, env)
        box("ROOM_SOFA_BACK", (-1.3, 1.25, 0.42), (0.6, 1.5, 0.95), sofa_m, env)
        box("ROOM_TABLE", (-0.9, -0.2, 0.0), (-0.35, 0.25, 0.40), wood, env)
        box("ROOM_SHELF", (0.9, 1.35, 0.0), (1.45, 1.6, 1.6), wood, env)
        if not (a.scene == "window_day" and subj["subject"] == "subject_01"):   # every camera but the pilot's sees the ceiling
            box("ROOM_CEILING", (-3, -3, 2.7), (3, 1.68, 2.78), wall, env)
    if a.scene == "window_day":                     # the pilot's daylight, unchanged
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
        sky.rotation_euler = (0.0, math.radians(-90.0), 0.0)
        world.name = "PHOTO_SKY"
        bg.inputs[0].default_value = (0.55, 0.68, 0.90, 1.0)
        bg.inputs[1].default_value = 0.6
    elif a.scene == "warm_indoor":                  # evening: a warm ceiling lamp, a table lamp, the window dark
        shade = flat("PHOTO_LAMPSHADE", (0.85, 0.78, 0.62), 0.9)
        box("ROOM_LAMP_SHADE", (-0.78, -0.08, 0.40), (-0.47, 0.13, 0.62), shade, env)
        point("LAMP_CEILING", 0.12, 120.0, (1.0, 0.74, 0.46), (0.25, -0.35, 2.55), lights)
        point("LAMP_TABLE", 0.10, 45.0, (1.0, 0.66, 0.36), (-0.62, 0.02, 0.70), lights)
        bg.inputs[0].default_value = (0.02, 0.025, 0.05, 1.0)
        bg.inputs[1].default_value = 0.2
    elif a.scene == "overhead":                     # a ceiling panel straight above the child, a weak bounce
        area("CEILING_PANEL", 0.6, 0.6, 260.0, (1.0, 0.95, 0.88), (eyes.x, eyes.y + 0.10, 2.62), (eyes.x, eyes.y + 0.10, 0.0), lights)
        bg.inputs[0].default_value = (0.30, 0.30, 0.32, 1.0)
        bg.inputs[1].default_value = 0.08
    elif a.scene == "open_shade":                   # outdoors, in the shade of a house wall: the open sky only
        paving = flat("PHOTO_PAVING", (0.30, 0.28, 0.25), 0.85)
        brick = flat("PHOTO_BRICK", (0.38, 0.20, 0.14), 0.9)
        hedge = flat("PHOTO_HEDGE", (0.06, 0.14, 0.05), 0.95)
        box("YARD_GROUND", (-6, -6, -0.02), (6, 6, 0.0), paving, env)
        box("YARD_WALL", (-4, 1.2, 0.0), (4, 1.4, 3.2), brick, env)
        box("YARD_EAVE", (-4, -0.6, 3.0), (4, 1.4, 3.1), brick, env)          # the overhang that shades the child
        box("YARD_HEDGE", (-4, -4.5, 0.0), (4, -3.7, 1.4), hedge, env)
        sun_d = bpy.data.lights.new("YARD_SUN", "SUN"); sun_d.energy = 4.0; sun_d.color = (1.0, 0.95, 0.88); sun_d.angle = math.radians(0.6)
        sun = bpy.data.objects.new("YARD_SUN", sun_d); lights.objects.link(sun)
        sun.rotation_euler = (Vector((0.3, 0.9, -0.55))).to_track_quat("-Z", "Y").to_euler()   # from behind the wall
        bg.inputs[0].default_value = (0.50, 0.65, 0.95, 1.0)
        bg.inputs[1].default_value = 1.6

    # ---- the phone camera ----
    cam = bpy.data.objects["CAM_001"]
    cam.animation_data_clear()
    cam.parent = None
    cam.data.lens = lens
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = CAM_SENSOR_MM
    az = math.radians(az_deg)
    cam.location = eyes + Vector((dist * math.sin(az), -dist * math.cos(az), above))
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (eyes + Vector((0, 0, -0.10)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.view_settings.exposure = SCENE_EXPOSURE[a.scene]
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"
    sc.render.filepath = f"//renders/packet_{subj['subject']}_{a.scene}/"
    sc["packet_scene"] = a.scene
    sc["packet_subject"] = subj["subject"]

    bpy.ops.wm.save_as_mainfile(filepath=a.out, compress=True)
    tilt = math.degrees(math.atan2(above + 0.10, dist))
    print(f"PACKET_OK {a.out} scene={a.scene} expression={'smile' if SCENE_SMILE[a.scene] else 'neutral'} camera {lens:.1f} mm / "
          f"{CAM_SENSOR_MM:.0f} mm sensor, {dist} m, azimuth {az_deg}°, tilt down ≈{tilt:.0f}°, portrait {RES[0]}x{RES[1]}; "
          f"top {top_kind} {tuple(round(x, 2) for x in top_colour)}; clothes {[o.name for o in clothes]}")


if __name__ == "__main__":
    main()
