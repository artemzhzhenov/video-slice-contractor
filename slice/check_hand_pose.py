"""The hand-over-the-face pose, measured on the shot file — ACCEPTANCE item 4 of burst 2 as the owner approved
it on 2026-09-26 (option 1): the hand comes from below and in front, the elbow down at chest height, the
palm on the eyes. SHOT_003 v02 checkpoint 2 solved the pose numerically against the eye alone and got an
arm that no arm can do: the elbow 206 mm above the shoulder, the wrist bent 85°, the forearm through the
head and the hand 15 mm under the skin — and the foreground hand plate, cut by the head, lost 23 % of the
hand. Per frame of the window (state_map hand_over_face unless --frames), from the .blend, the file never
saved:

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
    elbow_flexion             the forearm folds in the hinge's flexion direction: −(arm plane normal · the
                              forearm bone's local X axis), +1 for a flexed elbow, −1 for one folded backwards
                              (the rig's convention: flexion is a negative X rotation on lowerarm01)
    forearm_up / forearm_in   the forearm's direction: rising diagonally towards the face, not vertical
    wrist_bend_deg            angle between the forearm and the hand
    forearm_inside_head       samples of the elbow→wrist segment inside the head skin
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
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
REQ = json.loads((ROOT / "slice" / "state_requirements.json").read_text())["hand_pose"]
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


def arm_frame(rig, side, cam):
    """Body frame and arm points: up along the spine, out towards the arm's own shoulder, forward towards the camera's
    side of the body (the character faces the camera in every shot of the slice), the arm's joints, the arm plane's
    normal and the forearm's hinge axis."""
    pb = rig.pose.bones
    M = rig.matrix_world
    R = M.to_3x3()
    sh, el, wr = (M @ pb[ARM[k].format(s=side)].head for k in ("shoulder", "elbow", "wrist"))
    fin = M @ pb[ARM["wrist"].format(s=side)].tail
    spine = [n for n in ("spine_05", "spine_04", "spine_03", "spine_02", "spine_01") if n in pb]
    up = ((M @ pb[spine[0]].tail) - (M @ pb["spine_01"].head)).normalized()
    sl, sr = M @ pb["shoulder_l"].tail, M @ pb["shoulder_r"].tail   # the clavicles' ends: the shoulder joints
    out = (sl - sr).normalized() * (1 if side == "L" else -1)
    out = (out - up * out.dot(up)).normalized()
    fwd = up.cross(out)
    mid = (sl + sr) / 2
    if fwd.dot(cam.matrix_world.translation - mid) < 0:
        fwd = -fwd
    ua, fa, ha = el - sh, wr - el, fin - wr
    normal = ua.cross(fa)
    hinge = (R @ pb[ARM["elbow"].format(s=side)].x_axis).normalized()
    return {"sh": sh, "el": el, "wr": wr, "up": up, "out": out, "fwd": fwd, "mid": mid, "ua": ua, "fa": fa, "ha": ha,
            "flexion": -normal.normalized().dot(hinge) if normal.length > 1e-9 else 0.0}


def geometry(rig, hand, dg, skin, cam):
    side = arm_side(rig, hand, dg)
    if side is None:
        return {"status": "NOT_APPLICABLE", "why": "the rig has no upperarm01/lowerarm01/wrist chain with shoulder_l/r and spine_01"}
    a = arm_frame(rig, side, cam)
    ua, fa, ha = a["ua"], a["fa"], a["ha"]
    fd = fa.normalized()
    inside = sum(1 for i in range(21) if (d := inside_depth(a["el"] + fa * (i / 20), skin, dg)) is not None and d < 0)
    return {"status": "MEASURED", "side": side, "elbow_above_shoulder_mm": round(1000 * ua.dot(a["up"]), 1),
            "elbow_from_midline_mm": round(1000 * (a["el"] - a["mid"]).dot(a["out"]), 1), "elbow_out_from_shoulder_mm": round(1000 * ua.dot(a["out"]), 1),
            "elbow_forward_mm": round(1000 * ua.dot(a["fwd"]), 1),
            "elbow_angle_deg": round(float(np.degrees(ua.angle(fa))), 1), "elbow_flexion": round(a["flexion"], 3),
            "forearm_up": round(fd.dot(a["up"]), 3), "forearm_in": round(-fd.dot(a["out"]), 3),
            "wrist_bend_deg": round(float(np.degrees(fa.angle(ha))), 1), "forearm_inside_head_of_21": inside}


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
    if geo["forearm_inside_head_of_21"]:
        bad.append(f"forearm inside the head on {geo['forearm_inside_head_of_21']}/21 samples")
    return bad


def signed_to_tree(tree, p):
    """Signed distance of world point p to a world-space BVH tree (negative = inside)."""
    loc, nrm, _, _ = tree.find_nearest(p, 0.5)
    return (p - loc).length * (-1 if (p - loc).dot(nrm) < 0 else 1) if loc is not None else 0.5


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default=None)
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
    body = meshes("C_BODY", exclude=("PROXY", "RIG_", "SOCKET", "FACE_CTRL"))
    rig = bpy.data.objects.get("RIG_HERO")
    setup_flat(sc)
    rows, failed = [], []
    for f in frames_of(a.shot, a.frames):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        geo = geometry(rig, hand, dg, skin, sc.camera) if rig else {"status": "NOT_APPLICABLE", "why": "no RIG_HERO"}
        H = render(sc, {hand.name}, set(), out / f"hand_{f}.png")
        n = int(H.sum())
        if not n:
            raise HandPoseError(f"frame {f}: the hand is not in frame")
        Vh = render(sc, {hand.name}, {o.name for o in head_meshes}, out / f"hand_head_{f}.png")
        Vb = render(sc, {hand.name}, {o.name for o in body}, out / f"hand_body_{f}.png")
        he = hand.evaluated_get(dg)
        clear = min(d for v in he.data.vertices if (d := inside_depth(he.matrix_world @ v.co, skin, dg)) is not None)
        row = {"frame": f, "hand_px": n, "behind_head": round(float((H & ~Vh).sum()) / n, 4), "behind_body": round(float((H & ~Vb).sum()) / n, 4),
               "clearance_mm": round(1000 * clear, 1), **{"geometry": geo}}
        bad = []
        if row["behind_head"] > REQ["behind_head_fraction_max"]:
            bad.append(f"behind_head {row['behind_head']:.3f} > {REQ['behind_head_fraction_max']}")
        c0, c1 = REQ["clearance_mm_range"]
        if not c0 <= row["clearance_mm"] <= c1:
            bad.append(f"clearance {row['clearance_mm']} mm outside {c0}-{c1} (the palm on the face, not in it)")
        bad += geometry_failures(geo, REQ)
        row["failed"] = bad
        rows.append(row)
        if bad:
            failed.append(f)
        g = (f"elbow up {geo['elbow_above_shoulder_mm']:+.0f} out {geo['elbow_out_from_shoulder_mm']:+.0f} fwd {geo['elbow_forward_mm']:+.0f}mm "
             f"angle {geo['elbow_angle_deg']:.0f} flex {geo['elbow_flexion']:+.2f} forearm up {geo['forearm_up']:.2f} in {geo['forearm_in']:.2f} "
             f"wrist {geo['wrist_bend_deg']:.0f} in_head {geo['forearm_inside_head_of_21']}/21") if geo["status"] == "MEASURED" else "joints=NOT_APPLICABLE"
        print(f"HAND_POSE_FRAME {f} {'FAIL' if bad else 'PASS'} behind_head={row['behind_head']:.3f} behind_body={row['behind_body']:.3f} "
              f"clearance={row['clearance_mm']:+.1f}mm {g}" + (" — " + "; ".join(bad) if bad else ""))
    status = "FAIL" if failed else "OK"
    report = {"shot_id": a.shot, "rule": REQ, "frames": rows, "failed_frames": failed, "status": status,
              "joints": rows[0]["geometry"]["status"] if rows else None}
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1) + "\n")
    print(f"HAND_POSE_{status} {a.shot} {len(rows)} frames, {len(failed)} failed; joints {report['joints']}")
    if failed:
        sys.exit(2)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(argv)
    except (HandPoseError, KeyError, OSError, ValueError) as e:
        print(f"HAND_POSE_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
