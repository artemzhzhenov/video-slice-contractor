"""Phase 0.5 slice — scene template. Run headless:

    blender -b -P slice/scene_template.py -- --out benchmarks/bakeoff/<exp>/slice/template.blend

Builds the scene skeleton the whole pass table depends on (proposal §1–§2): collections,
materials, six view layers with per-layer exclusion / holdout / indirect-only, pass flags, render
and colour settings, socket empties, camera, and clearly named PLACEHOLDER_* geometry so the
pipeline (exporters, precomp, round-trip) can be developed before the rigger delivers. Nothing
here is a character; everything here is replaced by real assets without renaming.

Stdlib + bpy only. Every setting is explicit — no reliance on Blender defaults (CLAUDE.md §6,
providers rule: never rely on vendor defaults)."""
import argparse
import math
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())

COLLECTIONS = CONV["scene_naming"]["collections"]
MATERIALS = CONV["scene_naming"]["materials"]
VIEW_LAYERS = CONV["scene_naming"]["view_layers"]
HERO_HEAD_COLLS = ("C_HEAD", "C_HAIR")
HEAD_RADIUS = 0.14      # placeholder head sphere (m)
HEAD_CENTRE_Z = 1.51    # its centre, Blender world Z (m); socket at 1.42

# Per view layer: which collections are excluded / holdout / indirect-only. Everything not named
# renders normally. Source: proposal §1 pass table rows 1–4, 9; ADR-0002 D2 amendment (head is a
# shadow-caster only — enforced on the objects' ray visibility, see set_head_shadow_caster_only).
LAYER_RULES = {
    "L_FULL":       {},
    # Occluders (the hand) are shadow-casting but camera-invisible in both body plates, so that
    # PRECOMP_BACK holds nothing that PRECOMP_FRONT will lay over again at soft edges — the
    # pair reproduces the full render exactly instead of double-counting the occluder.
    "L_BODY":       {"exclude": ["C_HEAD", "C_HAIR"], "indirect_only": ["C_HAND_FG"]},
    "L_BODYSHADOW": {"indirect_only": ["C_HEAD", "C_HAIR", "C_HAND_FG"]},
    # The head layer is the head's UNOCCLUDED silhouette: occluders are shadow-only here too, so
    # FRONT over (HEAD over BACK) does not attenuate the head twice where the hand overlaps it.
    "L_HEAD":       {"holdout": ["C_BODY", "C_ENV"], "indirect_only": ["C_HAND_FG"]},
    "L_FG":         {"holdout": ["C_HEAD", "C_HAIR", "C_BODY", "C_ENV"]},
    "L_DATA":       {},
}
# Passes per layer (proposal §1 rows 2, 5, 10, 14).
LAYER_PASSES = {
    "L_FULL":       {"combined": True, "cryptomatte_object": True, "cryptomatte_material": True},
    "L_BODY":       {"combined": True},
    "L_BODYSHADOW": {"combined": True},
    "L_HEAD":       {"combined": True},
    "L_FG":         {"combined": True},
    "L_DATA":       {"combined": False, "z": True, "vector": True},
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--shot", default="SHOT_001")
    p.add_argument("--root-pose", nargs=4, type=float, metavar=("X", "Y", "Z", "YAW_DEG"), default=None,
                   help="TEST ONLY: place SOCKET_SPACE_ROOT away from the origin (Blender world, metres and degrees about Z) so the root⁻¹ term of every export convention is exercised; the camera and environment stay where they are")
    return p.parse_args(argv)


def fail(msg):
    print(f"TEMPLATE_ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def new_collection(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def new_material(name, base_color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        fail(f"no Principled BSDF on {name}")
    bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    return m


def set_head_shadow_caster_only(obj):
    """ADR-0002 D2 amendment: no indirect light from head or hair onto the body."""
    obj.visible_camera = True
    obj.visible_shadow = True
    obj.visible_diffuse = False
    obj.visible_glossy = False
    obj.visible_transmission = False
    obj.visible_volume_scatter = False


def _primitive(kind, name, **kw):
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(**kw)
    o = bpy.context.active_object
    o.name = name
    return o


def _sorted_by_angle(verts):
    import math
    cx = sum(v.co.x for v in verts) / len(verts)
    cy = sum(v.co.y for v in verts) / len(verts)
    return sorted(verts, key=lambda v: math.atan2(v.co.y - cy, v.co.x - cx))


def _ring_world_points(obj):
    """World positions of an object's SOCKET_BOUNDARY ring in weight (angular) order."""
    vg = obj.vertex_groups[CONV["scene_naming"]["vertex_group_socket_boundary"]]
    members = []
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == vg.index:
                members.append((g.weight, v.index))
    members.sort()
    return [obj.matrix_world @ obj.data.vertices[i].co for _, i in members]


def _tag_ring(obj, verts):
    """Vertex group SOCKET_BOUNDARY with the vertex's ORDER around the ring stored as its
    weight (index / count), sorted by angle about the ring centre — so an exporter can recover
    a polyline in a defined order from any mesh that follows the convention."""
    import math
    cx = sum(v.co.x for v in verts) / len(verts)
    cy = sum(v.co.y for v in verts) / len(verts)
    ordered = _sorted_by_angle(verts)
    vg = obj.vertex_groups.new(name=CONV["scene_naming"]["vertex_group_socket_boundary"])
    n = len(ordered)
    for i, v in enumerate(ordered):
        vg.add([v.index], (i + 1) / n, "REPLACE")


def _move_to(obj, coll):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)


def build_placeholder_rig(coll, root_empty):
    arm = bpy.data.armatures.new("RIG_HERO")
    rig = bpy.data.objects.new("RIG_HERO", arm)
    coll.objects.link(rig)
    rig.parent = root_empty
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    chain = [("spine_01", (0, 0, 0.90), (0, 0, 1.05)), ("spine_02", (0, 0, 1.05), (0, 0, 1.20)),
             ("spine_03", (0, 0, 1.20), (0, 0, 1.35)), ("neck", (0, 0, 1.35), (0, 0, 1.42)), ("head", (0, 0, 1.42), (0, 0, 1.62))]
    bones = {}
    for name, head, tail in chain:
        b = arm.edit_bones.new(name)
        b.head, b.tail = head, tail
        bones[name] = b
    for child, parent in (("spine_02", "spine_01"), ("spine_03", "spine_02"), ("neck", "spine_03"), ("head", "neck")):
        bones[child].parent = bones[parent]
        bones[child].use_connect = True
    for name, tail in (("shoulder_l", (0.18, 0, 1.33)), ("shoulder_r", (-0.18, 0, 1.33))):
        b = arm.edit_bones.new(name)
        b.head, b.tail = (0, 0, 1.33), tail
        b.parent = bones["spine_03"]
        bones[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = None
    # Placeholder spine sway so the Alembic proxies carry real per-frame samples (check_alembic.py).
    sp = rig.pose.bones["spine_01"]
    sp.rotation_mode = "XYZ"
    f0, f1 = bpy.context.scene.frame_start, bpy.context.scene.frame_end
    for frame, roll in ((f0, 0.0), ((f0 + f1) // 2, 0.08), (f1, -0.05)):
        sp.rotation_euler = (roll, 0.0, 0.0)
        sp.keyframe_insert(data_path="rotation_euler", frame=frame)
    # Placeholder head-turn animation on the neck so socket samples vary per frame.
    pb = rig.pose.bones["neck"]
    pb.rotation_mode = "XYZ"
    for frame, yaw in ((f0, 0.0), ((f0 + f1) // 2, 0.35), (f1, -0.2)):
        pb.rotation_euler = (0.0, yaw, 0.0)
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)
    # Leave the pose at the first frame: everything parented to a bone below takes its rest
    # relation from the pose current at parenting time, so a pose left at the last key would
    # bake a spurious offset into every child (found on the first export: 0.2 rad at f1001).
    bpy.context.scene.frame_set(f0)
    bpy.context.view_layer.update()
    return rig


def build_face_control(coll, rig, shot):
    """FACE_CTRL: one float custom property per channel_map.json channel, keyed through the
    state windows of state_map.json with simple ramps — enough to exercise the exporter and the
    range checks. The animator's burst replaces the keys, never the property names."""
    cmap = json.loads((ROOT / "slice" / "channel_map.json").read_text())
    smap = json.loads((ROOT / "slice" / "state_map.json").read_text())
    ctrl = bpy.data.objects.new("FACE_CTRL", None)
    ctrl.empty_display_type = "CIRCLE"
    ctrl.empty_display_size = 0.08
    coll.objects.link(ctrl)
    ctrl.parent = rig
    ctrl.parent_type = "BONE"
    ctrl.parent_bone = "head"
    for ch in cmap["channels"]:
        name = ch["channel"]
        ctrl[name] = 0.0
        ui = ctrl.id_properties_ui(name)
        # SOFT limits only. Hard min/max on an ID property clamp animated values before the
        # exporter can see them — a silent clamp (CLAUDE.md §6). An over-range key must reach
        # export_shot.py and stop the export.
        ui.update(soft_min=float(ch["output_range"][0]), soft_max=float(ch["output_range"][1]), description=ch["semantic"])
    ramps = {  # state → channels driven to a peak in the middle of the window
        "gaze_shift": {"gaze_yaw": 0.5}, "blink": {"blink_l": 1.0, "blink_r": 1.0},
        "smile": {"mouth_corner_l": 0.8, "mouth_corner_r": 0.8, "cheek_raise_l": 0.5, "cheek_raise_r": 0.5},
        "open_mouth": {"jaw_open": 0.7, "brow_inner_l": 0.6, "brow_inner_r": 0.6},
        "laughter": {"jaw_open": 0.9, "mouth_corner_l": 1.0, "mouth_corner_r": 1.0, "squint_l": 0.7, "squint_r": 0.7},
        "three_quarter": {"gaze_yaw": -0.3}, "head_turn": {"gaze_yaw": -0.6}, "profile": {"mouth_corner_l": 0.7, "mouth_corner_r": 0.7},
        "profile_strong_emotion": {"jaw_open": 0.9, "mouth_corner_l": 1.0, "mouth_corner_r": 1.0},
        "sadness": {"brow_inner_l": 0.8, "brow_inner_r": 0.8, "mouth_corner_l": -0.7, "mouth_corner_r": -0.7},
        "fear": {"brow_inner_l": 1.0, "brow_inner_r": 1.0, "lid_aperture_l": 0.9, "lid_aperture_r": 0.9, "jaw_open": 0.5},
        "hand_over_face": {"lid_aperture_l": -0.6, "lid_aperture_r": -0.6}, "fast_movement": {"brow_outer_l": 0.5, "brow_outer_r": 0.5},
    }
    for w in smap["windows"]:
        if w["shot_id"] != shot or w["state"] not in ramps:
            continue
        for start, end in w["frames"]:
            mid = (start + end) // 2
            for name, peak in ramps[w["state"]].items():
                for frame, value in ((start, 0.0), (mid, peak), (end, 0.0)):
                    ctrl[name] = value
                    ctrl.keyframe_insert(data_path=f'["{name}"]', frame=frame)
    for ch in cmap["channels"]:
        ctrl[ch["channel"]] = 0.0
    return ctrl


def build(scene, shot):
    conv_shot = CONV["shots"][shot]
    scene.name = "SLICE"
    scene["slice_template_version"] = 1
    scene["experiment_id"] = CONV["experiment_id"]
    scene["shot_id"] = shot

    # Units, time, frames (ADR-0002 D6).
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = float(CONV["units"]["scene_unit_scale"])
    scene.render.fps = CONV["fps"]
    scene.render.fps_base = 1.0
    scene.frame_start = conv_shot["frame_range"]["start"]
    scene.frame_end = conv_shot["frame_range"]["end"]
    scene.frame_current = scene.frame_start

    # Render engine and device: Cycles; GPU via Metal when available, recorded either way.
    scene.render.engine = "CYCLES"
    cprefs = bpy.context.preferences.addons["cycles"].preferences
    device_used = "CPU"
    try:
        cprefs.compute_device_type = "METAL"
        cprefs.get_devices()
        for d in cprefs.devices:
            d.use = d.type in ("METAL", "CPU")
        if any(d.type == "METAL" and d.use for d in cprefs.devices):
            scene.cycles.device = "GPU"
            device_used = "METAL"
    except Exception as e:  # noqa: BLE001 — recorded, never silent
        scene.cycles.device = "CPU"
        print(f"TEMPLATE_NOTE: Metal unavailable ({e}); CPU device set")
    scene["render_device"] = device_used

    # Resolution: video profile (still profile is set by render_passes.py per still frame).
    rx, ry = CONV["render_profiles"]["video"]["resolution"]
    scene.render.resolution_x, scene.render.resolution_y = rx, ry
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True  # premultiplied RGBA on beauty layers
    scene.render.use_border = False

    # Sampling: explicit and deterministic (proposal §8 risk 9). Values PROVISIONAL.
    scene.cycles.samples = 64
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    scene.cycles.use_denoising = False  # denoiser pinned separately once determinism is measured
    scene.cycles.max_bounces = 4

    # Motion blur (video profile). Vector pass needs blur OFF — render_passes.py renders L_DATA
    # in a second invocation with blur off; the template stores the video-profile intent.
    scene.render.use_motion_blur = True
    shutter_frames = CONV["render_profiles"]["video"]["shutter_angle_deg"] / 360.0
    scene.render.motion_blur_shutter = shutter_frames
    pos_target = {"CENTRED": "CENTER", "START": "START", "END": "END"}[CONV["render_profiles"]["video"]["shutter_position"]]
    if hasattr(scene.render, "motion_blur_position"):
        scene.render.motion_blur_position = pos_target
        scene["shutter_position_api"] = "scene.render.motion_blur_position"
    else:
        scene.cycles.motion_blur_position = pos_target
        scene["shutter_position_api"] = "scene.cycles.motion_blur_position"

    # Output: multilayer EXR, half beauty; data-pass depth is verified on the rendered file, not
    # assumed (README, "verified on the pinned version").
    img = scene.render.image_settings
    # Blender 5.x: multilayer EXR is a media type, and setting it selects the format itself.
    # Verified on 5.2.1 LTS: setting file_format directly is rejected until media_type is set.
    if hasattr(img, "media_type"):
        img.media_type = "MULTI_LAYER_IMAGE"
        if img.file_format != "OPEN_EXR_MULTILAYER":
            fail(f"media_type MULTI_LAYER_IMAGE gave file_format {img.file_format}")
    else:
        img.file_format = "OPEN_EXR_MULTILAYER"
    img.color_depth = "16"
    img.exr_codec = "ZIP"
    img.color_management = "FOLLOW_SCENE"
    scene.render.filepath = "//renders/" + shot + "/"
    scene.render.use_file_extension = True
    scene.render.use_overwrite = True
    scene.render.use_placeholder = False

    # Collections.
    root = scene.collection
    colls = {name: new_collection(name, root) for name in COLLECTIONS}

    # Materials.
    mats = {
        "HERO_SKIN_HEAD": new_material("HERO_SKIN_HEAD", (0.80, 0.55, 0.45)),
        "HERO_SKIN_BODY": new_material("HERO_SKIN_BODY", (0.80, 0.55, 0.45)),
        "HERO_CLOTH_01": new_material("HERO_CLOTH_01", (0.20, 0.35, 0.70)),
        "HERO_HAIR": new_material("HERO_HAIR", (0.15, 0.10, 0.06)),
    }
    for name in MATERIALS:
        if name not in mats:
            fail(f"material {name} in conventions but not built")

    # Socket space root (proposal §3) at the character's rest frame.
    root_empty = bpy.data.objects.new("SOCKET_SPACE_ROOT", None)
    root_empty.empty_display_type = "ARROWS"
    colls["C_BODY"].objects.link(root_empty)

    # PLACEHOLDER rig: the bones the exporters read (spine[], shoulder_l/r, neck, head). The
    # rigger's armature replaces it; bone names are the contract (conventions.json → bones).
    rig = build_placeholder_rig(colls["C_BODY"], root_empty)

    # Socket empty, bone-parented to the HEAD bone (conventions → scene_naming.socket_parent_bone):
    # its base is the boundary ring, and the socket must carry the whole head pose.
    socket = bpy.data.objects.new("SOCKET_HEAD", None)
    socket.empty_display_type = "ARROWS"
    socket.empty_display_size = 0.05
    colls["C_BODY"].objects.link(socket)
    socket.parent = rig
    socket.parent_type = "BONE"
    socket.parent_bone = CONV["scene_naming"]["socket_parent_bone"]
    bpy.context.view_layer.update()
    socket.matrix_world = Matrix.Translation((0.0, 0.0, 1.42))  # Blender Z-up → socket-space y = 1.42 m
    bpy.context.view_layer.update()

    # Proxies (pass 11) in their own sub-collection: exported to Alembic, never rendered.
    proxies = new_collection("C_PROXIES", colls["C_BODY"])
    neck_proxy = _primitive("cylinder", "NECK_PROXY", radius=0.11, depth=0.10, location=(0.0, 0.0, 1.37), vertices=24)
    coll_proxy = _primitive("cube", "COLLISION_PROXY", size=1.0, location=(0.0, 0.0, 1.15))
    coll_proxy.scale = (0.26, 0.14, 0.18)
    for o, bone in ((neck_proxy, "spine_03"), (coll_proxy, "spine_03")):
        _move_to(o, proxies)
        o.hide_render = True
        o.parent = rig
        o.parent_type = "BONE"
        o.parent_bone = bone
        mw = o.matrix_world.copy()
        bpy.context.view_layer.update()
        o.matrix_world = mw
    bpy.context.view_layer.update()

    # Face control (pass 12): one custom property per channel, keyed through the state windows.
    build_face_control(colls["C_BODY"], rig, shot)

    # PLACEHOLDER geometry — one object per collection so every view layer renders something.
    # The neck's radius and the ring height are the head sphere's own ring (ring 18 of 24 at
    # polar angle 135°: r = 0.14·sin 45°, z = 1.51 − 0.14·cos 45°), so the weld below moves no
    # vertex and the seam has no flare — a flared collar seen edge-on from the camera filled the
    # seam band with fractional-coverage pixels (measured 2026-09-15: inside-band@5e-2 0.890).
    neck_r = HEAD_RADIUS * math.sin(math.radians(45))
    ring_z = HEAD_CENTRE_Z - HEAD_RADIUS * math.cos(math.radians(45))
    body_bottom = 0.10
    bpy.ops.mesh.primitive_cylinder_add(radius=neck_r, depth=ring_z - body_bottom, location=(0.0, 0.0, (ring_z + body_bottom) / 2), vertices=48)
    body = bpy.context.active_object
    body.name = "PLACEHOLDER_BODY"
    # A body asset ends at its boundary ring with an open edge — no cap inside the neck. The
    # cylinder's top n-gon would be coplanar with the head's ring and resolve differently in
    # L_HEAD (body held out) and L_FULL, putting error into the seam band for no reason.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(body.data)
    top = [f for f in bm.faces if len(f.verts) > 4 and f.calc_center_median().z > 0.6]
    if len(top) != 1:
        fail(f"placeholder body: expected one top cap, found {len(top)}")
    bmesh.ops.delete(bm, geom=top, context="FACES_ONLY")
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    body.data.materials.append(mats["HERO_SKIN_BODY"])
    body.data.materials.append(mats["HERO_CLOTH_01"])
    half_depth = (ring_z - body_bottom) / 2
    for poly in body.data.polygons:  # top 20 cm (local coordinates) = skin (neck), rest = cloth
        poly.material_index = 0 if poly.center.z > half_depth - 0.20 else 1
    # SOCKET_BOUNDARY ring on the body: the cylinder's top ring, weight encodes the ORDER around
    # the ring (proposal §3: matched count and order on head and body; the exporter checks both).
    _tag_ring(body, [v for v in body.data.vertices if v.co.z > 0.0 and abs((v.co.x ** 2 + v.co.y ** 2) ** 0.5 - neck_r) < 1e-4])
    for c in body.users_collection:
        c.objects.unlink(body)
    colls["C_BODY"].objects.link(body)
    # The body belongs to the character: parented to the rig (a real body is skinned to it), so
    # it follows SOCKET_SPACE_ROOT wherever the root is placed.
    body.parent = rig
    body.matrix_parent_inverse = rig.matrix_world.inverted()

    bpy.ops.mesh.primitive_uv_sphere_add(radius=HEAD_RADIUS, location=(0.0, 0.0, HEAD_CENTRE_Z), segments=48, ring_count=24)
    head = bpy.context.active_object
    head.name = "PLACEHOLDER_HEAD"
    head.data.materials.append(mats["HERO_SKIN_HEAD"])
    # SOCKET_BOUNDARY ring on the head placeholder: its lowest full ring (48 vertices, the same
    # count as the body ring) is WELDED onto the body's ring, vertex for vertex in angular order,
    # so the two rings coincide at rest exactly as a real asset's do (proposal §3).
    # A head asset ends at its boundary ring — nothing of it sits inside the body. The sphere's
    # rings below the body ring's height are deleted first (they would be held out by C_BODY in
    # L_HEAD and make HEAD_HOLDOUT differ from the head's own silhouette, which the D7 round-trip
    # compares against), then the lowest remaining ring is welded onto the body ring.
    body_ring_world = _ring_world_points(body)
    body_ring_z = sum(p.z for p in body_ring_world) / len(body_ring_world)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(head.data)
    below = [v for v in bm.verts if (head.matrix_world @ v.co).z < body_ring_z - 1e-6]
    bmesh.ops.delete(bm, geom=below, context="VERTS")
    bm.to_mesh(head.data)
    bm.free()
    head.data.update()
    ring_z = min(v.co.z for v in head.data.vertices)
    head_ring = [v for v in head.data.vertices if abs(v.co.z - ring_z) < 1e-5]
    if len(head_ring) != len(body_ring_world):
        fail(f"placeholder rings differ in count: head {len(head_ring)} body {len(body_ring_world)}")
    head_inv = head.matrix_world.inverted()
    for v, wp in zip(_sorted_by_angle(head_ring), body_ring_world):
        v.co = head_inv @ wp
    head.data.update()
    _tag_ring(head, head_ring)
    for c in head.users_collection:
        c.objects.unlink(head)
    colls["C_HEAD"].objects.link(head)
    head.parent = socket
    head.matrix_parent_inverse = socket.matrix_world.inverted()
    set_head_shadow_caster_only(head)
    bpy.context.view_layer.update()

    hair_data = bpy.data.hair_curves.new("PLACEHOLDER_HAIR")
    hair = bpy.data.objects.new("PLACEHOLDER_HAIR", hair_data)
    hair_data.materials.append(mats["HERO_HAIR"])
    colls["C_HAIR"].objects.link(hair)
    hair.parent = socket
    set_head_shadow_caster_only(hair)

    bpy.ops.mesh.primitive_cube_add(size=0.10, location=(0.12, -0.16, 1.50))
    hand = bpy.context.active_object
    hand.name = "PLACEHOLDER_HAND_FG"
    hand.data.materials.append(mats["HERO_SKIN_BODY"])
    for c in hand.users_collection:
        c.objects.unlink(hand)
    colls["C_HAND_FG"].objects.link(hand)
    hand.parent = rig  # the hero's own hand travels with the character
    hand.matrix_parent_inverse = rig.matrix_world.inverted()

    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "PLACEHOLDER_ENV_FLOOR"
    for c in floor.users_collection:
        c.objects.unlink(floor)
    colls["C_ENV"].objects.link(floor)
    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 2.5, 3.0), rotation=(1.5707963, 0.0, 0.0))
    wall = bpy.context.active_object
    wall.name = "PLACEHOLDER_ENV_WALL"
    for c in wall.users_collection:
        c.objects.unlink(wall)
    colls["C_ENV"].objects.link(wall)

    key_data = bpy.data.lights.new("KEY_001", "AREA")
    key_data.energy = 400.0
    key_data.size = 1.0
    key = bpy.data.objects.new("KEY_001", key_data)
    key.location = (1.5, -2.0, 2.6)
    key.rotation_euler = (0.9, 0.0, 0.6)
    colls["C_LIGHTS"].objects.link(key)

    cam_data = bpy.data.cameras.new("CAM_001")
    cam_data.lens = 50.0
    cam_data.sensor_width = 36.0
    cam_data.sensor_height = 24.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.clip_start = 0.1
    cam_data.clip_end = 100.0
    cam_data.dof.use_dof = False
    cam = bpy.data.objects.new("CAM_001", cam_data)
    cam.location = (0.0, -2.2, 1.45)
    cam.rotation_euler = (1.5707963, 0.0, 0.0)
    root.objects.link(cam)
    scene.camera = cam
    # Placeholder camera move so the extrinsics are not constant across the shot.
    cam.keyframe_insert(data_path="location", frame=scene.frame_start)
    cam.location = (0.05, -2.05, 1.47)
    cam.keyframe_insert(data_path="location", frame=scene.frame_end)
    cam.location = (0.0, -2.2, 1.45)

    # View layers.
    scene.view_layers[0].name = VIEW_LAYERS[0]
    for name in VIEW_LAYERS[1:]:
        scene.view_layers.new(name)
    for vl in scene.view_layers:
        rules = LAYER_RULES[vl.name]
        for coll_name in COLLECTIONS:
            lc = vl.layer_collection.children[coll_name]
            lc.exclude = coll_name in rules.get("exclude", [])
            lc.holdout = coll_name in rules.get("holdout", [])
            lc.indirect_only = coll_name in rules.get("indirect_only", [])
        passes = LAYER_PASSES[vl.name]
        vl.use_pass_combined = passes.get("combined", False)
        vl.use_pass_z = passes.get("z", False)
        vl.use_pass_vector = passes.get("vector", False)
        vl.use_pass_cryptomatte_object = passes.get("cryptomatte_object", False)
        vl.use_pass_cryptomatte_material = passes.get("cryptomatte_material", False)
        vl.use_pass_cryptomatte_asset = False
        vl.pass_cryptomatte_depth = 6
        vl.use_pass_normal = False  # not in the base set (ADR-0002 D5)
        vl.use = True

    # Colour management: the OCIO config comes from $OCIO (pinned in toolchain.lock.json).
    # Under the ACES v4.0.0 studio config (verified on 5.2.1 LTS) the scene-linear space is
    # ACEScg, the SDR video view is 'ACES 2.0 - SDR 100 nits (Rec.709)' and the display is
    # 'sRGB - Display'. Set explicitly when available; record what is active either way. EXR
    # output is scene-linear regardless (FOLLOW_SCENE), so the view is for previews and QC.
    import os
    scene["ocio_config_env"] = os.environ.get("OCIO", "")
    for view in ("ACES 2.0 - SDR 100 nits (Rec.709)",):
        try:
            scene.view_settings.view_transform = view
            break
        except TypeError:
            print(f"TEMPLATE_NOTE: view '{view}' not in the active OCIO config; keeping {scene.view_settings.view_transform!r}")
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene["view_transform"] = scene.view_settings.view_transform
    scene["display_device"] = scene.display_settings.display_device
    scene["scene_linear"] = getattr(scene.sequencer_colorspace_settings, "name", "UNKNOWN")


def pose_root(scene, pose):
    """Move SOCKET_SPACE_ROOT (and with it the rig, socket, head, proxies) after the build. The
    scene records the pose so a check can tell a posed test template from the production one."""
    import math
    x, y, z, yaw = pose
    root = bpy.data.objects["SOCKET_SPACE_ROOT"]
    scene.frame_set(scene.frame_start)
    root.matrix_world = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
    scene["root_pose_test"] = [x, y, z, yaw]
    bpy.context.view_layer.update()


def main():
    args = parse_args()
    if args.shot not in CONV["shots"]:
        fail(f"unknown shot {args.shot}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    build(scene, args.shot)
    if args.root_pose is not None:
        pose_root(scene, args.root_pose)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print(f"TEMPLATE_OK {out} device={scene['render_device']} blender={bpy.app.version_string}")


if __name__ == "__main__":
    main()
