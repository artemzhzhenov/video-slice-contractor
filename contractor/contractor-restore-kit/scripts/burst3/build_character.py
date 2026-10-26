"""build_character.py — burst 1 deliverable: replace the template's PLACEHOLDER_* geometry and
placeholder rig with the hero character (girl, 7–9 presentation age), default head, hair and
RIG_HERO, keeping FACE_CTRL and SOCKET_HEAD (re-parented, never recreated).

    blender -b template.blend --python-exit-code 2 -P deliverables/scripts/build_character.py -- --out deliverables/character_v01.blend

Blender 5.2.1 LTS. Requires the MPFB2 extension (v2.0.17 / 80919fa, CC0 assets) installed as
`bl_ext.<repo>.mpfb`; the script finds it under any extension repo and stops if the version
differs from --mpfb-version. No randomness anywhere: two runs on the same template give the
same slice/blend_content_hash.py hash.

What is built (all names are the contract, see contractor/burst-1/TASK.md):
  C_BODY   HERO_BODY (skinned, one Armature modifier, SOCKET_BOUNDARY ring weighted 100 % to
           `head`), RIG_HERO (MakeHuman default skeleton, contract bone names), proxies
           NECK_PROXY / COLLISION_PROXY re-fitted and re-parented, FACE_CTRL and SOCKET_HEAD
           re-parented to `head`.
  C_HAND_FG HERO_HAND_FG — the anatomical-left hand split off the body at the wrist, same
           weights, so the seam stays welded.
  C_HEAD   HERO_HEAD (shell, SOCKET_BOUNDARY ring, 26-channel face shape keys driven from
           FACE_CTRL), HERO_EYE_L/R (gaze drivers), HERO_TEETH_UPPER/LOWER, HERO_TONGUE,
           brows as a HERO_BROW material region of the shell — all children of SOCKET_HEAD, unskinned, shadow-caster-only.
  C_HAIR   HERO_HAIR — built by hair_on_head.py from the head shell (bob + strands, or the child's class), opaque.
"""
import argparse
import importlib
import json
import math
import os
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hair_on_head                                        # noqa: E402  (Q61)
from hair_on_head import (BROW_ABOVE_EYE_M, BROW_TOP_M, BROW_X_MAX_M, BROW_X_MIN_M, DRESS_COLLAR_ABOVE_CLAVICLE_M)  # noqa: E402

# --------------------------------------------------------------------------------------------
# Tunables. Every number here is a design decision recorded once; nothing is derived from time,
# randomness or the machine.
# --------------------------------------------------------------------------------------------
MACRO = {"gender": 0.0, "age": 0.19, "muscle": 0.5, "weight": 0.5, "height": 0.6, "proportions": 0.5,
         "cupsize": 0.0, "firmness": 0.5, "race": {"asian": 0.33, "caucasian": 0.33, "african": 0.33}}
STYLE_TARGETS = [  # (folder, target, weight) — MakeHuman modelling targets for a mild cartoon read
    ("head", "head-round", 0.35), ("head", "head-scale-vert-incr", 0.15),
    ("eyes", "l-eye-scale-incr", 0.55), ("eyes", "r-eye-scale-incr", 0.55),
    ("eyes", "l-eye-height2-incr", 0.25), ("eyes", "r-eye-height2-incr", 0.25),
    ("cheek", "l-cheek-volume-incr", 0.35), ("cheek", "r-cheek-volume-incr", 0.35),
    ("nose", "nose-scale-vert-decr", 0.30), ("nose", "nose-volume-decr", 0.30),
    ("chin", "chin-height-decr", 0.20), ("mouth", "mouth-scale-horiz-decr", 0.10),
]
EXPRESSION_SET = "caucasian"     # the unit targets exist per race set; one set, recorded here
EXPRESSION_UNITS = ["eye-left-closure", "eye-right-closure", "eye-left-opened-up", "eye-right-opened-up",
                    "eye-left-slit", "eye-right-slit", "eyebrows-left-down", "eyebrows-right-down",
                    "eyebrows-left-extern-up", "eyebrows-right-extern-up", "eyebrows-left-inner-up",
                    "eyebrows-right-inner-up", "mouth-compression", "mouth-corner-puller", "mouth-depression",
                    "mouth-elevation", "mouth-open", "mouth-parling", "mouth-protusion", "mouth-pursing",
                    "mouth-retraction", "nose-compression", "nose-left-dilatation", "nose-right-dilatation",
                    "nose-left-elevation", "nose-right-elevation", "mouth-upward-retraction"]
# channel → list of (unit, side, factor). side: None = whole, "l"/"r" = anatomical side mask.
# Channels with a −1..1 range get a "_neg" list for the negative direction.
CHANNEL_MAP = {
    "brow_inner_l":      ([("eyebrows-left-inner-up", None, 1.0)],   [("eyebrows-left-down", None, 0.8)]),
    "brow_inner_r":      ([("eyebrows-right-inner-up", None, 1.0)],  [("eyebrows-right-down", None, 0.8)]),
    "brow_outer_l":      ([("eyebrows-left-extern-up", None, 1.0)],  [("eyebrows-left-down", None, 0.6)]),
    "brow_outer_r":      ([("eyebrows-right-extern-up", None, 1.0)], [("eyebrows-right-down", None, 0.6)]),
    "lid_aperture_l":    ("LID", None),                              # see build lids: combination_rules
    "lid_aperture_r":    ("LID", None),
    "squint_l":          ([("eye-left-slit", None, 1.0)], None),
    "squint_r":          ([("eye-right-slit", None, 1.0)], None),
    "cheek_raise_l":     ([("mouth-upward-retraction", "l", 0.7), ("eye-left-slit", None, 0.35)], None),
    "cheek_raise_r":     ([("mouth-upward-retraction", "r", 0.7), ("eye-right-slit", None, 0.35)], None),
    "nose_wrinkle":      ([("nose-left-elevation", None, 1.0), ("nose-right-elevation", None, 1.0), ("nose-compression", None, 0.5)], None),
    "nostril_flare":     ([("nose-left-dilatation", None, 1.0), ("nose-right-dilatation", None, 1.0)], [("nose-compression", None, 1.0)]),
    "mouth_corner_l":    ([("mouth-corner-puller", "l", 1.0)],       [("mouth-depression", "l", 1.0)]),
    "mouth_corner_r":    ([("mouth-corner-puller", "r", 1.0)],       [("mouth-depression", "r", 1.0)]),
    "mouth_width":       ([("mouth-retraction", None, 1.0)],         [("mouth-pursing", None, 0.6)]),
    "jaw_open":          ([("mouth-open", None, 0.85)], None),
    "jaw_lateral":       ("JAW_LATERAL", None),                      # procedural, see make_jaw_lateral
    "lip_funnel":        ([("mouth-protusion", None, 0.7), ("mouth-parling", None, 0.5)], None),
    "lip_purse":         ([("mouth-pursing", None, 1.0)], None),
    "lip_press":         ([("mouth-compression", None, 1.0)],        [("mouth-parling", None, 0.5)]),
    "upper_lip_raise_l": ([("mouth-elevation", "l", 1.0)], None),
    "upper_lip_raise_r": ([("mouth-elevation", "r", 1.0)], None),
    "blink_l":           ("LID", None),
    "blink_r":           ("LID", None),
    # gaze_yaw / gaze_pitch drive the eye objects' rotation (see build_eyes)
}
GAZE_YAW_DEG, GAZE_PITCH_DEG = 30.0, 20.0
LID_EYE_CLEARANCE_M = 0.0006
LID_COLUMN_HALF_WIDTH_M = 0.004
LID_OVERLAP_M = 0.0008
LID_GAIN_MAX = 2.2
EYE_SEGMENTS = 32
EYE_PUPIL_DEG, EYE_IRIS_DEG = 10.0, 25.0
EYE_LATITUDES_DEG = [0.0, 5.0, 10.0, 17.0, 25.0, 35.0, 50.0, 65.0, 80.0, 95.0, 110.0, 130.0, 150.0, 170.0]
JAW_LATERAL_M = 0.012
SIDE_BLEND_M = 0.008         # half-width of the left/right mask blend across the midline
BROW_RINGS, BROW_SIDES = 9, 8
BROW_THICK_M = 0.0032
BROW_HEIGHT_M = 0.0048
BROW_WINDOW_M = 0.006
BROW_ARCH_M = 0.009
BROW_LIFT_M = 0.0015
                                                            # where the side hair actually covers the skin   # (start yaw°, end z (filled below), width factor)
                                         # the strand and is hidden by the side hair in front of it
NECK_BLEND_ROWS = 4
# burst 3 — curly voluminous hair (hair class "curly_voluminous")
# burst 3 — straight hair classes and bangs
GLASSES_LENS_RADIUS_M = 0.018
GLASSES_LENS_UP_M = 0.003
GLASSES_VERTEX_M = 0.012                 # the lens plane this far in front of the eyes' front points (spec 10-14 mm)
GLASSES_VERTEX_MAX_M = 0.014             # ... moved forward up to this if a rim comes too close to the skin
GLASSES_RIM_CLEAR_M = 0.003              # a rim's tube surface at least this far off the skin at rest
GLASSES_LENS_RADIUS_MIN_M = 0.015        # ... then the lens made smaller down to this
GLASSES_BRIDGE_GAP_M = 0.001             # the bridge's tube surface off the nose at the nearest point (spec 0-2 mm)
GLASSES_TEMPLE_CLEAR_M = 0.002           # the temples' tube surface off the skin (spec: skin + ~2 mm)
GLASSES_BROW_CLEAR_M = 0.0015            # a rim's tube surface off the brows at their lowest (every brow channel down)
GLASSES_RIM_TUBE_R_M = 0.0016
GLASSES_RIM_SEGS = 28
        # back strands end ~1 cm above the back neckline
NECK_BLEND_HEAD_WEIGHT = [0.78, 0.52, 0.28, 0.10]   # head weight on rows 1..4 below the ring; ring itself = 1.0
ARMATURE_PRESERVE_VOLUME = False
DRESS_RINGS, DRESS_SEGMENTS = 30, 48
DRESS_OFFSET_M = 0.007
DRESS_FLARE_M = 0.05
DRESS_HEM_ABOVE_KNEE_M = 0.04
SLEEVE_RINGS, SLEEVE_SEGMENTS = 8, 24
SLEEVE_OFFSET_M = 0.007
SLEEVE_START_M = -0.06               # the sleeve starts inside the dress shoulder, before the joint
SLEEVE_SHOULDER_FLARE_TO_M = 0.0
SLEEVE_SHOULDER_FLARE = 0.0
ARM_REMOVE_FROM_M = 0.045            # the shoulder ball keeps its skin under the dress
DRESS_SHOULDER_BALL_M = 0.035        # upper-arm vertices this close to the joint shape the dress top
SKIRT_BIN_WIDTH = 4.0
YOKE_RINGS = 6                       # rings from the dress rim to the collar line on the neck (Д1)
YOKE_RISE_FRONT_M = 0.020
YOKE_RISE_BACK_M = 0.042
YOKE_RISE_SIDE_M = 0.030
COLLAR_PENETRATION_FRONT_M = 0.005   # collar line inside the neck skin (variant В, Д1): measured
COLLAR_PENETRATION_BACK_M = 0.009    # at the max head turn the nape skin swings away most, so deeper there
TUCK_M = 0.011                       # v04 seam tuck: covers the 7.5 mm the neck skin swings + the 2 mm margin + slack
SEAM_TUCK_RAMP_MM = 2.0
SEAM_BAND_RADIUS_M = 0.08            # same band radius as slice/conventions.json → seam_margin
COLLAR_HEAD_NECK_M = 0.012           # head-shell vertices this far above the seam count as neck skin
YOKE_BAND_M = 0.012
YOKE_EASE = 1.4
BODY_REMOVE_MARGIN_M = 0.03                    # set after the neck-turn preview (Q17)
NECK_RING_FRACTION = 0.70    # where between shoulder top (clavicle) and chin bottom the ring loop is sought
BONE_RENAME = {"spine05": "spine_01", "spine04": "spine_02", "spine03": "spine_03", "spine02": "spine_04",
               "spine01": "spine_05", "neck01": "neck", "head": "head", "clavicle.L": "shoulder_l", "clavicle.R": "shoulder_r"}
BONES_MERGE_INTO_NECK = {"neck02", "neck03"}
FACE_BONE_PREFIXES = ("jaw", "oris", "levator", "oculi", "orbicularis", "risorius", "temporalis", "special", "tongue", "eye.")
CLOTH_BONES = ("spine", "root", "clavicle", "shoulder", "upperarm", "breast", "pelvis", "upperleg", "lowerleg")
SHOE_BONES = ("foot", "toe")
HAND_BONES_L = ("wrist.L", "finger", "metacarpal")
RIG_TEST_SWAY = [(0, 0.0), (0.5, 0.08), (1.0, -0.05)]        # spine_01 roll, fraction of shot
RIG_TEST_YAW = [(0, 0.0), (0.5, 0.35), (1.0, -0.2)]          # neck yaw, fraction of shot


def fail(msg):
    print(f"BUILD_ERROR {msg}")
    sys.exit(2)


# --------------------------------------------------------------------------------------------
# MPFB
# --------------------------------------------------------------------------------------------
def enable_mpfb(want_version):
    import addon_utils
    names = [m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb") or m.__name__ == "mpfb"]
    if not names:
        fail("MPFB extension not installed (looked for bl_ext.<repo>.mpfb)")
    name = sorted(names)[0]
    mod = addon_utils.enable(name, default_set=True, persistent=True) or importlib.import_module(name)
    manifest = Path(mod.__file__).parent / "blender_manifest.toml"
    version = None
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            if line.strip().startswith("version"):
                version = line.split("=", 1)[1].strip().strip('"')
    if version != want_version:
        fail(f"MPFB version {version!r} at {name}, expected {want_version} (LICENSES.md)")
    return name, version


def dyn(pkg, key):
    for m in list(sys.modules):
        if m.endswith(pkg):
            return getattr(importlib.import_module(m), key)
    raise ImportError(pkg)


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------
def link_only(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def mat_get(name, color, **bsdf):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        p = m.node_tree.nodes["Principled BSDF"]
        p.inputs["Base Color"].default_value = (*color, 1.0)
        for k, v in bsdf.items():
            p.inputs[k].default_value = v
    return m


def shadow_caster_only(obj):
    obj.visible_camera = True
    obj.visible_shadow = True
    obj.visible_diffuse = False
    obj.visible_glossy = False
    obj.visible_transmission = False
    obj.visible_volume_scatter = False


def mesh_from_faces(name, src_co, faces, extra_keys=None):
    """New mesh object from a face subset of a vertex array. Returns (object, old→new index map)."""
    used = sorted({i for f in faces for i in f})
    remap = {old: new for new, old in enumerate(used)}
    me = bpy.data.meshes.new(name)
    me.from_pydata([src_co[i][:] for i in used], [], [[remap[i] for i in f] for f in faces])
    me.validate()
    me.update()
    obj = bpy.data.objects.new(name, me)
    for p in me.polygons:
        p.use_smooth = True
    return obj, remap, used


def add_shape_key(obj, name, deltas_by_old, used, scale=1.0):
    """Shape key from a {old_index: Vector} delta map. Creates Basis on first use."""
    me = obj.data
    if me.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    kb = obj.shape_key_add(name=name, from_mix=False)
    basis = me.shape_keys.key_blocks[0]
    for new, old in enumerate(used):
        d = deltas_by_old.get(old)
        kb.data[new].co = basis.data[new].co + (d * scale if d is not None else Vector())
    kb.slider_min, kb.slider_max = 0.0, 1.0
    return kb


def add_driver(id_block, path, ctrl, channel, expr, index=-1, extra=None):
    """Scripted driver: variable `v` = FACE_CTRL[channel]; `extra` = {name: channel} adds more."""
    fc = id_block.driver_add(path, index) if index >= 0 else id_block.driver_add(path)
    drv = fc.driver
    drv.type = "SCRIPTED"
    for name, ch in [("v", channel)] + sorted((extra or {}).items()):
        var = drv.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "OBJECT"
        var.targets[0].id = ctrl
        var.targets[0].data_path = f'["{ch}"]'
    drv.expression = expr
    return fc


def side_mask(x, side):
    if side is None:
        return 1.0
    t = (x if side == "l" else -x) / SIDE_BLEND_M
    return max(0.0, min(1.0, 0.5 + 0.5 * t))


# --------------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------------
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--mpfb-version", default="2.0.17")
    p.add_argument("--height", type=float, default=1.40, help="character height, metres")
    p.add_argument("--keep-env", action="store_true", help="keep the template's PLACEHOLDER_ENV_* floor and wall (Q16); off by default — "
                   "with them present slice/composite.py fails its precomp reproduction gate (Q23)")
    p.add_argument("--subject", default=None, help="burst 3: a synthetic child's parameter file (subject_NN.json); "
                   "without it the script builds character v04.1 exactly as before")
    args = p.parse_args(argv)
    subj = json.load(open(args.subject)) if args.subject else None

    scene = bpy.data.scenes.get("SLICE") or fail("scene SLICE missing — run on template.blend")
    bpy.context.window.scene = scene
    scene.frame_set(scene.frame_start)
    colls = {n: bpy.data.collections[n] for n in ("C_HEAD", "C_HAIR", "C_BODY", "C_HAND_FG", "C_PROXIES")}
    mats = {n: bpy.data.materials[n] for n in ("HERO_SKIN_HEAD", "HERO_SKIN_BODY", "HERO_CLOTH_01", "HERO_HAIR")}
    ctrl = bpy.data.objects.get("FACE_CTRL") or fail("FACE_CTRL missing")
    socket = bpy.data.objects.get("SOCKET_HEAD") or fail("SOCKET_HEAD missing")
    root = bpy.data.objects.get("SOCKET_SPACE_ROOT") or fail("SOCKET_SPACE_ROOT missing")
    old_rig = bpy.data.objects.get("RIG_HERO")
    ctrl_world = ctrl.matrix_world.copy()

    mpfb_name, mpfb_version = enable_mpfb(args.mpfb_version)
    HumanService = dyn("mpfb.services.humanservice", "HumanService")
    TargetService = dyn("mpfb.services.targetservice", "TargetService")
    ObjectService = dyn("mpfb.services.objectservice", "ObjectService")
    LocationService = dyn("mpfb.services.locationservice", "LocationService")
    targets_root = LocationService.get_mpfb_data("targets")

    # ---- 1. MakeHuman base mesh, child macros, mild cartoon targets, baked ----------------
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children["C_BODY"]
    human = HumanService.create_human(mask_helpers=False, macro_detail_dict=json.loads(json.dumps(MACRO)))
    for folder, target, weight in STYLE_TARGETS:
        TargetService.load_target(human, os.path.join(targets_root, folder, target + ".target.gz"), weight=weight)
    TargetService.bake_targets(human)
    gdef = ObjectService.get_base_mesh_vertex_group_definition()
    groups = {k: set(v) for k, v in gdef.items()}
    me = human.data
    body_idx = groups["body"]
    zs = [me.vertices[i].co.z for i in body_idx]
    height_now = max(zs) - min(zs)
    s = args.height / height_now
    for v in me.vertices:            # uniform scale to the target height, feet at z = 0
        v.co = Vector((v.co.x * s, v.co.y * s, (v.co.z - min(zs)) * s))
    me.update()

    # ---- 2. MakeHuman default skeleton with its weights (163 bones) -------------------------
    mh_rig = HumanService.add_builtin_rig(human, "default")
    bpy.context.view_layer.update()
    mh_bones = {b.name: {"head": b.head_local.copy(), "tail": b.tail_local.copy(), "z": Vector(b.matrix_local.col[2][:3]),
                         "parent": b.parent.name if b.parent else None, "connect": b.use_connect} for b in mh_rig.data.bones}

    # ---- 3. expression unit targets as deltas (adult-scale, so scaled by height ratio) ------
    for unit in EXPRESSION_UNITS:
        TargetService.load_target(human, os.path.join(targets_root, "expression", "units", EXPRESSION_SET, unit + ".target.gz"), weight=0.0, name=unit)
    basis = me.shape_keys.key_blocks[0]
    delta_scale = args.height / 1.66
    units = {}
    for unit in EXPRESSION_UNITS:
        kb = me.shape_keys.key_blocks[unit]
        d = {}
        for i in range(len(me.vertices)):
            dv = kb.data[i].co - basis.data[i].co
            if dv.length > 1e-7:
                d[i] = dv * delta_scale
        units[unit] = d
    co = [v.co.copy() for v in me.vertices]
    n_v = len(co)

    # bone weights per vertex: {vertex: {bone: w}}
    vg_names = {g.index: g.name for g in human.vertex_groups}
    bone_names = set(mh_bones)
    weights = [dict() for _ in range(n_v)]
    for v in me.vertices:
        for g in v.groups:
            nm = vg_names[g.group]
            if nm in bone_names and g.weight > 0.0:
                weights[v.index][nm] = g.weight
    faces_all = [tuple(p.vertices) for p in me.polygons]
    faces_body = [f for f in faces_all if all(i in body_idx for i in f)]

    # ---- 4. neck ring: an existing edge loop between chin and shoulders -----------------------
    jaw_tail = mh_bones["jaw"]["tail"].z
    clav_z = mh_bones["clavicle.L"]["head"].z
    z_target = clav_z + NECK_RING_FRACTION * (jaw_tail - clav_z)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    body_bm_faces = [f for f in bm.faces if all(v.index in body_idx for v in f.verts)]
    # candidate start: front-most body vertex on the midline near z_target with valence 4
    cands = [v for v in bm.verts if v.index in body_idx and abs(v.co.x) < 0.004 and v.co.y < -0.02
             and abs(v.co.z - z_target) < 0.03 and len(v.link_edges) == 4]
    if not cands:
        fail("no valence-4 midline neck vertex near the ring height")
    start = min(cands, key=lambda v: abs(v.co.z - z_target))

    def walk_loop(v0, e0):
        loop, v, e = [v0], v0, e0
        for _ in range(500):
            v = e.other_vert(v)
            if v is v0:
                return loop
            loop.append(v)
            if len(v.link_edges) != 4:
                return None
            faces_e = set(e.link_faces)
            nxt = [x for x in v.link_edges if x is not e and not (set(x.link_faces) & faces_e)]
            if len(nxt) != 1:
                return None
            e = nxt[0]
        return None
    ring = None
    for e0 in start.link_edges:
        if abs(e0.other_vert(start).co.z - start.co.z) > 0.02:
            continue      # not a horizontal edge
        loop = walk_loop(start, e0)
        if loop and 12 <= len(loop) <= 80 and all(abs(v.co.z - start.co.z) < 0.06 for v in loop):
            ring = loop
            break
    if ring is None:
        fail("could not walk a closed horizontal edge loop around the neck")
    ring_idx = [v.index for v in ring]
    ring_set = set(ring_idx)
    ring_edges = {e for v in ring for e in v.link_edges if e.other_vert(v) in ring}
    # flood fill faces above the ring (head side) without crossing ring edges
    seed = max((f for f in body_bm_faces if not any(v in ring for v in f.verts)), key=lambda f: f.calc_center_median().z)
    head_faces_bm, stack, seen = [], [seed], {seed}
    while stack:
        f = stack.pop()
        head_faces_bm.append(f)
        for e in f.edges:
            if e in ring_edges:
                continue
            for g in e.link_faces:
                if g not in seen and all(v.index in body_idx for v in g.verts):
                    seen.add(g)
                    stack.append(g)
    head_faces = [tuple(v.index for v in f.verts) for f in head_faces_bm]
    head_face_set = set(head_faces)
    body_faces = [f for f in faces_body if f not in head_face_set]
    # rows of body vertices below the ring (Q17 gradient): row 1 = neighbours of the ring across
    # body faces, row 2 = their neighbours, ... — topology only, no distances.
    head_bm_set = set(head_faces_bm)
    neck_row, frontier = {}, set(ring)
    for row in range(1, NECK_BLEND_ROWS + 1):
        nxt = set()
        for v in frontier:
            for e in v.link_edges:
                w = e.other_vert(v)
                if w in ring or w.index in neck_row or w.index not in body_idx:
                    continue
                if any(f in head_bm_set for f in e.link_faces):
                    continue
                nxt.add(w)
        for w in nxt:
            neck_row[w.index] = row
        frontier = nxt
    print(f"neck blend rows: {[sum(1 for r in neck_row.values() if r == k) for k in range(1, NECK_BLEND_ROWS + 1)]} vertices")
    bm.free()
    low = min(co[i].z for f in head_faces for i in f)
    if low < min(co[i].z for i in ring_idx) - 1e-6:
        fail("head region reaches below the ring — the loop does not separate the neck")
    ring_c = sum((co[i] for i in ring_idx), Vector()) / len(ring_idx)
    ring_order = sorted(ring_idx, key=lambda i: math.atan2(co[i].y - ring_c.y, co[i].x - ring_c.x))
    ring_weight = {i: (k + 1) / len(ring_order) for k, i in enumerate(ring_order)}
    print(f"ring: {len(ring_idx)} vertices, centre {[round(c, 4) for c in ring_c]}, z span {max(co[i].z for i in ring_idx) - min(co[i].z for i in ring_idx):.4f} m")
    for d in units.values():         # the seam never deforms
        for i in ring_idx:
            d.pop(i, None)

    # ---- 5. RIG_HERO: MakeHuman skeleton copied with contract names --------------------------
    arm = bpy.data.armatures.new("RIG_HERO_arm")
    rig = bpy.data.objects.new("RIG_HERO_new", arm)
    colls["C_BODY"].objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    keep = [n for n in mh_bones if n not in BONES_MERGE_INTO_NECK and not n.startswith(FACE_BONE_PREFIXES)]
    new_name = {n: BONE_RENAME.get(n, n) for n in keep}
    ebs = {}
    for n in keep:
        b = mh_bones[n]
        eb = arm.edit_bones.new(new_name[n])
        eb.head, eb.tail = b["head"].copy(), b["tail"].copy()
        eb.align_roll(b["z"])
        eb.use_deform = True
        ebs[n] = eb
    ebs["neck01"].tail = ring_c.copy()
    ebs["head"].head = ring_c.copy()
    # The exported chain (spine_01..03, neck, head, shoulder_l/r) is made exactly axis-aligned:
    # Blender stores bone matrices in float32 and a tilted bone decomposes with a scale error of
    # ~1e-6, which export_shot.py rejects. Vertical spine/neck/head on the ring axis, shoulders
    # along X — exact in float32. Skinning is unaffected (weights are rest-relative).
    for src_name in ("root", "spine05", "spine04", "spine03", "spine02", "spine01", "neck01", "head"):
        eb = ebs[src_name]
        eb.head = Vector((0.0, ring_c.y, eb.head.z))
        eb.tail = Vector((0.0, ring_c.y, eb.tail.z))
        eb.roll = 0.0
    for src_name in ("clavicle.L", "clavicle.R"):
        eb = ebs[src_name]
        eb.tail = Vector((eb.tail.x, eb.head.y, eb.head.z))
        eb.roll = 0.0
    for n in keep:
        par = mh_bones[n]["parent"]
        while par is not None and par not in ebs:
            par = mh_bones[par]["parent"]
        if par is not None:
            ebs[n].parent = ebs[par]
            ebs[n].use_connect = mh_bones[n]["connect"] and (ebs[n].head - ebs[par].tail).length < 1e-6
    ebs["head"].parent = ebs["neck01"]
    ebs["head"].use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = None
    bone_map = {}          # source bone → target bone for weights
    for n in mh_bones:
        if n in BONES_MERGE_INTO_NECK:
            bone_map[n] = "neck"
        elif n.startswith(FACE_BONE_PREFIXES):
            bone_map[n] = "head"
        else:
            bone_map[n] = new_name[n]
    neck_base_z = mh_bones["neck01"]["head"].z
    eye_c = {sd: sum((co[i] for i in groups[g]), Vector()) / len(groups[g]) for sd, g in (("L", "helper-l-eye"), ("R", "helper-r-eye"))}

    # ---- 6. drop the MakeHuman objects and the template placeholders -------------------------
    old_rig_action = old_rig.animation_data.action if old_rig and old_rig.animation_data else None
    for o in [human, mh_rig] + [o for o in bpy.data.objects if o.name.startswith("PLACEHOLDER_") and not (args.keep_env and o.name.startswith("PLACEHOLDER_ENV"))] + ([old_rig] if old_rig else []):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll_ in (bpy.data.meshes, bpy.data.armatures, bpy.data.hair_curves):
        for d in list(coll_):
            if d.users == 0:
                coll_.remove(d)
    if old_rig_action is not None and old_rig_action.users == 0:
        bpy.data.actions.remove(old_rig_action)
    rig.name = "RIG_HERO"
    arm.name = "RIG_HERO"
    rig.parent = root
    rig.matrix_parent_inverse = root.matrix_world.inverted()

    # ---- 7. body and hand meshes ---------------------------------------------------------------
    def dominant(f):
        acc = {}
        for i in f:
            for bn, w in weights[i].items():
                acc[bn] = acc.get(bn, 0.0) + w
        return max(acc, key=acc.get) if acc else "root"
    hand_faces = [f for f in body_faces if dominant(f).startswith(HAND_BONES_L) and dominant(f).endswith(".L")]
    hand_set = set(hand_faces)
    body_faces = [f for f in body_faces if f not in hand_set]

    neckline_z = clav_z + 0.012                     # collar: just above the shoulder top
    elbow_x = abs(mh_bones["lowerarm01.L"]["head"].x) # short sleeves end at the elbow
    ankle_z = mh_bones["foot.L"]["head"].z + 0.01   # shoes below the ankle

    def region(f):
        pts = [co[i] for i in f]
        if all(p.z < ankle_z for p in pts):
            return 2                                   # shoes
        return 0                                       # skin (the dress is separate geometry, Q20)

    # ---- 7a. dress and sleeves as separate skinned geometry; body removed underneath (Q20/Q21) ----
    import numpy as np
    knee_z = mh_bones["lowerleg01.L"]["head"].z
    hem_z = knee_z + DRESS_HEM_ABOVE_KNEE_M
    collar_z = clav_z + DRESS_COLLAR_ABOVE_CLAVICLE_M
    waist_z = mh_bones["spine03"]["head"].z
    dom_v = {}                                          # dominant bone per body vertex
    for i in range(n_v):
        if weights[i]:
            dom_v[i] = max(weights[i], key=weights[i].get)
    torso_bones = ("spine", "root", "pelvis", "breast", "clavicle", "shoulder01", "upperleg")
    arm_bones = ("upperarm",)
    shoulder_joint = {sd: mh_bones["upperarm01" + sd]["head"] for sd in (".L", ".R")}
    def near_shoulder(i):
        d = dom_v[i]
        return d.startswith(arm_bones) and (co[i] - shoulder_joint[".L" if d.endswith(".L") else ".R"]).length < DRESS_SHOULDER_BALL_M
    torso_v = [i for i in range(n_v) if i in body_idx and i in dom_v and (dom_v[i].startswith(torso_bones) or near_shoulder(i))
               and hem_z - 0.05 <= co[i].z <= collar_z + 0.03 and i not in ring_set and i not in neck_row]
    arm_v = {sd: [i for i in range(n_v) if i in body_idx and i in dom_v and dom_v[i].startswith(arm_bones + ("shoulder01",)) and dom_v[i].endswith(sd)]
             for sd in (".L", ".R")}

    def polar_tube(rings, samples, centre_fn, radius_offset_fn, K, band, frame=None, skirt_below=None):
        """Surface of revolution-like tube: for each ring (parameter t / height) the radius per
        angle bin is the largest sample radius in that bin (+offset), smoothed 1-2-1 along the
        angle and the rings. frame=None: rings are z levels, angle in the XY plane; otherwise
        frame=(origin, axis, u, v) and rings are distances along the axis."""
        S = np.array([co[i][:] for i in samples], dtype=np.float64)
        if frame is None:
            tS, rel = S[:, 2], S[:, :2]
        else:
            o, a, u, v = frame
            rel3 = S - np.array(o)
            tS = rel3 @ np.array(a)
            rel = np.stack([rel3 @ np.array(u), rel3 @ np.array(v)], axis=1)
        out_rings = []
        prev = None
        for t in rings:
            sel = np.abs(tS - t) < band
            if sel.sum() < 4:
                sel = np.abs(tS - t) < band * 2.5
            c = centre_fn(t, rel[sel]) if frame is None else np.zeros(2)
            d = rel[sel] - c
            ang = np.arctan2(d[:, 1], d[:, 0])
            rad = np.hypot(d[:, 0], d[:, 1])
            r = np.zeros(K)
            skirt = skirt_below is not None and t < skirt_below
            win = (2 * math.pi / K) * (SKIRT_BIN_WIDTH if skirt else 1.5)
            for k in range(K):
                th = -math.pi + 2 * math.pi * k / K
                dif = np.abs((ang - th + math.pi) % (2 * math.pi) - math.pi)
                m = dif < win
                r[k] = rad[m].max() if m.any() else np.nan
            if np.isnan(r).any():
                fill = np.nanmean(r) if not np.isnan(r).all() else (prev.mean() if prev is not None else 0.05)
                r = np.where(np.isnan(r), fill, r)
            r = (np.roll(r, 1) + 2 * r + np.roll(r, -1)) / 4
            r = r + radius_offset_fn(t)
            if skirt and prev is not None:
                r = np.maximum(r, prev)          # a skirt never narrows towards the hem
            out_rings.append((t, c, r))
            prev = r
        rr = np.array([r for _, _, r in out_rings])
        rr[1:-1] = (rr[:-2] + 2 * rr[1:-1] + rr[2:]) / 4
        verts, faces = [], []
        for j, (t, c, _) in enumerate(out_rings):
            for k in range(K):
                th = -math.pi + 2 * math.pi * k / K
                x, y = c[0] + rr[j, k] * math.cos(th), c[1] + rr[j, k] * math.sin(th)
                if frame is None:
                    verts.append(Vector((x, y, t)))
                else:
                    o, a, u, v = frame
                    verts.append(Vector(o) + Vector(a) * t + Vector(u) * x + Vector(v) * y)
        for j in range(len(out_rings) - 1):
            for k in range(K):
                k1 = (k + 1) % K
                faces.append([j * K + k, j * K + k1, (j + 1) * K + k1, (j + 1) * K + k])
        return verts, faces

    def garment_object(name, verts, faces, samples, exclude_bones=()):
        me_g = bpy.data.meshes.new(name)
        me_g.from_pydata([v[:] for v in verts], [], faces)
        me_g.validate()
        me_g.update()
        obj = bpy.data.objects.new(name, me_g)
        me_g.materials.append(mats["HERO_CLOTH_01"])
        for p_ in me_g.polygons:
            p_.use_smooth = True
        # weights: copied from the nearest sampled body vertex (deterministic nearest, ties → lowest index)
        S = np.array([co[i][:] for i in samples], dtype=np.float64)
        V = np.array([v[:] for v in verts], dtype=np.float64)
        groups_by_bone = {}
        for new, v in enumerate(V):
            dist = ((S - v) ** 2).sum(axis=1)
            src_i = samples[int(np.argmin(dist))]
            acc = {}
            for bn, w in weights[src_i].items():
                tb = bone_map[bn]
                if tb in exclude_bones:
                    continue
                acc[tb] = acc.get(tb, 0.0) + w
            if not acc:
                acc = {"spine_05": 1.0}
            tot = sum(acc.values()) or 1.0
            for tb, w in acc.items():
                if w > 0.0:
                    groups_by_bone.setdefault(tb, []).append((new, w / tot))
        for bn in sorted(groups_by_bone):
            vg = obj.vertex_groups.new(name=bn)
            for new, w in groups_by_bone[bn]:
                vg.add([new], w, "REPLACE")
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        mod.use_deform_preserve_volume = ARMATURE_PRESERVE_VOLUME
        obj.parent = rig
        return obj

    # dress: body of the dress (yoke top → hem, flaring below the waist) …
    dress_rings = [collar_z - k * (collar_z - hem_z) / (DRESS_RINGS - 1) for k in range(DRESS_RINGS)]
    def dress_offset(z):
        flare = max(0.0, (waist_z - z) / (waist_z - hem_z)) if z < waist_z else 0.0
        return DRESS_OFFSET_M + flare ** 1.3 * DRESS_FLARE_M
    def dress_centre(z, rel):
        return np.array([0.0, float(rel[:, 1].mean())])
    dv, df = polar_tube(dress_rings, torso_v, dress_centre, dress_offset, DRESS_SEGMENTS, (collar_z - hem_z) / (DRESS_RINGS - 1) * 0.8, skirt_below=waist_z)
    # … plus a yoke that closes the neck opening (Д1): the dress top was a horizontal circle that
    # never touched the neck, so a line of sight entered over its rim and left through the front.
    # The yoke runs from the top ring of the dress to a collar line resting on the neck — higher at
    # the back than at the front, as a real neckline does — and its last ring sits on the neck
    # surface, so there is no opening from any angle. Its rings are interpolated per angle between
    # the dress rim and the collar line, so it is one closed surface with the dress.
    neck_samples = [i for i in range(n_v) if i in body_idx and i in dom_v
                    and dom_v[i] in ("neck01", "neck02", "neck03", "head") and co[i].z >= collar_z - 0.01]
    # the neck skin above and below the seam: body vertices ruled by the neck/head bones plus the
    # head shell's own neck part (unskinned, but the collar line at the back reaches above the seam)
    neck_axis_y = ring_c.y                         # the neck axis is the seam ring's centre (SOCKET_HEAD)
    surf = torso_v + neck_samples                  # skin samples for the body radius around the collar
    K = DRESS_SEGMENTS
    ths = [-math.pi + 2 * math.pi * k / K for k in range(K)]

    def body_radius(z, samples=None):
        """Skin radius per angle at height z in the collar's polar frame (max sample in a ±2-bin window,
        wider band when sparse), smoothed 1-2-1 twice along the angle."""
        src = surf if samples is None else samples
        band = [i for i in src if abs(co[i].z - z) < YOKE_BAND_M]
        if len(band) < 8:
            band = sorted(src, key=lambda i: abs(co[i].z - z))[:24]
        pol = [(math.atan2(co[i].y - neck_axis_y, co[i].x), math.hypot(co[i].x, co[i].y - neck_axis_y)) for i in band]
        r = []
        for th in ths:
            rads = [rr for a, rr in pol if abs((a - th + math.pi) % (2 * math.pi) - math.pi) < 2 * math.pi / K * 2.0]
            r.append(max(rads) if rads else float("nan"))
        if any(x != x for x in r):
            fill = max(x for x in r if x == x)
            r = [x if x == x else fill for x in r]
        for _ in range(2):
            r = [(r[k - 1] + 2 * r[k] + r[(k + 1) % K]) / 4 for k in range(K)]
        return r

    # collar line: z per angle (front dips, back rises), radius = smoothed skin radius − penetration.
    # Smoothing never pushes the radius below the skin minus the penetration (owner's clamp, Д1).
    z_collar, r_collar = [], []
    for th in ths:
        sn = math.sin(th)
        sideness = 1.0 - abs(sn)
        z_collar.append(collar_z + YOKE_RISE_SIDE_M * sideness + (YOKE_RISE_BACK_M if sn > 0 else YOKE_RISE_FRONT_M) * abs(sn))
    # The collar line is measured by ray-casting from the neck axis outward at each angle and height
    # against the skin (body + head shell, rest pose): the first hit is the neck surface, whatever the
    # jaw or the shoulders do nearby. Smoothing along the angle never lifts the line out of the skin
    # (clamped to hit − penetration) and never sinks it deeper than twice the penetration.
    from mathutils.bvhtree import BVHTree
    # neck skin only: the body and the shell's neck part (the shell's mouth cavity sits just above)
    skin_faces = [list(f) for f in body_faces] + [list(f) for f in head_faces if all(co[i].z < ring_c.z + COLLAR_HEAD_NECK_M for i in f)]
    skin_tree = BVHTree.FromPolygons([c[:] for c in co], skin_faces, all_triangles=False)
    raw = []
    for k, th in enumerate(ths):
        o = Vector((0.0, neck_axis_y, z_collar[k]))
        d = Vector((math.cos(th), math.sin(th), 0.0))
        hit = skin_tree.ray_cast(o, d, 0.4)
        raw.append(hit[3] if hit[0] is not None else float("nan"))
    if any(x != x for x in raw):
        fill = min(x for x in raw if x == x)
        raw = [x if x == x else fill for x in raw]
    pen = [COLLAR_PENETRATION_FRONT_M + (COLLAR_PENETRATION_BACK_M - COLLAR_PENETRATION_FRONT_M) * (0.5 + 0.5 * math.sin(th)) for th in ths]
    r_collar = [(raw[k - 1] + 2 * raw[k] + raw[(k + 1) % K]) / 4 for k in range(K)]
    r_collar = [min(max(r_collar[k], raw[k] - 2 * pen[k]), raw[k] - pen[k]) for k in range(K)]
    print(f"collar line: neck radius by ray-cast per 30°: {[round(raw[k] * 100, 1) for k in range(0, K, 4)]} cm, line {COLLAR_PENETRATION_FRONT_M * 1000:.1f} (front) – {COLLAR_PENETRATION_BACK_M * 1000:.1f} (back) mm inside the skin")
    rim = dv[:K]                                   # top ring of the dress, angle k → vertex
    yoke_rings = []
    for step in range(1, YOKE_RINGS + 1):
        u = step / YOKE_RINGS
        w = u ** YOKE_EASE                          # ease so the yoke leaves the dress tangentially
        ring = []
        for k, th in enumerate(ths):
            target = Vector((r_collar[k] * math.cos(th), neck_axis_y + r_collar[k] * math.sin(th), z_collar[k]))
            ring.append(rim[k] * (1.0 - w) + target * w)
        # intermediate rings never dip inside the skin at their own height (shoulder slope)
        if step < YOKE_RINGS:
            zs_ring = [v.z for v in ring]
            for k, th in enumerate(ths):
                rb = body_radius(zs_ring[k])[k] + DRESS_OFFSET_M * (1.0 - w)
                v = ring[k]
                rr = math.hypot(v.x, v.y - neck_axis_y)
                if rr < rb:
                    ring[k] = Vector((rb * math.cos(th), neck_axis_y + rb * math.sin(th), v.z))
            rrs = [math.hypot(v.x, v.y - neck_axis_y) for v in ring]
            rrs = [(rrs[k - 1] + 2 * rrs[k] + rrs[(k + 1) % K]) / 4 for k in range(K)]
            ring = [Vector((rrs[k] * math.cos(th), neck_axis_y + rrs[k] * math.sin(th), ring[k].z)) for k, th in enumerate(ths)]
        yoke_rings.append(ring)
    for step, ring in enumerate(yoke_rings):
        start = len(dv)
        dv.extend(ring)
        prev = 0 if step == 0 else start - K
        for k in range(K):
            k1 = (k + 1) % K
            df.append([prev + k1, prev + k, start + k, start + k1])
    print(f"yoke: {YOKE_RINGS} rings, rise front {YOKE_RISE_FRONT_M * 100:.1f} / side {YOKE_RISE_SIDE_M * 100:.1f} / back {YOKE_RISE_BACK_M * 100:.1f} cm")
    # weights of the whole dress, collar included, come from the torso only (owner's condition: the
    # neckline follows the chest, never the head or the neck)
    garments = [garment_object("HERO_DRESS", dv, df, torso_v, exclude_bones=("head", "neck"))]
    bad = [g.name for g in garments[0].vertex_groups if g.name in ("head", "neck")]
    if bad:
        fail(f"HERO_DRESS carries weights on {bad} — the collar would turn with the head")
    # sleeves: tubes along the upper arm, from inside the shoulder to the elbow
    arm_t = {}
    for sd, S_ in ((".L", "L"), (".R", "R")):
        sh = mh_bones["upperarm01" + sd]["head"]
        el = mh_bones["lowerarm01" + sd]["head"]
        a = (el - sh).normalized()
        u = a.cross(Vector((0.0, 0.0, 1.0))).normalized()
        v = a.cross(u).normalized()
        L = (el - sh).length
        arm_t[sd] = (sh, a, L)
        rings = [SLEEVE_START_M + k * (L - SLEEVE_START_M) / (SLEEVE_RINGS - 1) for k in range(SLEEVE_RINGS)]
        sv, sf = polar_tube(rings, arm_v[sd], None, lambda t: SLEEVE_OFFSET_M + max(0.0, SLEEVE_SHOULDER_FLARE_TO_M - t) * SLEEVE_SHOULDER_FLARE, SLEEVE_SEGMENTS, (L - SLEEVE_START_M) / (SLEEVE_RINGS - 1) * 0.8, frame=(sh, a, u, v))
        cap = len(sv)                                       # the shoulder end is closed: nothing to see inside
        sv.append(sum((sv[k] for k in range(SLEEVE_SEGMENTS)), Vector()) / SLEEVE_SEGMENTS)
        for k in range(SLEEVE_SEGMENTS):
            sf.append([cap, (k + 1) % SLEEVE_SEGMENTS, k])
        garments.append(garment_object("HERO_SLEEVE_" + S_, sv, sf, arm_v[sd]))

    # body under the dress and sleeves is removed (margins under collar, hem and cuffs)
    def under_garment(i):
        if i not in dom_v or i in ring_set or i in neck_row:
            return False
        d = dom_v[i]
        z = co[i].z
        if d.startswith(torso_bones) and hem_z + BODY_REMOVE_MARGIN_M <= z <= collar_z - BODY_REMOVE_MARGIN_M:
            return True
        for sd in (".L", ".R"):
            if d.startswith(arm_bones + ("shoulder01",)) and d.endswith(sd):
                sh, a, L = arm_t[sd]
                t = (co[i] - sh).dot(a)
                if ARM_REMOVE_FROM_M <= t <= L - BODY_REMOVE_MARGIN_M:
                    return True
        return False
    before = len(body_faces)
    body_faces = [f for f in body_faces if not all(under_garment(i) for i in f)]
    print(f"body under the dress removed: {before - len(body_faces)} faces of {before}")

    def skinned(name, faces, ring_group):
        obj, remap, used = mesh_from_faces(name, co, faces)
        obj.data.materials.append(mats["HERO_SKIN_BODY"])
        obj.data.materials.append(mats["HERO_CLOTH_01"])
        obj.data.materials.append(mat_get("HERO_SHOES", (0.12, 0.10, 0.22), Roughness=0.5))
        for p in obj.data.polygons:
            p.material_index = region(tuple(used[i] for i in p.vertices))
        groups_by_bone = {}
        for new, old in enumerate(used):
            if ring_group and old in ring_set:
                groups_by_bone.setdefault("head", []).append((new, 1.0))
                continue
            acc = {}
            for bn, w in weights[old].items():
                tb = bone_map[bn]
                acc[tb] = acc.get(tb, 0.0) + w
            if ring_group and old in neck_row:      # Q17: smooth head → neck hand-over below the seam
                hw = NECK_BLEND_HEAD_WEIGHT[neck_row[old] - 1]
                rest = {tb: w for tb, w in acc.items() if tb != "head"}
                tot = sum(rest.values())
                acc = {"head": hw}
                if tot > 0.0:
                    for tb, w in rest.items():
                        acc[tb] = (1.0 - hw) * w / tot
                else:
                    acc["neck"] = 1.0 - hw
            tot = sum(acc.values()) or 1.0
            for tb, w in acc.items():
                if w > 0.0:
                    groups_by_bone.setdefault(tb, []).append((new, w / tot))
        for bn in sorted(groups_by_bone):
            vg = obj.vertex_groups.new(name=bn)
            for new, w in groups_by_bone[bn]:
                vg.add([new], w, "REPLACE")
        if ring_group:
            vg = obj.vertex_groups.new(name="SOCKET_BOUNDARY")
            for new, old in enumerate(used):
                if old in ring_set:
                    vg.add([new], ring_weight[old], "REPLACE")
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        mod.use_deform_preserve_volume = ARMATURE_PRESERVE_VOLUME
        obj.parent = rig
        return obj
    body = skinned("HERO_BODY", body_faces, True)
    link_only(body, colls["C_BODY"])
    for g in garments:
        link_only(g, colls["C_BODY"])
    hand = skinned("HERO_HAND_FG", hand_faces, False)
    link_only(hand, colls["C_HAND_FG"])

    # ---- 8. socket, face control, proxies re-parented to the new head bone -----------------
    bpy.context.view_layer.update()
    for o in (socket, ctrl):
        o.parent = rig
        o.parent_type = "BONE"
        o.parent_bone = "head"
    bpy.context.view_layer.update()
    socket.matrix_world = Matrix.Translation(ring_c)
    ctrl.matrix_world = Matrix.Translation(ring_c + Vector((0.0, -0.25, 0.10))) @ ctrl_world.to_3x3().to_4x4()
    bpy.context.view_layer.update()
    ring_r = max((co[i] - ring_c).xy.length for i in ring_idx)
    neck_len = ring_c.z - clav_z            # visible neck: shoulder top → ring
    prox_specs = {"NECK_PROXY": ("neck", "cyl", ring_r * 1.08, neck_len, Vector((0, ring_c.y, ring_c.z - neck_len / 2))),
                  "COLLISION_PROXY": ("spine_03", "box", None, None, None)}
    torso = [co[i] for f in body_faces for i in f if dominant(f).startswith(("spine01", "spine02", "clavicle", "breast", "shoulder01"))]
    lo = Vector((min(v.x for v in torso), min(v.y for v in torso), min(v.z for v in torso)))
    hi = Vector((max(v.x for v in torso), max(v.y for v in torso), max(v.z for v in torso)))
    for name, (bone, kind, r, h, at) in prox_specs.items():
        o = bpy.data.objects[name]
        bmp = bmesh.new()
        if kind == "cyl":
            bmesh.ops.create_cone(bmp, cap_ends=True, segments=24, radius1=r, radius2=r, depth=h)
            world = Matrix.Translation(at)
        else:
            bmesh.ops.create_cube(bmp, size=1.0)
            size = (hi - lo) * 1.05
            world = Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((size.x, size.y, size.z, 1.0))
        bmp.to_mesh(o.data)
        bmp.free()
        o.data.update()
        o.parent = rig
        o.parent_type = "BONE"
        o.parent_bone = bone
        bpy.context.view_layer.update()
        o.matrix_world = world
        o.hide_render = True
    bpy.context.view_layer.update()

    # ---- 8b. burst 3: the synthetic child's head (only with --subject) -----------------------
    # Body, clothes, rig and proxies are already built from the master positions above, so nothing below
    # the ring can change. A second MakeHuman human carries the child's own targets; every vertex ABOVE the
    # ring moves toward it, plus the child's own sculpted deviation, with a weight that fades to zero at the
    # ring (smoothstep over blend_ramp_m) — the ring stays vertex for vertex the default head's ring.
    if subj is not None:
        objs0, meshes0, mats0 = set(bpy.data.objects.keys()), set(bpy.data.meshes.keys()), set(bpy.data.materials.keys())
        arms0 = set(bpy.data.armatures.keys())
        child_h = HumanService.create_human(mask_helpers=False, macro_detail_dict=json.loads(json.dumps(MACRO)))
        for folder, target, weight in [tuple(t) for t in STYLE_TARGETS] + [tuple(t) for t in subj["targets"]]:
            TargetService.load_target(child_h, os.path.join(targets_root, folder, target + ".target.gz"), weight=weight)
        TargetService.bake_targets(child_h)
        cme = child_h.data
        czs = [cme.vertices[i].co.z for i in body_idx]
        cs = args.height / (max(czs) - min(czs))
        co2 = [Vector((v.co.x * cs, v.co.y * cs, (v.co.z - min(czs)) * cs)) for v in cme.vertices]
        # Collar seam (Q55; one rule for every child — owner Q58, no flag): the child's MakeHuman body is normalised to
        # the height on its own, so a head target that changes its height (head-scale-vert, ...) moves the child's
        # whole head up or down against the default ring, and the 35-mm ramp stretches or squeezes the neck band — a
        # see-through slit at the collar on the extreme turn. Translate the child's human so its ring centre coincides
        # with the default ring centre. The default head (no --subject) never comes here: v04.1 stays bit for bit.
        c_def = sum((co[i] for i in ring_idx), Vector()) / len(ring_idx)
        c_chd = sum((co2[i] for i in ring_idx), Vector()) / len(ring_idx)
        shift = c_def - c_chd
        co2 = [p_ + shift for p_ in co2]
        print(f"subject {subj['subject']}: ring alignment — child human moved {shift.length * 1000:.2f} mm "
              f"({shift.x * 1000:+.2f}, {shift.y * 1000:+.2f}, {shift.z * 1000:+.2f}) to the default ring")
        for name in set(bpy.data.objects.keys()) - objs0:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        for coll, before in ((bpy.data.meshes, meshes0), (bpy.data.materials, mats0), (bpy.data.armatures, arms0)):
            for name in set(coll.keys()) - before:
                coll.remove(coll[name])
        ring_ang = sorted((math.atan2(co[i].x - ring_c.x, co[i].y - ring_c.y), co[i].z) for i in ring_idx)
        def ring_z_at(p):
            ang = math.atan2(p.x - ring_c.x, p.y - ring_c.y)
            return min(ring_ang, key=lambda t: abs(math.remainder(t[0] - ang, 2 * math.pi)))[1]
        ramp = float(subj.get("blend_ramp_m", 0.035))
        bumps = [(Vector(b["centre"]) + ring_c, float(b["radius"]), Vector(b["offset"])) for b in subj.get("sculpt", [])]
        head_vset = {i for f in head_faces for i in f}
        moved = 0
        for i in range(n_v):
            if i in ring_set:
                continue
            depth = co[i].z - ring_z_at(co[i])
            if depth <= 0.0 or (i not in head_vset and i in body_idx and depth < 0.002):
                continue
            t = min(1.0, depth / ramp)
            w = t * t * (3.0 - 2.0 * t)
            sculpt = Vector()
            for c_, r_, off in (bumps if i in head_vset else ()):   # Q58: bumps on the head shell only — the eye,
                sculpt += off * math.exp(-((co[i] - c_).length / r_) ** 2)   # teeth and tongue helpers take the targets only
            co[i] = co[i] + ((co2[i] - co[i]) + sculpt) * w
            moved += 1
        print(f"subject {subj['subject']}: {moved} head vertices moved toward the child's identity "
              f"({len(subj['targets'])} targets, {len(bumps)} sculpt bumps, ramp {ramp * 1000:.0f} mm to the ring)")
        # Q58: the eye centres are the CHILD's eye helpers after the morph — every later use (lid closure gain and push-out,
        # brows and hair z_eye, the cheek strand, glasses, curls) works on this child's eyes, not the default head's.
        eye_c = {sd: sum((co[i] for i in groups[g]), Vector()) / len(groups[g]) for sd, g in (("L", "helper-l-eye"), ("R", "helper-r-eye"))}
        print(f"subject {subj['subject']}: eye centres from the child's helpers — L {tuple(round(x, 4) for x in eye_c['L'])}")

    # ---- 9. head shell with the 26-channel face --------------------------------------------
    head, hremap, hused = mesh_from_faces("HERO_HEAD", co, head_faces)
    head.data.materials.append(mats["HERO_SKIN_HEAD"])
    if subj is not None:                      # skin exactly the child's tone, head and body (TASK §3.2)
        for mn in ("HERO_SKIN_HEAD", "HERO_SKIN_BODY"):
            bsdf = mats[mn].node_tree.nodes.get("Principled BSDF") if mats[mn].use_nodes else None
            if bsdf is None:
                fail(f"{mn}: no Principled BSDF to set the tone on")
            bsdf.inputs["Base Color"].default_value = (*subj["tone_albedo_linear"], 1.0)
            mats[mn].diffuse_color = (*subj["tone_albedo_linear"], 1.0)
    vg = head.vertex_groups.new(name="SOCKET_BOUNDARY")
    for new, old in enumerate(hused):
        if old in ring_set:
            vg.add([new], ring_weight[old], "REPLACE")
    hset = set(hused)
    # v04 (Q28, ADR-0002 §D1 amendment 22.09): the shell's overlap band — everything below the
    # boundary curve — must sit INSIDE the body neck on every frame, not just at rest. The head is
    # rigid on the socket while the neck is skinned, so the body surface swings under it by several
    # millimetres; v03 ran from 0 to +7.5 mm outside. The band is therefore tucked toward the neck
    # axis: nothing at the ring itself (the seam stays welded), ramping to the full tuck TUCK_M a
    # little below it. This is applied to the base mesh BEFORE the face shape keys are built, so
    # every key inherits the same offset (Q28.2).
    ring_by_angle = sorted(ring_idx, key=lambda i: math.atan2(co[i].x - ring_c.x, co[i].y - ring_c.y))
    def ring_z_at(p):
        a = math.atan2(p.x - ring_c.x, p.y - ring_c.y)
        j = min(ring_by_angle, key=lambda i: abs((math.atan2(co[i].x - ring_c.x, co[i].y - ring_c.y) - a + math.pi) % (2 * math.pi) - math.pi))
        return co[j].z
    tucked = 0
    for new, old in enumerate(hused):
        p = head.data.vertices[new].co
        depth = ring_z_at(p) - p.z
        if depth <= 0 or math.hypot(p.x - ring_c.x, p.y - ring_c.y) > SEAM_BAND_RADIUS_M:
            continue
        w = min(1.0, (depth * 1000.0) / SEAM_TUCK_RAMP_MM)
        radial = Vector((p.x - ring_c.x, p.y - ring_c.y, 0.0))
        if radial.length < 1e-6:
            continue
        head.data.vertices[new].co = p - radial.normalized() * (TUCK_M * w)
        tucked += 1
    head.data.update()
    print(f"seam band tucked: {tucked} shell vertices, up to {TUCK_M * 1000:.1f} mm toward the neck axis (ramp {SEAM_TUCK_RAMP_MM} mm)")

    def combine(spec):
        d = {}
        for unit, side, factor in spec:
            for i, dv in units[unit].items():
                if i in hset:
                    m = side_mask(co[i].x, side) * factor
                    if m > 0.0:
                        d[i] = d.get(i, Vector()) + dv * m
        return d
    mouth_open = units["mouth-open"]
    jaw_pts = [i for i, dv in mouth_open.items() if i in hset]
    jaw_max = max(mouth_open[i].length for i in jaw_pts)
    jaw_lateral = {i: Vector((JAW_LATERAL_M * mouth_open[i].length / jaw_max, 0.0, 0.0)) for i in jaw_pts}
    face_keys = {}       # channel → [(key name, expression)]
    for channel, (pos, neg) in CHANNEL_MAP.items():
        entries = []
        if pos == "LID":
            continue
        if pos == "JAW_LATERAL":
            entries.append((f"fc_{channel}_pos", jaw_lateral, "max(v, 0.0)"))
            entries.append((f"fc_{channel}_neg", {i: -dv for i, dv in jaw_lateral.items()}, "max(-v, 0.0)"))
        else:
            entries.append((f"fc_{channel}_pos", combine(pos), "max(v, 0.0)"))
            if neg:
                entries.append((f"fc_{channel}_neg", combine(neg), "max(-v, 0.0)"))
        face_keys[channel] = entries
    for channel, entries in face_keys.items():
        for kname, deltas, expr in entries:
            kb = add_shape_key(head, kname, deltas, hused)
            add_driver(kb, "value", ctrl, channel, expr)
    # Lids (Q19/Q21, channel_map.json → combination_rules):
    #   closure  c = max(max(0, -lid_aperture), blink)      widening w = max(0, lid_aperture) · (1 − blink)
    # closure runs through an in-between at c = 0.5 (the linear half-way lid cuts into the eyeball;
    # the mid key keeps every lid vertex outside the eye sphere), so: full = max(0, 2c−1),
    # mid = 1 − |2c−1|. The pair sums to the closure target exactly at c = 1 and to the mid key at c = 0.5.
    lid_keys = {}
    for side, S, grp in (("l", "L", "helper-l-eye"), ("r", "R", "helper-r-eye")):
        closure = combine([(f"eye-{'left' if side == 'l' else 'right'}-closure", None, 1.0)])
        widen = combine([(f"eye-{'left' if side == 'l' else 'right'}-opened-up", None, 1.0)])
        ec = eye_c[S]
        er = max((co[i] - ec).length for i in groups[grp]) * 0.98
        # Full closure on this head: the MakeHuman unit is adult-scale and the eyes were enlarged by
        # the style targets, so the lid margins may still leave a slit at weight 1. Measure the gap
        # between the upper and lower lid margins over the pupil column at full weight and scale the
        # unit so that the margins meet (lid_aperture −1 = "fully closed", channel_map.json).
        col = [i for i in closure if abs(co[i].x - ec.x) < LID_COLUMN_HALF_WIDTH_M and (co[i] - ec).y < 0.0]
        upper = [i for i in col if co[i].z > ec.z]
        # the lower lid does not move in the unit: its margin is the highest front shell vertex on
        # the eyeball below the centre line
        lower = [i for i in hused if abs(co[i].x - ec.x) < LID_COLUMN_HALF_WIDTH_M and (co[i] - ec).y < 0.0
                 and co[i].z <= ec.z and (co[i] - ec).length < er + 0.003]
        if upper and lower:
            up_margin = min(upper, key=lambda i: (co[i] + closure[i]).z)
            lo_margin = max(lower, key=lambda i: (co[i] + closure.get(i, Vector())).z)
            gap = (co[up_margin] + closure[up_margin]).z - (co[lo_margin] + closure.get(lo_margin, Vector())).z
            travel = -closure[up_margin].z
            gain = min(LID_GAIN_MAX, max(1.0, 1.0 + (gap + LID_OVERLAP_M) / travel)) if travel > 1e-6 else 1.0
        else:
            gain = 1.0
        print(f"lid {side}: closure gain {gain:.3f}")
        closure = {i: dv * gain for i, dv in closure.items()}
        pushed_full = 0
        for i, dv in list(closure.items()):        # the closed lid lies on the eyeball, never inside it
            p = co[i] + dv
            rad = p - ec
            if rad.length < er + LID_EYE_CLEARANCE_M and rad.length > 1e-9:
                closure[i] = ec + rad.normalized() * (er + LID_EYE_CLEARANCE_M) - co[i]
                pushed_full += 1
        print(f"lid {side}: {pushed_full} closure vertices pushed out of the eye sphere at full closure")
        mid, pushed = {}, 0
        for i, dv in closure.items():
            p = co[i] + dv * 0.5
            rad = p - ec
            if rad.length < er + LID_EYE_CLEARANCE_M and rad.length > 1e-9:
                p = ec + rad.normalized() * (er + LID_EYE_CLEARANCE_M)
                pushed += 1
            mid[i] = p - co[i]
        print(f"lid {side}: {len(closure)} closure vertices, {pushed} pushed out of the eye sphere at the in-between")
        c_expr = "max(max(0.0, -v), b)"
        kb = add_shape_key(head, f"fc_lid_close_full_{side}", closure, hused)
        add_driver(kb, "value", ctrl, f"lid_aperture_{side}", f"max(0.0, 2.0 * {c_expr} - 1.0)", extra={"b": f"blink_{side}"})
        kb = add_shape_key(head, f"fc_lid_close_mid_{side}", mid, hused)
        add_driver(kb, "value", ctrl, f"lid_aperture_{side}", f"1.0 - abs(2.0 * {c_expr} - 1.0)", extra={"b": f"blink_{side}"})
        kb = add_shape_key(head, f"fc_lid_widen_{side}", widen, hused)
        add_driver(kb, "value", ctrl, f"lid_aperture_{side}", "max(0.0, v) * (1.0 - b)", extra={"b": f"blink_{side}"})
        lid_keys[side] = (closure, mid, widen)
    chin = [i for i in jaw_pts if co[i].z < ring_c.z + 0.6 * (max(co[j].z for j in jaw_pts) - ring_c.z)]
    jaw_drop = sum((mouth_open[i] for i in chin), Vector()) / max(1, len(chin)) * 0.85

    # ---- 10. eyes, teeth, tongue, brows --------------------------------------------------------
    head_children = [head]
    for side, grp in (("L", "helper-l-eye"), ("R", "helper-r-eye")):
        pts = [co[i] for i in groups[grp]]
        c = sum(pts, Vector()) / len(pts)
        r = max((p - c).length for p in pts) * 0.98
        # Sphere with its pole on the view axis (−Y) and ring latitudes chosen so the pupil and
        # iris edges are exact vertex rings — the pupil is geometry, not a face-normal cut (Q20/Q21).
        me_e = bpy.data.meshes.new(f"HERO_EYE_{side}")
        ev, ef, emat = [], [], []
        ev.append(Vector((0.0, -r, 0.0)))
        ring_ids = []
        for lat in EYE_LATITUDES_DEG[1:]:
            ph = math.radians(lat)
            ids = []
            for k in range(EYE_SEGMENTS):
                th = 2 * math.pi * k / EYE_SEGMENTS
                ids.append(len(ev))
                ev.append(Vector((r * math.sin(ph) * math.cos(th), -r * math.cos(ph), r * math.sin(ph) * math.sin(th))))
            ring_ids.append(ids)
        ev.append(Vector((0.0, r, 0.0)))
        def zone(lat):
            return 2 if lat <= EYE_PUPIL_DEG + 1e-9 else (1 if lat <= EYE_IRIS_DEG + 1e-9 else 0)
        for k in range(EYE_SEGMENTS):
            ef.append([0, ring_ids[0][k], ring_ids[0][(k + 1) % EYE_SEGMENTS]])
            emat.append(zone(EYE_LATITUDES_DEG[1]))
        for a in range(len(ring_ids) - 1):
            for k in range(EYE_SEGMENTS):
                k1 = (k + 1) % EYE_SEGMENTS
                ef.append([ring_ids[a][k], ring_ids[a + 1][k], ring_ids[a + 1][k1], ring_ids[a][k1]])
                emat.append(zone(EYE_LATITUDES_DEG[a + 2]))
        last = len(ev) - 1
        for k in range(EYE_SEGMENTS):
            ef.append([ring_ids[-1][(k + 1) % EYE_SEGMENTS], ring_ids[-1][k], last])
            emat.append(0)
        me_e.from_pydata([v[:] for v in ev], [], ef)
        me_e.validate()
        me_e.update()
        eye = bpy.data.objects.new(f"HERO_EYE_{side}", me_e)
        for m_ in (mat_get("HERO_EYE_SCLERA", (0.90, 0.90, 0.92), Roughness=0.25),
                   mat_get("HERO_EYE_IRIS", tuple(subj["iris_color_linear"]) if subj else (0.10, 0.30, 0.55), Roughness=0.35),
                   mat_get("HERO_EYE_PUPIL", (0.01, 0.01, 0.01), Roughness=0.3)):
            me_e.materials.append(m_)
        for p_, mi in zip(me_e.polygons, emat):
            p_.use_smooth = True
            p_.material_index = mi
        eye.matrix_world = Matrix.Translation(c)
        eye.rotation_mode = "XYZ"
        add_driver(eye, "rotation_euler", ctrl, "gaze_yaw", f"v * {math.radians(GAZE_YAW_DEG):.6f}", index=2)   # +1 → anatomical left (+X)
        add_driver(eye, "rotation_euler", ctrl, "gaze_pitch", f"-v * {math.radians(GAZE_PITCH_DEG):.6f}", index=0)  # +1 → up
        head_children.append(eye)
    for name, grp, mname, color in (("HERO_TEETH_UPPER", "helper-upper-teeth", "HERO_TEETH", (0.85, 0.83, 0.78)),
                                    ("HERO_TEETH_LOWER", "helper-lower-teeth", "HERO_TEETH", (0.85, 0.83, 0.78)),
                                    ("HERO_TONGUE", "helper-tongue", "HERO_MOUTH_INNER", (0.45, 0.12, 0.14))):
        faces = [f for f in faces_all if all(i in groups[grp] for i in f)]
        obj, rmap, used = mesh_from_faces(name, co, faces)
        obj.data.materials.append(mat_get(mname, color, Roughness=0.4))
        if name != "HERO_TEETH_UPPER":
            kb = add_shape_key(obj, "fc_jaw_open_pos", {i: jaw_drop for i in used}, used)
            add_driver(kb, "value", ctrl, "jaw_open", "max(v, 0.0)")
        head_children.append(obj)
    # brow patch: shell faces whose vertices move most under the brow-up units
    # ---- brows: a separate tapered arch per side in C_HEAD (Q20), following the brow shape keys ----
    z_eye = (eye_c["L"].z + eye_c["R"].z) / 2
    head_c = sum((co[i] for i in hused), Vector()) / len(hused)
    def in_brow(i):
        v = co[i]
        return (z_eye + BROW_ABOVE_EYE_M < v.z < z_eye + BROW_TOP_M and v.y < head_c.y - 0.01
                and BROW_X_MIN_M < abs(v.x) < BROW_X_MAX_M)
    brow_band = [i for i in hused if in_brow(i)]
    bv, bf, brow_rings = [], [], []          # rings: (vertex ids, nearest band vertex)
    for S, sign in (("L", 1.0), ("R", -1.0)):
        ec = eye_c[S]
        front = [i for i in hused if co[i].x * sign > 0.0 and co[i].y < head_c.y - 0.01 and z_eye < co[i].z < z_eye + 0.06]
        base_ring = len(brow_rings)
        for k in range(BROW_RINGS):
            u = k / (BROW_RINGS - 1)
            # parametric arch over the eye: from the inner corner outwards, peaking past the pupil
            x = BROW_X_MIN_M + (BROW_X_MAX_M - BROW_X_MIN_M) * u
            z = z_eye + BROW_ABOVE_EYE_M + BROW_ARCH_M * math.sin(math.pi * u ** 0.8)
            win = [i for i in front if abs(co[i].x * sign - x) < BROW_WINDOW_M and abs(co[i].z - z) < BROW_WINDOW_M]
            if not win:
                win = sorted(front, key=lambda i: (co[i].x * sign - x) ** 2 + (co[i].z - z) ** 2)[:4]
            y = min(co[i].y for i in win)                   # the skin surface at (x, z): the front-most vertex
            c = Vector((x * sign, y, z))
            src = min(win, key=lambda i: (co[i] - c).length)
            out = (c - ec).normalized()
            up = (Vector((0.0, 0.0, 1.0)) - out * out.z).normalized()
            thick = BROW_THICK_M * (1.0 - 0.55 * u)     # tapers to the outer end
            height = BROW_HEIGHT_M * (1.0 - 0.35 * u)
            c = c + out * (thick + BROW_LIFT_M)
            ids = []
            for j in range(BROW_SIDES):
                a = 2 * math.pi * j / BROW_SIDES
                ids.append(len(bv))
                bv.append(c + up * (height * math.cos(a)) + out * (thick * math.sin(a)))
            brow_rings.append((ids, src))
        for k in range(BROW_RINGS - 1):
            r0, r1 = brow_rings[base_ring + k][0], brow_rings[base_ring + k + 1][0]
            for j in range(BROW_SIDES):
                j1 = (j + 1) % BROW_SIDES
                bf.append([r0[j], r1[j], r1[j1], r0[j1]][::int(sign)])
        for end, order in ((0, 1), (BROW_RINGS - 1, -1)):
            ids = brow_rings[base_ring + end][0]
            cap = len(bv)
            bv.append(sum((bv[i] for i in ids), Vector()) / len(ids))
            for j in range(BROW_SIDES):
                bf.append([cap, ids[(j + 1) % BROW_SIDES], ids[j]][::order * int(sign)])
    me_b = bpy.data.meshes.new("HERO_BROWS")
    me_b.from_pydata([v[:] for v in bv], [], bf)
    me_b.validate()
    me_b.update()
    brows = bpy.data.objects.new("HERO_BROWS", me_b)
    me_b.materials.append(mat_get("HERO_BROW", tuple(subj["brow_color_linear"]) if subj else (0.20, 0.12, 0.07), Roughness=0.7))
    for p_ in me_b.polygons:
        p_.use_smooth = True
    # the arch follows the shell: every ring moves with the brow-channel delta of its source vertex
    for channel, entries in face_keys.items():
        if not channel.startswith("brow"):
            continue
        for kname, deltas, expr in entries:
            per_vertex = {}
            for ids, src in brow_rings:
                d = deltas.get(src)
                if d is not None:
                    for vid_ in ids:
                        per_vertex[vid_] = d
            kb = add_shape_key(brows, kname, per_vertex, list(range(len(bv))))
            add_driver(kb, "value", ctrl, channel, expr)
    head_children.append(brows)
    print(f"brows: {len(bv)} vertices, {len(bf)} faces, band of {len(brow_band)} shell vertices")

    # ---- 11d. burst 3: glasses (only with --subject and "glasses": true) ------------------------
    # Rims, bridge and temples as tubes, flat lenses: fitted to this child's eyes and head width, rigid on the
    # socket like the hair, in C_HEAD without SOCKET_BOUNDARY (an accessory of the child's head). Materials
    # HERO_GLASSES_FRAME (dark plastic) and HERO_GLASSES_LENS (glass, transmission). Deterministic.
    if subj is not None and subj.get("glasses"):
        gv, gf = [], []
        def tube(path, r, sides=8, closed=False):
            base = len(gv); n = len(path)
            for i, p in enumerate(path):
                t = (path[(i + 1) % n] - path[i - 1]).normalized() if closed else (path[min(i + 1, n - 1)] - path[max(i - 1, 0)]).normalized()
                u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized(); w = t.cross(u).normalized()
                for s in range(sides):
                    al = 2 * math.pi * s / sides
                    gv.append(p + (u * math.cos(al) + w * math.sin(al)) * r)
            segs = n if closed else n - 1
            for i in range(segs):
                j = (i + 1) % n
                for s in range(sides):
                    s1 = (s + 1) % sides
                    gf.append([base + i * sides + s, base + i * sides + s1, base + j * sides + s1, base + j * sides + s])
        # Seat (Q55/Q59, spec): fitted to THIS child's head after the morph — the lens plane GLASSES_VERTEX_M in front of
        # the eyes' front points (10-14 mm), moved forward within that range and then the lens made smaller if a rim
        # would come closer than GLASSES_RIM_CLEAR_M to the skin (brow ridge, cheek); the bridge rests on the nose
        # (its tube GLASSES_BRIDGE_GAP_M off the skin at the nearest point); the temples run back outside the skin
        # (tube surface GLASSES_TEMPLE_CLEAR_M off it) over the top of the ear and hook down behind it.
        from mathutils.bvhtree import BVHTree
        skin_v = [co[i].copy() for i in range(n_v)]
        skin = BVHTree.FromPolygons(skin_v, [tuple(f) for f in head_faces])
        def skin_gap(p, r):                                # tube surface to skin, metres (negative = inside)
            hit = skin.find_nearest(p)
            return (hit[3] if hit[0] is not None else 1.0) - r
        def ray_y(x, z):                                   # the skin's front surface at (x, z), from in front
            hit = skin.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)), 2.0)
            return hit[0].y if hit[0] is not None else None
        def ray_x(sgn, y, z):                              # the skin's side surface at (y, z), from outside
            hit = skin.ray_cast(Vector((sgn * 1.0, y, z)), Vector((-sgn, 0.0, 0.0)), 2.0)
            return hit[0].x if hit[0] is not None else None
        eyes_mid = (eye_c["L"] + eye_c["R"]) / 2
        eye_r = {S: sum((co[i] - eye_c[S]).length for i in groups[g]) / len(groups[g]) for S, g in (("L", "helper-l-eye"), ("R", "helper-r-eye"))}
        eye_front_y = min(eye_c[S].y - eye_r[S] for S in ("L", "R"))
        tr = GLASSES_RIM_TUBE_R_M
        # the brows at their lowest (every *_neg key at 1): the rims must clear them there too (brows_down, all_squeezed)
        bk = brows.data.shape_keys.key_blocks
        bdown = [bk["Basis"].data[i].co.copy() for i in range(len(brows.data.vertices))]
        for kb in bk:
            if kb.name.endswith("_neg"):
                for i in range(len(bdown)):
                    bdown[i] += kb.data[i].co - bk["Basis"].data[i].co
        brow_low = BVHTree.FromPolygons([brows.matrix_world @ v for v in bdown], [tuple(p_.vertices) for p_ in brows.data.polygons])
        def brow_gap(p, r):
            hit = brow_low.find_nearest(p)
            return (hit[3] if hit[0] is not None else 1.0) - r
        lens_up, rim_h = GLASSES_LENS_UP_M, 0.88            # rim_h: the lens's height / width
        def rim_ring(S, y, r):
            c_ = Vector((eye_c[S].x, y, eye_c[S].z + lens_up))
            return c_, [c_ + Vector((r * math.cos(2 * math.pi * k / GLASSES_RIM_SEGS), 0.0, r * rim_h * math.sin(2 * math.pi * k / GLASSES_RIM_SEGS))) for k in range(GLASSES_RIM_SEGS)]
        def rims_gap(y, r):
            return min(skin_gap(p, tr) for S in ("L", "R") for p in rim_ring(S, y, r)[1])
        def rims_brow_gap(y, r):
            return min(brow_gap(p, tr) for S in ("L", "R") for p in rim_ring(S, y, r)[1])
        def fits(y, r):
            return rims_gap(y, r) >= GLASSES_RIM_CLEAR_M and rims_brow_gap(y, r) >= GLASSES_BROW_CLEAR_M
        vtx, rim_r = GLASSES_VERTEX_M, GLASSES_LENS_RADIUS_M
        while not fits(eye_front_y - vtx, rim_r) and vtx < GLASSES_VERTEX_MAX_M - 1e-9:
            vtx = min(GLASSES_VERTEX_MAX_M, vtx + 0.0005)
        while not fits(eye_front_y - vtx, rim_r) and lens_up > 1e-9:
            lens_up = max(0.0, lens_up - 0.0005)
        while not fits(eye_front_y - vtx, rim_r) and rim_h > 0.70 + 1e-9:
            rim_h = max(0.70, rim_h - 0.01)
        while not fits(eye_front_y - vtx, rim_r) and rim_r > GLASSES_LENS_RADIUS_MIN_M + 1e-9:
            rim_r = max(GLASSES_LENS_RADIUS_MIN_M, rim_r - 0.0005)
        front_y = eye_front_y - vtx
        rims = {}
        for S in ("L", "R"):
            c_, ring = rim_ring(S, front_y, rim_r)
            tube(ring, tr, closed=True)
            rims[S] = c_
        # bridge: inner rim tops → over the nose → its middle rests on the nasal bridge
        z_b = eyes_mid.z + lens_up + 0.002
        y_n = ray_y(0.0, z_b)
        mid = Vector((0.0, (y_n if y_n is not None else front_y) - GLASSES_BRIDGE_GAP_M - tr * 0.9, z_b))
        def bridge_path(m):
            a_ = Vector((rims["R"].x + rim_r * 0.92, front_y, rims["R"].z + 0.004)); b_ = Vector((rims["L"].x - rim_r * 0.92, front_y, rims["L"].z + 0.004))
            return [a_, (a_ + m) / 2 + Vector((0, 0, 0.002)), m, (b_ + m) / 2 + Vector((0, 0, 0.002)), b_]
        for _ in range(60):                                # nearest point of the tube to the skin: 0.5-1.5 mm
            g = min(skin_gap(p, tr * 0.9) for p in bridge_path(mid))
            if g < GLASSES_BRIDGE_GAP_M - 0.0005: mid.y -= 0.00025
            elif g > GLASSES_BRIDGE_GAP_M + 0.0005: mid.y += 0.00025
            else: break
        tube(bridge_path(mid), tr * 0.9)
        # temples: hinge at the rim's outer edge → back along the side of the head → over the ear top → hook down
        ears = groups["ears"] & set(hused)
        temple_info = {}
        for S, sgn in (("L", 1.0), ("R", -1.0)):
            side = [co[i] for i in ears if co[i].x * sgn > 0]
            top = max(side, key=lambda p_: p_.z)
            back_y = max(p_.y for p_ in side if p_.z > top.z - 0.012)
            hinge = Vector((rims[S].x + sgn * rim_r, front_y, rims[S].z + 0.004))
            z_top = top.z + tr * 0.85 + GLASSES_TEMPLE_CLEAR_M
            path = [hinge]
            for k in range(1, 13):
                t = k / 12.0; y = hinge.y + (top.y - hinge.y) * t
                z = hinge.z + (z_top - hinge.z) * (t * t * (3 - 2 * t))
                xs = ray_x(sgn, y, z)
                x = sgn * max(sgn * path[-1].x, (sgn * xs + tr * 0.85 + GLASSES_TEMPLE_CLEAR_M) if xs is not None else 0.0)
                q = Vector((x, y, z))
                while skin_gap(q, tr * 0.85) < GLASSES_TEMPLE_CLEAR_M:      # the nearest skin, not the sideways ray
                    q.x += sgn * 0.0002
                path.append(q)
            for dy, dz in ((0.004, -0.004), (0.008, -0.011), (0.010, -0.018)):
                y = back_y + dy; z = top.z + dz
                xs = ray_x(sgn, y, z)
                q = Vector(((xs if xs is not None else path[-1].x) + sgn * (tr * 0.85 + GLASSES_TEMPLE_CLEAR_M), y, z))
                while skin_gap(q, tr * 0.85) < GLASSES_TEMPLE_CLEAR_M:
                    q.x += sgn * 0.0002
                path.append(q)
            tube(path, tr * 0.85)
            temple_info[S] = (top, min(skin_gap(p_, tr * 0.85) for p_ in path[2:]))
            if os.environ.get("GLASSES_DEBUG"):
                print(f"temple {S}: " + " | ".join(f"{k}:y{p_.y:.3f} z{p_.z:.3f} x{p_.x:+.3f} g{skin_gap(p_, tr * 0.85) * 1000:.1f}" for k, p_ in enumerate(path)))
        lens_base = len(gv)
        for S in ("L", "R"):
            c_ = rims[S]; ctr = len(gv); gv.append(c_ + Vector((0, 0.0015, 0)))
            ring_idx_ = []
            for k in range(GLASSES_RIM_SEGS):
                ring_idx_.append(len(gv)); gv.append(c_ + Vector((rim_r * 0.92 * math.cos(2 * math.pi * k / GLASSES_RIM_SEGS), 0.0015, rim_r * (rim_h - 0.08) * math.sin(2 * math.pi * k / GLASSES_RIM_SEGS))))
            for k in range(GLASSES_RIM_SEGS):
                gf.append([ctr, ring_idx_[k], ring_idx_[(k + 1) % GLASSES_RIM_SEGS]])
        me_g = bpy.data.meshes.new("HERO_GLASSES"); me_g.from_pydata([v[:] for v in gv], [], gf); me_g.validate(); me_g.update()
        for p_ in me_g.polygons:
            p_.use_smooth = True
        glasses = bpy.data.objects.new("HERO_GLASSES", me_g)
        me_g.materials.append(mat_get("HERO_GLASSES_FRAME", tuple(subj.get("glasses_frame_color_linear", (0.05, 0.03, 0.02))), Roughness=0.3))
        lens_m = mat_get("HERO_GLASSES_LENS", (0.9, 0.95, 1.0), Roughness=0.0)
        nt_ = lens_m.node_tree                      # a thin lens: transparent with a Fresnel glossy reflection
        for n_ in list(nt_.nodes):
            nt_.nodes.remove(n_)
        out_ = nt_.nodes.new("ShaderNodeOutputMaterial"); mix_ = nt_.nodes.new("ShaderNodeMixShader")
        tr_ = nt_.nodes.new("ShaderNodeBsdfTransparent"); gl_ = nt_.nodes.new("ShaderNodeBsdfGlossy"); fr_ = nt_.nodes.new("ShaderNodeFresnel")
        gl_.inputs["Roughness"].default_value = 0.0; fr_.inputs["IOR"].default_value = 1.5
        nt_.links.new(fr_.outputs["Fac"], mix_.inputs["Fac"]); nt_.links.new(tr_.outputs["BSDF"], mix_.inputs[1]); nt_.links.new(gl_.outputs["BSDF"], mix_.inputs[2])
        nt_.links.new(mix_.outputs["Shader"], out_.inputs["Surface"])
        lens_m.blend_method = "BLEND" if hasattr(lens_m, "blend_method") else lens_m.blend_method
        me_g.materials.append(lens_m)
        for p_ in me_g.polygons:
            p_.material_index = 1 if p_.vertices[0] >= lens_base else 0
        head_children.append(glasses)
        print(f"glasses: {len(gv)} vertices, lens {2 * rim_r * 1000:.0f} x {2 * rim_r * rim_h * 1000:.0f} mm, rims {abs(rims['L'].x - rims['R'].x) * 1000:.0f} mm apart, "
              f"lens plane {vtx * 1000:.1f} mm in front of the eyes, lens centre {lens_up * 1000:+.1f} mm above the eye, rims >= {rims_gap(front_y, rim_r) * 1000:.1f} mm off the skin and {rims_brow_gap(front_y, rim_r) * 1000:.1f} mm off the lowest brows, "
              f"bridge {min(skin_gap(p, tr * 0.9) for p in bridge_path(mid)) * 1000:.2f} mm off the nose, temples >= "
              f"{min(v[1] for v in temple_info.values()) * 1000:.2f} mm off the skin, ear tops z {temple_info['L'][0].z:.4f}/{temple_info['R'][0].z:.4f}")

    # ---- 11. hair (Q61): hair_on_head.build_hair — the bob + strands (+ the default head's cheek strand) or the
    # child's hair class, from the head shell, eye centres, ring centre and collar height alone (no MakeHuman).
    hair = hair_on_head.build_hair(co, hused, head_faces, eye_c, ring_c, collar_z, brow_band, subj, mats, fail)

    # ---- 12. head-side objects: collections, socket parenting, ray visibility ------------------
    for o in head_children:
        link_only(o, colls["C_HEAD"])
    link_only(hair, colls["C_HAIR"])
    for o in head_children + [hair]:
        mw = o.matrix_world.copy()
        o.parent = socket
        o.matrix_parent_inverse = socket.matrix_world.inverted()
        o.matrix_world = mw
        shadow_caster_only(o)
    bpy.context.view_layer.update()

    # ---- 13. rig test motion (burst 2 replaces it): spine sway + neck yaw as in the template -----
    f0, f1 = scene.frame_start, scene.frame_end
    for bone, keys, axis in (("spine_01", RIG_TEST_SWAY, 0), ("neck", RIG_TEST_YAW, 2)):
        pb = rig.pose.bones[bone]
        pb.rotation_mode = "XYZ"
        for frac, val in keys:
            rot = [0.0, 0.0, 0.0]
            rot[axis] = val
            pb.rotation_euler = rot
            pb.keyframe_insert(data_path="rotation_euler", frame=round(f0 + frac * (f1 - f0)))
    scene.frame_set(f0)
    bpy.context.view_layer.update()

    # ---- 14. self-checks and save -------------------------------------------------------------------
    hr = [(head.matrix_world @ head.data.vertices[i].co) for i in range(len(head.data.vertices)) if any(g.group == head.vertex_groups["SOCKET_BOUNDARY"].index for g in head.data.vertices[i].groups)]
    if len(hr) != len(ring_idx):
        fail(f"head ring count {len(hr)} != {len(ring_idx)}")
    shells = [o for o in colls["C_HEAD"].all_objects if o.type == "MESH" and "SOCKET_BOUNDARY" in o.vertex_groups]
    if len(shells) != 1:
        fail(f"head shell count {len(shells)}")
    scene["character_build"] = {"script": "build_character.py", "mpfb": f"{mpfb_name} {mpfb_version}", "height_m": args.height,
                                "ring_vertices": len(ring_idx), "ring_centre_m": list(ring_c), "expression_set": EXPRESSION_SET, "keep_env": bool(args.keep_env)}
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print(f"BUILD_OK {out} height={args.height} ring={len(ring_idx)} ring_z={ring_c.z:.4f} body_verts={len(body.data.vertices)} "
          f"head_verts={len(head.data.vertices)} hair_verts={len(hair.data.vertices)} bones={len(arm.bones)} blender={bpy.app.version_string}")


if __name__ == "__main__":
    main()
