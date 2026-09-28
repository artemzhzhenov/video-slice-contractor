"""The hand-over-the-face pose, measured on the shot file — ACCEPTANCE item 4 of burst 2 as the owner approved
it on 2026-09-26 (option 1): the hand comes from below and in front, the elbow down at chest height, the
palm on the eyes. SHOT_003 v02 checkpoint 2 solved the pose numerically against the eye alone and got an
arm that no arm can do: the elbow 206 mm above the shoulder, the wrist bent 85°, the forearm through the
head and the hand 15 mm under the skin — and the foreground hand plate, cut by the head, lost 23 % of the
hand. From the .blend, the file never saved, on two sets of frames:

  the hold      the hand_over_face window (state_map, or --frames): every rule below;
  every frame   of the shot (conventions → shots, or --transit): the collision rules alone — no hand vertex
                inside the skin, the forearm outside the head, no hand pixel behind the head or the hair. The
                approach and the release move the arm between poses the hold rules do not describe, and they
                can still run it through the head (SHOT_003 v03 in progress: 137 hand and forearm points inside
                the skin on 1303, an approach the first two gate versions never looked at). A frame whose hand
                is out of shot has nothing to cut from the plate and passes the render rule vacuously.


  geometry (the arm that holds C_HAND_FG — the side whose wrist is nearest the hand mesh), in the body's
  frame — up along the spine, out towards that arm's shoulder, forward calibrated by the camera:
    elbow_above_shoulder_mm   elbow height above the shoulder joint
    elbow_from_midline_mm     elbow's distance from the body's midline towards its own side (negative = the arm
                              thrown across the chest — checkpoint 3 had −100 mm with the forearm vertical)
    elbow_out_from_shoulder_mm  elbow outside the shoulder joint, to the arm's own side — the upper arm abducted
                              out, near horizontal, as in the owner's reference photo (2026-09-26 "elbow": the hand
                              to the head from the side, the elbow out at shoulder height, not in front of the chest)
    elbow_forward_mm          elbow in front of the shoulder joint
    elbow_angle_deg           interior angle upper arm / forearm (180 = straight)
    elbow_flexion             the forearm folds in the hinge's flexion direction: (arm plane normal · the
                              forearm bone's local X axis), +1 for a flexed elbow, −1 for one folded backwards.
                              On this MPFB rig flexion is a POSITIVE X rotation on lowerarm01 — measured on the rig
                              2026-09-28: with the rest's upper arm, X +30/+60/+90 brings the forearm forward and up
                              to the face, X −40 straightens it and X −90 bends it 42° backwards. Gates v2–v6 had the
                              sign the other way round (read off checkpoint 3's arm, not measured): our hold (path A)
                              and every transit since reached the face with the elbow bent ~100° backwards and the
                              humerus turned ~180° about itself to point it forwards — the owner's "the shoulder slides
                              inwards" on variants C/D, the sleeve collapsing and tearing at the armpit
    humerus_twist_deg /       the upper arm's and the forearm's rotation about their own axes against the rig's
    forearm_twist_deg         rest (upperarm01 + upperarm02, lowerarm02 + wrist; the twist part of each local
                              rotation): a living arm turns about 70–90° each way; at most twist_deg_max on EVERY
                              frame. Our old hold had the humerus at −196°
    forearm_up / forearm_in   the forearm's direction: rising diagonally towards the face, not vertical
    wrist_bend_deg            angle between the forearm and the hand
    forearm_inside_head       samples of the elbow→wrist segment inside the head skin
  the hand itself (every frame; a rig without finger bones reports NOT_APPLICABLE) — SHOT_003 v03 shipped the
  fingers in the rig's rest pose, straight and splayed with the thumb 51° off the index: "four fingers", the
  owner said, the pinky hidden behind the rest:
    thumb_spread_deg          angle between the thumb's first bone and the index metacarpal
    finger_curl_deg           mean bend at the first knuckle of fingers 2-5, in each finger's own flexion plane
    finger_lateral_deg        the largest sideways bend at a middle or end knuckle (finger k-2, k-3): the part of the
                              phalanx's pose rotation that is not about its own X, the hinge: these joints are hinges. v05's hand bent the middle
                              phalanges 20–30° sideways towards each other — the owner's "the fingers stuck
                              together" — and the old curl measure counted the sideways bend as curl
    finger_splay_deg          angle between the index and the pinky metacarpals
  motion (every frame): wrist_speed_mm_per_frame — the wrist joint's travel since the previous frame of the
    run; v03 flung the hand to the face at 216 mm/frame and dropped it at 155 (the release "like a stick")
  the raised hand (every frame): wrist_above_shoulder_mm — a hand raised above the shoulder joint is up only AT
    the face: more than raised_wrist_above_shoulder_mm up and more than raised_clearance_mm_max off the skin
    fails. v04's approach held the forearm level across the face (1294–1297, 53–120 mm off it) and its release
    left the hand up in the air as the head turned away (1339–1346, 69–118 mm) — a raised arm on screen
  the body (every frame): inside_body — the near arm's points inside the body: the hand (C_HAND_FG) and the arm (the
    vertices of C_BODY's meshes weighted to that side's upperarm02 / lowerarm01-02 / wrist, the elbow and the forearm)
    against every other surface of C_BODY (the near arm's own faces left out: the dress, the far arm, the neck). A
    point is inside a mesh when its generalized winding number (Jacobson et al. 2013) is above 0.5 in magnitude — the
    shells are open (a dress at the neck, the armholes and the hem; a skin whose torso the clothes replaced) and one
    of them is wound inward, so the nearest face's normal lies; how deep, by the distance to that mesh. No point
    deeper than body_inside_depth_mm_max: the contractor's hanging arm presses its sleeve up to 15 mm into the dress's
    side (1280) — cloth against cloth, hidden between the arm and the body. The frame's own controls — the spine's
    midpoint inside, a point 300 mm in front of it outside — or the frame is not measured. SHOT_003 v05 (our transit table, variant A) ran the forearm and the elbow through the chest on
    1286–1298 and 1343–1353 (the hand wholly in the belly on 1288–1290, through the far arm on 1294–1295) while
    every other rule passed: the render rule is vacuous below the frame, and the head was the only obstacle
  the palm (every frame with the hand in shot): palm_to_camera — the palm's normal (the side the fingers curl
    towards, fingers 2-5) against the direction to the camera; above palm_to_camera_max the open palm faces the
    viewer: v05 raised the hand palm-out like a wave (1293–1299, up to 0.89) and turned it out again on the way
    down (1339–1344) — the owner's "it turns the wrong way"; the palm on the eyes reads −0.54
  MEDIUM windows (TASK §6 rule 3, state_map tiers): no hand on the face — hand_over_head, the head + hair
    silhouette's pixels with the hand in front of them (flat renders), at most medium_hand_over_head_max on
    every frame of a MEDIUM window. The body is not gated here: the dress collar always covers a sliver of the
    neck, which belongs to the head's silhouette (0.2–0.5 %). v04 covered the head up to 0.21 in fear
  penetration (flat Workbench renders from the shot camera, no AA; and vertex distances):
    behind_head               hand-silhouette pixels where the head or the hair is drawn IN FRONT of the hand —
                              the pixels the foreground plate loses, which every order's head shows through
    behind_body               the same against C_BODY (reported, not gated: a sleeve cuff may cross the wrist)
    clearance_mm              nearest distance of any hand vertex to the head skin: 0–15 mm — not inside the skin, and ON
                              the face, the palm on the eyes (the 5 mm floor of 2026-09-26 morning contradicted the
                              gesture: checkpoint 3 hung the hand 39 mm off the face); the skin is the one closed mesh —
                              the hair strands and the dress are open shells, which the render covers

Limits live in slice/state_requirements.json → hand_pose. A rig without the arm chain reports the geometry as
NOT_APPLICABLE (never as a pass) and the gate rests on the penetration alone.

    blender -b SHOT_003_vNN.blend --python-exit-code 2 -P slice/check_hand_pose.py -- --shot SHOT_003 \\
        --out <dir> [--frames 1305-1332] [--json out.json]

Prints HAND_POSE_FRAME per frame and HAND_POSE_OK / HAND_POSE_FAIL; exit 2 on FAIL or when it cannot measure."""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
REQ = json.loads((ROOT / "slice" / "state_requirements.json").read_text())["hand_pose"]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
ARM = {"shoulder": "upperarm01.{s}", "elbow": "lowerarm01.{s}", "wrist": "wrist.{s}"}


class HandPoseError(Exception):
    pass


def frames_of(shot, spec):
    if spec:
        f0, f1 = (int(x) for x in spec.split("-"))
        return list(range(f0, f1 + 1))
    sm = json.loads((ROOT / "slice" / "state_map.json").read_text())
    win = [w for w in sm["windows"] if w["shot_id"] == shot and w["state"] == "hand_over_face"]
    if len(win) != 1:
        raise HandPoseError(f"{shot}: expected one hand_over_face window in state_map.json, found {len(win)}")
    (f0, f1), = win[0]["frames"]
    return list(range(f0, f1 + 1))


def shot_frames(shot, spec):
    if spec:
        f0, f1 = (int(x) for x in spec.split("-"))
        return list(range(f0, f1 + 1))
    if shot not in CONV["shots"]:
        raise HandPoseError(f"{shot}: not in conventions.json → shots")
    r = CONV["shots"][shot]["frame_range"]
    return list(range(r["start"], r["end"] + 1))


def medium_frames(shot):
    """Frames of the shot's MEDIUM-tier windows (state_map tiers)."""
    sm = json.loads((ROOT / "slice" / "state_map.json").read_text())
    medium = set(sm["tiers"]["MEDIUM"])
    return {f for w in sm["windows"] if w["shot_id"] == shot and w["state"] in medium for a, b in w["frames"] for f in range(a, b + 1)}


def collision_failures(row, geo, req):
    """The rules that hold on every frame of the shot, the approach and the release included."""
    bad = []
    if row["behind_head"] > req["behind_head_fraction_max"]:
        bad.append(f"behind_head {row['behind_head']:.3f} > {req['behind_head_fraction_max']}")
    if row["clearance_mm"] < req["clearance_mm_range"][0]:
        bad.append(f"clearance {row['clearance_mm']} mm — the hand inside the skin")
    if geo["status"] == "MEASURED" and geo["forearm_inside_head_of_21"]:
        bad.append(f"forearm inside the head on {geo['forearm_inside_head_of_21']}/21 samples")
    if (geo["status"] == "MEASURED" and geo["wrist_above_shoulder_mm"] > req["raised_wrist_above_shoulder_mm"]
            and row["clearance_mm"] > req["raised_clearance_mm_max"]):
        bad.append(f"the hand raised {geo['wrist_above_shoulder_mm']:.0f} mm above the shoulder {row['clearance_mm']} mm off the face "
                   f"(> {req['raised_clearance_mm_max']}) — a raised arm, not a hand at the face")
    if row.get("medium") and row["hand_over_head"] > req["medium_hand_over_head_max"]:
        bad.append(f"hand over the head {row['hand_over_head']:.3f} in a MEDIUM window (> {req['medium_hand_over_head_max']}, TASK §6 rule 3)")
    for part, p in row["inside_body"]["parts"].items():
        if p["max_depth_mm"] > req["body_inside_depth_mm_max"]:
            bad.append(f"the {part} inside the body {p['max_depth_mm']} mm deep > {req['body_inside_depth_mm_max']} ({p['inside']}/{p['of']} points "
                       f"inside: {', '.join(row['inside_body']['hits'].get(part, []))}) — the arm passes through the torso")
    cl = row.get("shoulder_cloth", {"status": "NOT_APPLICABLE"})
    if cl["status"] == "MEASURED" and (cl["area_p5"] < req["cloth_area_p5_min"] or cl["folds"] > req["cloth_folds_max"]):
        bad.append(f"the shoulder's cloth collapsing: 5 % of its faces at {cl['area_p5']} of their rest area (min {req['cloth_area_p5_min']}), "
                   f"{cl['folds']} folds (max {req['cloth_folds_max']}) — the sleeve caving in or tearing at the armhole")
    if geo["status"] == "MEASURED":
        for k, what in (("humerus_twist_deg", "the upper arm"), ("forearm_twist_deg", "the forearm")):
            if abs(geo[k]) > req["twist_deg_max"]:
                bad.append(f"{what} turned {geo[k]:+.0f} deg about itself (> {req['twist_deg_max']}) — past what a living arm turns")
    p = geo.get("palm_to_camera") if geo["status"] == "MEASURED" else None
    if p is not None and row["hand_px"] and p > req["palm_to_camera_max"]:
        bad.append(f"the palm open to the viewer {p:+.2f} > {req['palm_to_camera_max']} — a wave, not a hand going to the face")
    return bad


def meshes(coll, exclude=()):
    return [o for o in bpy.data.collections[coll].all_objects if o.type == "MESH" and not o.hide_render
            and not any(x in o.name for x in exclude)]


def inside_depth(p, obj, dg):
    """Signed distance of world point p to obj's evaluated surface: negative when inside."""
    ev = obj.evaluated_get(dg)
    bvh = BVHTree.FromObject(ev, dg)
    lp = ev.matrix_world.inverted() @ p
    loc, nrm, _, dist = bvh.find_nearest(lp)
    if loc is None:
        return None
    d = (ev.matrix_world @ loc - p).length
    return -d if (lp - loc).dot(nrm) < 0 else d


def setup_flat(sc):
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light, sh.color_type = "FLAT", "OBJECT"
    sh.show_shadows = sh.show_cavity = sh.show_object_outline = sh.show_specular_highlight = False
    sc.display.render_aa = "OFF"
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
    sc.render.use_motion_blur = False
    sc.view_settings.view_transform = "Raw"
    sc.render.image_settings.media_type = "IMAGE"
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGBA"


def mask(path):
    img = bpy.data.images.load(str(path))
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(-1, 4)
    return (px[:, 0] > 0.5) & (px[:, 3] > 0.5)


def render(sc, white, black, path):
    for o in bpy.data.objects:
        o.hide_render = o.name not in white | black
        o.color = (1, 1, 1, 1) if o.name in white else (0, 0, 0, 1)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return mask(path)


def arm_side(rig, hand, dg):
    """The side whose wrist is nearest the hand mesh, or None when the rig lacks the chain."""
    pb = rig.pose.bones
    sides = [s for s in ("L", "R") if all(ARM[k].format(s=s) in pb for k in ARM)]
    if not sides or "spine_01" not in pb or "shoulder_l" not in pb or "shoulder_r" not in pb:
        return None
    he = hand.evaluated_get(dg)
    hc = he.matrix_world @ (sum((v.co for v in he.data.vertices), he.data.vertices[0].co * 0) / len(he.data.vertices))
    return min(sides, key=lambda s: (rig.matrix_world @ pb[ARM["wrist"].format(s=s)].head - hc).length)


def body_axes(rig, cam):
    """Up along the spine, left-right across the shoulder joints (towards the left one), forward towards the camera's
    side of the body (the character faces the camera in every shot of the slice), the shoulders' midpoint."""
    pb = rig.pose.bones
    M = rig.matrix_world
    spine = [n for n in ("spine_05", "spine_04", "spine_03", "spine_02", "spine_01") if n in pb]
    up = ((M @ pb[spine[0]].tail) - (M @ pb["spine_01"].head)).normalized()
    sl, sr = M @ pb["shoulder_l"].tail, M @ pb["shoulder_r"].tail   # the clavicles' ends: the shoulder joints
    lr = (sl - sr).normalized()
    lr = (lr - up * lr.dot(up)).normalized()
    fwd = up.cross(lr)
    mid = (sl + sr) / 2
    if fwd.dot(cam.matrix_world.translation - mid) < 0:
        fwd = -fwd
    return up, lr, fwd, mid


def arm_frame(rig, side, cam):
    """Body frame and arm points: up along the spine, out towards the arm's own shoulder, forward towards the camera's
    side of the body (the character faces the camera in every shot of the slice), the arm's joints, the arm plane's
    normal and the forearm's hinge axis."""
    pb = rig.pose.bones
    M = rig.matrix_world
    R = M.to_3x3()
    sh, el, wr = (M @ pb[ARM[k].format(s=side)].head for k in ("shoulder", "elbow", "wrist"))
    fin = M @ pb[ARM["wrist"].format(s=side)].tail
    up, lr, fwd, mid = body_axes(rig, cam)
    out = lr * (1 if side == "L" else -1)
    ua, fa, ha = el - sh, wr - el, fin - wr
    normal = ua.cross(fa)
    hinge = (R @ pb[ARM["elbow"].format(s=side)].x_axis).normalized()
    return {"sh": sh, "el": el, "wr": wr, "up": up, "out": out, "fwd": fwd, "mid": mid, "ua": ua, "fa": fa, "ha": ha,
            "flexion": normal.normalized().dot(hinge) if normal.length > 1e-9 else 0.0}


FINGERS = {"thumb": "finger1-1.{s}", "index": "finger2-1.{s}", "pinky": "finger5-1.{s}"}


def hand_shape(rig, side):
    """The fingers' pose: thumb spread, first-knuckle curl of fingers 2-5 in each finger's flexion plane, the largest
    sideways bend at a middle or end knuckle, index-pinky splay (degrees)."""
    pb = rig.pose.bones
    M = rig.matrix_world
    need = [FINGERS[k].format(s=side) for k in FINGERS] + [f"finger{k}-{j}.{side}" for k in (2, 3, 4, 5) for j in (1, 2)]
    if not all(n in pb for n in need) or f"wrist.{side}" not in pb:
        return {"status": "NOT_APPLICABLE", "why": "the rig has no wrist / finger1-1 / finger2-1..finger5-2 chain"}
    d = lambda n: ((M @ pb[n].tail) - (M @ pb[n].head)).normalized()  # noqa: E731
    thumb = float(np.degrees(d(FINGERS["thumb"].format(s=side)).angle(d(FINGERS["index"].format(s=side)))))
    along = d(f"wrist.{side}")
    across = (M @ pb[f"finger5-1.{side}"].head) - (M @ pb[f"finger2-1.{side}"].head)
    across = (across - along * across.dot(along)).normalized()
    normal = along.cross(across)
    curls, lateral = [], 0.0
    for k in (2, 3, 4, 5):
        d1 = d(f"finger{k}-1.{side}")
        m = d1.cross(normal).normalized()          # the finger's sideways axis: out of its flexion plane
        d2 = d(f"finger{k}-2.{side}")
        curls.append(np.degrees(d1.angle((d2 - m * d2.dot(m)).normalized())))
        for j in (2, 3):
            n = f"finger{k}-{j}.{side}"
            if n in pb:
                # a middle / end knuckle is a hinge about the phalanx's own X (measured on this rig 2026-09-28: X
                # curls every phalanx towards the palm, Z moves it sideways): whatever its pose turns about any other
                # axis is a sideways bend. The rig's own fingers converge a little as they curl — not counted.
                q = pb[n].matrix_basis.to_quaternion()
                hinge = Quaternion((q.w, q.x, 0.0, 0.0)).normalized() if abs(q.w) + abs(q.x) > 1e-9 else Quaternion()
                lateral = max(lateral, float(np.degrees((q @ hinge.inverted()).angle)))
    splay = float(np.degrees(d(FINGERS["index"].format(s=side)).angle(d(FINGERS["pinky"].format(s=side)))))
    return {"status": "MEASURED", "thumb_spread_deg": round(thumb, 1), "finger_curl_deg": round(float(np.mean(curls)), 1),
            "finger_lateral_deg": round(lateral, 1), "finger_splay_deg": round(splay, 1)}


def axial_twist_deg(pbone):
    """A pose bone's rotation about its own Y axis against its rest (the twist of a swing-twist split)."""
    q = pbone.matrix_basis.to_quaternion()
    return float(np.degrees(2 * np.arctan2(q.y, q.w)))


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def palm_normal(rig, side):
    """The palm's outward normal: where fingers 2-5 curl to — each second phalanx's direction off its first's, summed.
    Anatomical, so no rig's bone rolls or axis conventions enter; None when the fingers are too straight to say."""
    pb = rig.pose.bones
    M = rig.matrix_world
    if not all(f"finger{k}-{j}.{side}" in pb for k in (2, 3, 4, 5) for j in (1, 2)):
        return None
    acc = None
    for k in (2, 3, 4, 5):
        a = ((M @ pb[f"finger{k}-1.{side}"].tail) - (M @ pb[f"finger{k}-1.{side}"].head)).normalized()
        b = ((M @ pb[f"finger{k}-2.{side}"].tail) - (M @ pb[f"finger{k}-2.{side}"].head)).normalized()
        p = b - a * b.dot(a)
        acc = p if acc is None else acc + p
    return acc.normalized() if acc.length > 0.1 else None   # ~6 deg of mean curl


BODY_EXCLUDE = ("PROXY", "RIG_", "SOCKET", "FACE_CTRL")
DISTAL = ("upperarm02", "lowerarm01", "lowerarm02", "wrist")   # the elbow and the forearm


def side_weight(obj, v, side, names, hand_bones):
    s = 0.0
    for g in v.groups:
        base, _, sfx = obj.vertex_groups[g.group].name.rpartition(".")
        if sfx == side and (base in names or (hand_bones and base.startswith(("finger", "metacarpal", "thumb")))):
            s += g.weight
    return s


def body_setup(body, side):
    """Per mesh of C_BODY, once: the polygons kept as obstacles (none of their vertices owned by the near arm — its
    upper arm, forearm, wrist and hand bones) and the vertices that are the near arm's elbow and forearm."""
    near = ("upperarm01",) + DISTAL
    out = []
    for o in body:
        vs = o.data.vertices
        own = np.array([side_weight(o, v, side, near, True) >= 0.5 for v in vs]) if side else np.zeros(len(vs), bool)
        arm = np.array([side_weight(o, v, side, DISTAL, False) >= 0.5 for v in vs]) if side else np.zeros(len(vs), bool)
        keep = np.array([not own[list(p.vertices)].any() for p in o.data.polygons])
        out.append({"obj": o, "keep": keep, "arm": np.nonzero(arm)[0]})
    return out


def world_mesh(obj, dg, tris=False):
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    if len(me.vertices) != len(obj.data.vertices):
        ev.to_mesh_clear()
        raise HandPoseError(f"{obj.name}: its modifiers change the vertex count ({len(obj.data.vertices)} -> {len(me.vertices)}), "
                            "so the arm's vertices cannot be found by their weights")
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    m = np.array(ev.matrix_world)
    co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    lt = pi = None
    if tris:
        me.calc_loop_triangles()
        lt = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", lt)
        pi = np.empty(len(me.loop_triangles), dtype=np.int64)
        me.loop_triangles.foreach_get("polygon_index", pi)
    ev.to_mesh_clear()
    return co, (None if lt is None else lt.reshape(-1, 3)), pi


def winding(tris, pts, chunk=48):
    """Generalized winding number of each point against a triangle soup (Jacobson et al. 2013): about ±1 inside a
    shell whatever its holes (the sign is the faces' orientation), about 0 outside."""
    w = np.zeros(len(pts))
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk, None, :]
        a, b, c = tris[None, :, 0] - p, tris[None, :, 1] - p, tris[None, :, 2] - p
        la, lb, lc = (np.linalg.norm(x, axis=-1) for x in (a, b, c))
        det = np.einsum("pti,pti->pt", a, np.cross(b, c))
        den = (la * lb * lc + np.einsum("pti,pti->pt", a, b) * lc + np.einsum("pti,pti->pt", b, c) * la
               + np.einsum("pti,pti->pt", c, a) * lb)
        w[s:s + chunk] = np.arctan2(det, den).sum(axis=1) / (2 * np.pi)
    return w


def inside_body(setup, hand, rig, dg, fwd, max_points=800):
    """The near arm's hand and arm points inside the body's obstacles on this frame, with the frame's controls."""
    obstacles = []
    arm = []
    for s in setup:
        co, lt, pi = world_mesh(s["obj"], dg, tris=True)
        t = lt[s["keep"][pi]]
        if len(t):
            obstacles.append((s["obj"].name, co[t]))
        arm.append(co[s["arm"]])
    hco, _, _ = world_mesh(hand, dg)
    parts = {"hand": hco, "arm": np.concatenate(arm) if arm else np.zeros((0, 3))}
    pb = rig.pose.bones
    spine = [n for n in ("spine_05", "spine_04", "spine_03", "spine_02", "spine_01") if n in pb]
    mid = np.array(((rig.matrix_world @ pb["spine_01"].head) + (rig.matrix_world @ pb[spine[0]].tail))[:]) / 2
    ctrl = np.array([mid, mid + 0.3 * np.array(fwd[:])])
    cin = np.zeros(2, bool)
    res = {"parts": {}, "hits": {}}
    sub = {k: v[::max(1, -(-len(v) // max_points))] for k, v in parts.items()}
    depth = {k: np.zeros(len(v)) for k, v in sub.items()}     # how far inside, 0 = outside every obstacle
    for name, tris in obstacles:
        cin |= np.abs(winding(tris, ctrl)) > 0.5
        bvh = None
        for k, p in sub.items():
            if not len(p):
                continue
            hit = np.abs(winding(tris, p)) > 0.5
            if hit.any():
                if bvh is None:
                    flat = tris.reshape(-1, 3)
                    bvh = BVHTree.FromPolygons([Vector(v) for v in flat], [(i, i + 1, i + 2) for i in range(0, len(flat), 3)])
                d = np.array([bvh.find_nearest(Vector(x))[3] for x in p[hit]])
                depth[k][hit] = np.maximum(depth[k][hit], d)
                res["hits"].setdefault(k, []).append(f"{name} {int(hit.sum())} to {1000 * d.max():.0f} mm")
    if not cin[0] or cin[1]:
        raise HandPoseError(f"the body-collision controls failed: the spine's midpoint {'inside' if cin[0] else 'NOT inside'} the body, "
                            f"a point 300 mm in front of it {'INSIDE' if cin[1] else 'outside'} — the obstacles are not a body")
    res["parts"] = {k: {"inside": int((v > 0).sum()), "of": len(v), "max_depth_mm": round(1000 * float(v.max()), 1) if len(v) else 0.0}
                    for k, v in depth.items()}
    return res


def cloth_setup(body, side):
    """The cloth around the near shoulder, once: per mesh of C_BODY, the faces with a vertex weighted >= 0.3 to the
    side's shoulder01 / upperarm01 (the sleeve's cap, the dress around the armhole) and their edge-adjacent pairs."""
    out = []
    if not side:
        return out
    for o in body:
        w = np.array([side_weight(o, v, side, ("shoulder01", "upperarm01"), False) >= 0.3 for v in o.data.vertices])
        sel = np.array([w[list(p.vertices)].any() for p in o.data.polygons])
        if not sel.any():
            continue
        e2f = {}
        for p in o.data.polygons:
            if sel[p.index]:
                for e in p.edge_keys:
                    e2f.setdefault(e, []).append(p.index)
        out.append({"obj": o, "sel": np.nonzero(sel)[0], "pairs": np.array([f for f in e2f.values() if len(f) == 2], dtype=np.int64).reshape(-1, 2)})
    return out


def cloth_faces(o, dg):
    """Per-polygon world area and unit normal."""
    co, lt, pi = world_mesh(o, dg, tris=True)
    t = co[lt]
    cr = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = np.zeros(len(o.data.polygons))
    n = np.zeros((len(o.data.polygons), 3))
    np.add.at(a, pi, 0.5 * np.linalg.norm(cr, axis=1))
    np.add.at(n, pi, cr)
    return a, n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def shoulder_cloth(cs, dg, ref):
    """The shoulder's cloth against the reference frame: the 5th percentile of the faces' area ratio (a collapsing
    sleeve cap goes to ~0) and the folds — adjacent faces that turned over (normals now > 120 deg apart, within 60 at
    the reference). NOT_APPLICABLE without cloth weighted to the shoulder."""
    if not cs:
        return {"status": "NOT_APPLICABLE"}
    ratios, folds, npairs = [], 0, 0
    for c in cs:
        a, n = cloth_faces(c["obj"], dg)
        a0, n0 = ref[c["obj"].name]
        ratios.append(a[c["sel"]] / np.maximum(a0[c["sel"]], 1e-12))
        if len(c["pairs"]):
            i, j = c["pairs"][:, 0], c["pairs"][:, 1]
            folds += int(((np.einsum("ij,ij->i", n[i], n[j]) < -0.5) & (np.einsum("ij,ij->i", n0[i], n0[j]) > 0.5)).sum())
            npairs += len(c["pairs"])
    r = np.concatenate(ratios)
    return {"status": "MEASURED", "area_p5": round(float(np.percentile(r, 5)), 3), "area_min": round(float(r.min()), 3), "folds": folds, "of": npairs}


def hand_failures(shape, req):
    bad = []
    if shape["status"] != "MEASURED":
        return bad
    if shape["thumb_spread_deg"] > req["thumb_spread_deg_max"]:
        bad.append(f"thumb spread {shape['thumb_spread_deg']} > {req['thumb_spread_deg_max']} — the thumb sticking out")
    if shape["finger_curl_deg"] < req["finger_curl_deg_min"]:
        bad.append(f"finger curl {shape['finger_curl_deg']} < {req['finger_curl_deg_min']} — the fingers straight, the rig's rest hand")
    lo, hi = req["finger_splay_deg_range"]
    if not lo <= shape["finger_splay_deg"] <= hi:
        bad.append(f"finger splay {shape['finger_splay_deg']} outside {lo}-{hi} — the fingers "
                   + ("spread apart" if shape["finger_splay_deg"] > hi else "pressed together"))
    if shape["finger_lateral_deg"] > req["finger_lateral_deg_max"]:
        bad.append(f"a finger bent {shape['finger_lateral_deg']} deg sideways at a middle or end knuckle > {req['finger_lateral_deg_max']} "
                   "— those joints are hinges")
    return bad


def geometry(rig, hand, dg, skin, cam):
    side = arm_side(rig, hand, dg)
    if side is None:
        return {"status": "NOT_APPLICABLE", "why": "the rig has no upperarm01/lowerarm01/wrist chain with shoulder_l/r and spine_01"}
    a = arm_frame(rig, side, cam)
    ua, fa, ha = a["ua"], a["fa"], a["ha"]
    shape = hand_shape(rig, side)
    fd = fa.normalized()
    inside = sum(1 for i in range(21) if (d := inside_depth(a["el"] + fa * (i / 20), skin, dg)) is not None and d < 0)
    pn = palm_normal(rig, side)
    pb = rig.pose.bones
    tw = lambda *names: round(wrap_deg(sum(axial_twist_deg(pb[n]) for n in names if n in pb)), 1)  # noqa: E731
    return {"palm_to_camera": None if pn is None else round(pn.dot((cam.matrix_world.translation - a["wr"]).normalized()), 3),
            "humerus_twist_deg": tw(f"upperarm01.{side}", f"upperarm02.{side}"), "forearm_twist_deg": tw(f"lowerarm02.{side}", f"wrist.{side}"),"status": "MEASURED", "side": side, "elbow_above_shoulder_mm": round(1000 * ua.dot(a["up"]), 1),
            "elbow_from_midline_mm": round(1000 * (a["el"] - a["mid"]).dot(a["out"]), 1), "elbow_out_from_shoulder_mm": round(1000 * ua.dot(a["out"]), 1),
            "elbow_forward_mm": round(1000 * ua.dot(a["fwd"]), 1),
            "elbow_angle_deg": round(float(np.degrees(ua.angle(fa))), 1), "elbow_flexion": round(a["flexion"], 3),
            "forearm_up": round(fd.dot(a["up"]), 3), "forearm_in": round(-fd.dot(a["out"]), 3),
            "wrist_bend_deg": round(float(np.degrees(fa.angle(ha))), 1), "forearm_inside_head_of_21": inside,
            "wrist_world_mm": [round(1000 * v, 1) for v in a["wr"]], "hand": shape,
            "wrist_above_shoulder_mm": round(1000 * (a["wr"] - a["sh"]).dot(a["up"]), 1)}


def geometry_failures(geo, req):
    """The rules on the measured geometry — shared with slice/measurements/find_hand_hold.py."""
    bad = []
    if geo["status"] != "MEASURED":
        return bad
    if geo["elbow_above_shoulder_mm"] > req["elbow_above_shoulder_mm_max"]:
        bad.append(f"elbow {geo['elbow_above_shoulder_mm']} mm above the shoulder > {req['elbow_above_shoulder_mm_max']}")
    if geo["elbow_from_midline_mm"] < req["elbow_from_midline_mm_min"]:
        bad.append(f"elbow {geo['elbow_from_midline_mm']} mm from the midline — thrown across the chest (min {req['elbow_from_midline_mm_min']})")
    if geo["elbow_out_from_shoulder_mm"] < req["elbow_out_from_shoulder_mm_min"]:
        bad.append(f"elbow {geo['elbow_out_from_shoulder_mm']} mm outside the shoulder < {req['elbow_out_from_shoulder_mm_min']} — the upper arm must swing out to the side, not forward across the chest")
    f0, f1 = req["elbow_forward_mm_range"]
    if not f0 <= geo["elbow_forward_mm"] <= f1:
        bad.append(f"elbow {geo['elbow_forward_mm']} mm forward of the shoulder outside {f0}-{f1}")
    if geo["elbow_flexion"] < req["elbow_flexion_min"]:
        bad.append(f"elbow flexion {geo['elbow_flexion']} < {req['elbow_flexion_min']} — the forearm folded backwards against the hinge")
    u0, u1 = req["forearm_up_range"]
    if not u0 <= geo["forearm_up"] <= u1:
        bad.append(f"forearm up {geo['forearm_up']} outside {u0}-{u1} (diagonal, not vertical or flat)")
    if geo["forearm_in"] < req["forearm_in_min"]:
        bad.append(f"forearm in {geo['forearm_in']} < {req['forearm_in_min']} (it must cross towards the face)")
    lo, hi = req["elbow_angle_deg_range"]
    if not lo <= geo["elbow_angle_deg"] <= hi:
        bad.append(f"elbow angle {geo['elbow_angle_deg']} outside {lo}-{hi}")
    if geo["wrist_bend_deg"] > req["wrist_bend_deg_max"]:
        bad.append(f"wrist bend {geo['wrist_bend_deg']} > {req['wrist_bend_deg_max']}")
    return bad


def signed_to_tree(tree, p):
    """Signed distance of world point p to a world-space BVH tree (negative = inside)."""
    loc, nrm, _, _ = tree.find_nearest(p, 0.5)
    return (p - loc).length * (-1 if (p - loc).dot(nrm) < 0 else 1) if loc is not None else 0.5


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default=None, help="the hold: every rule (default: state_map hand_over_face)")
    ap.add_argument("--transit", default=None, help="the collision rules alone (default: the shot's frame range)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc = bpy.data.scenes["SLICE"]
    bpy.context.window.scene = sc
    hands = meshes("C_HAND_FG")
    if len(hands) != 1:
        raise HandPoseError(f"expected one render-visible mesh in C_HAND_FG, found {[o.name for o in hands]}")
    hand = hands[0]
    head_meshes = meshes("C_HEAD") + meshes("C_HAIR")
    skins = [o for o in meshes("C_HEAD") if o.vertex_groups.get("SOCKET_BOUNDARY")]   # the head shell (conventions → head_shell_rule)
    if len(skins) != 1:
        raise HandPoseError(f"expected one head shell carrying SOCKET_BOUNDARY in C_HEAD, found {[o.name for o in skins]}")
    skin = skins[0]
    body = meshes("C_BODY", exclude=BODY_EXCLUDE)
    rig = bpy.data.objects.get("RIG_HERO")
    if rig is None or not all(n in rig.pose.bones for n in ("spine_01", "shoulder_l", "shoulder_r")):
        raise HandPoseError("the body rule needs RIG_HERO with spine_01 and shoulder_l/r (its controls and forward axis)")
    sc.frame_set(shot_frames(a.shot, a.transit)[0])
    side0 = arm_side(rig, hand, bpy.context.evaluated_depsgraph_get())
    setup = body_setup(body, side0)
    cloth = cloth_setup(body, side0)
    sc.frame_set(shot_frames(a.shot, None)[0])   # the cloth's reference: the shot's first frame (the rest), whatever --transit says
    cloth_ref = {c["obj"].name: cloth_faces(c["obj"], bpy.context.evaluated_depsgraph_get()) for c in cloth}
    setup_flat(sc)
    rows, failed = [], []
    hold = set(frames_of(a.shot, a.frames))
    medium = medium_frames(a.shot)
    prev = None   # (frame, wrist position) of the previous frame of the run, for the wrist speed
    for f in sorted(hold | set(shot_frames(a.shot, a.transit))):
        role = "hold" if f in hold else "transit"
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        geo = geometry(rig, hand, dg, skin, sc.camera) if rig else {"status": "NOT_APPLICABLE", "why": "no RIG_HERO"}
        if geo["status"] == "MEASURED":
            w = np.array(geo["wrist_world_mm"])
            geo["wrist_speed_mm_per_frame"] = round(float(np.linalg.norm(w - prev[1])), 1) if prev and prev[0] == f - 1 else None
            prev = (f, w)
        H = render(sc, {hand.name}, set(), out / f"hand_{f}.png")
        n = int(H.sum())
        if not n and role == "hold":
            raise HandPoseError(f"frame {f}: the hand is not in frame on the hold")
        Vh = render(sc, {hand.name}, {o.name for o in head_meshes}, out / f"hand_head_{f}.png") if n else H
        Vb = render(sc, {hand.name}, {o.name for o in body}, out / f"hand_body_{f}.png") if n else H
        Hd = render(sc, {o.name for o in head_meshes}, set(), out / f"head_{f}.png")     # the head + hair silhouette alone
        nh = int(Hd.sum())
        he = hand.evaluated_get(dg)
        clear = min(d for v in he.data.vertices if (d := inside_depth(he.matrix_world @ v.co, skin, dg)) is not None)
        row = {"frame": f, "role": role, "medium": f in medium, "hand_over_head": round(float((Hd & Vh).sum()) / nh, 4) if (n and nh) else 0.0,
               "hand_px": n, "behind_head": round(float((H & ~Vh).sum()) / n, 4) if n else 0.0,
               "behind_body": round(float((H & ~Vb).sum()) / n, 4) if n else 0.0, "clearance_mm": round(1000 * clear, 1),
               "inside_body": inside_body(setup, hand, rig, dg, body_axes(rig, sc.camera)[2]),
               "shoulder_cloth": shoulder_cloth(cloth, dg, cloth_ref), **{"geometry": geo}}
        bad = collision_failures(row, geo, REQ)
        if geo["status"] == "MEASURED":
            bad += hand_failures(geo["hand"], REQ)
            sp = geo["wrist_speed_mm_per_frame"]
            if sp is not None and sp > REQ["wrist_speed_mm_per_frame_max"]:
                bad.append(f"wrist speed {sp} mm/frame > {REQ['wrist_speed_mm_per_frame_max']} — the hand flung")
        if role == "hold":
            if row["clearance_mm"] > REQ["clearance_mm_range"][1]:
                bad.append(f"clearance {row['clearance_mm']} mm > {REQ['clearance_mm_range'][1]} — the palm off the face")
            bad += [b for b in geometry_failures(geo, REQ)]
        row["failed"] = bad
        rows.append(row)
        if bad:
            failed.append(f)
        g = (f"elbow up {geo['elbow_above_shoulder_mm']:+.0f} out {geo['elbow_out_from_shoulder_mm']:+.0f} fwd {geo['elbow_forward_mm']:+.0f}mm "
             f"angle {geo['elbow_angle_deg']:.0f} flex {geo['elbow_flexion']:+.2f} twist {geo['humerus_twist_deg']:+.0f}/{geo['forearm_twist_deg']:+.0f} "
             f"forearm up {geo['forearm_up']:.2f} in {geo['forearm_in']:.2f} "
             f"wrist {geo['wrist_bend_deg']:.0f} in_head {geo['forearm_inside_head_of_21']}/21 "
             f"speed {geo['wrist_speed_mm_per_frame'] if geo['wrist_speed_mm_per_frame'] is not None else '-'} "
             + (f"hand thumb {geo['hand']['thumb_spread_deg']:.0f} curl {geo['hand']['finger_curl_deg']:.0f} lateral {geo['hand']['finger_lateral_deg']:.0f} splay {geo['hand']['finger_splay_deg']:.0f}"
                if geo["hand"]["status"] == "MEASURED" else "hand=NOT_APPLICABLE")) if geo["status"] == "MEASURED" else "joints=NOT_APPLICABLE"
        ib = " ".join(f"{k} {p['inside']}/{p['of']} {p['max_depth_mm']:.0f}mm" for k, p in row["inside_body"]["parts"].items())
        cl = row["shoulder_cloth"]
        ib += f" cloth {cl['area_p5']:.2f}/{cl['folds']}" if cl["status"] == "MEASURED" else " cloth -"
        palm = geo.get("palm_to_camera") if geo["status"] == "MEASURED" else None
        print(f"HAND_POSE_FRAME {f} {role} {'FAIL' if bad else 'PASS'} behind_head={row['behind_head']:.3f} behind_body={row['behind_body']:.3f} "
              f"clearance={row['clearance_mm']:+.1f}mm in_body {ib} palm_to_camera={'-' if palm is None else f'{palm:+.2f}'} {g}"
              + (" — " + "; ".join(bad) if bad else ""))
    status = "FAIL" if failed else "OK"
    nh = sum(1 for r in rows if r["role"] == "hold")
    fh = sum(1 for r in rows if r["role"] == "hold" and r["failed"])
    report = {"shot_id": a.shot, "rule": REQ, "frames": rows, "failed_frames": failed, "status": status,
              "hold_frames": nh, "transit_frames": len(rows) - nh, "joints": rows[0]["geometry"]["status"] if rows else None,
              "body_points": rows[0]["inside_body"]["parts"] if rows else None,
              "fingers": rows[0]["geometry"].get("hand", {}).get("status") if rows else None}
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1) + "\n")
    body_pts = " ".join(f"{k} {p['of']}" for k, p in (report["body_points"] or {}).items())
    print(f"HAND_POSE_{status} {a.shot} hold {nh} frames, {fh} failed; transit {len(rows) - nh} frames, {len(failed) - fh} failed"
          f"{' (' + ', '.join(str(f) for f in failed[:12]) + (' …' if len(failed) > 12 else '') + ')' if failed else ''}; joints {report['joints']}, fingers {report['fingers']}, "
          f"body points {body_pts}")
    if failed:
        sys.exit(2)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(argv)
    except (HandPoseError, KeyError, OSError, ValueError) as e:
        print(f"HAND_POSE_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
