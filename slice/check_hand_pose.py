"""The hand-over-the-face pose, measured on the shot file — ACCEPTANCE item 4 of burst 2 as the owner approved
it on 2026-09-26 (option 1): the hand comes from below and in front, the elbow down at chest height, the
palm on the eyes. SHOT_003 v02 checkpoint 2 solved the pose numerically against the eye alone and got an
arm that no arm can do: the elbow 206 mm above the shoulder, the wrist bent 85°, the forearm through the
head and the hand 15 mm under the skin — and the foreground hand plate, cut by the head, lost 23 % of the
hand. Per frame of the window (state_map hand_over_face unless --frames), from the .blend, the file never
saved:

  geometry (the arm that holds C_HAND_FG — the side whose wrist is nearest the hand mesh):
    elbow_above_shoulder_mm   elbow height above the shoulder joint along the body's up axis
    elbow_angle_deg           interior angle upper arm / forearm (180 = straight)
    wrist_bend_deg            angle between the forearm and the hand
    forearm_inside_head       samples of the elbow→wrist segment inside the head skin
  penetration (flat Workbench renders from the shot camera, no AA; and vertex distances):
    behind_head               hand-silhouette pixels where the head or the hair is drawn IN FRONT of the hand —
                              the pixels the foreground plate loses, which every order's head shows through
    behind_body               the same against C_BODY (reported, not gated: a sleeve cuff may cross the wrist)
    clearance_mm              nearest distance of any hand vertex to the head skin (negative = inside; the skin is the
                              one closed mesh — the hair strands and the dress are open shells, which the render covers)

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


def geometry(rig, hand, dg, skin):
    pb = rig.pose.bones
    M = rig.matrix_world
    sides = [s for s in ("L", "R") if all(ARM[k].format(s=s) in pb for k in ARM)]
    if not sides or "spine_01" not in pb:
        return {"status": "NOT_APPLICABLE", "why": "the rig has no upperarm01/lowerarm01/wrist chain"}
    he = hand.evaluated_get(dg)
    hc = he.matrix_world @ (sum((v.co for v in he.data.vertices), he.data.vertices[0].co * 0) / len(he.data.vertices))
    side = min(sides, key=lambda s: (M @ pb[ARM["wrist"].format(s=s)].head - hc).length)
    sh, el, wr = (M @ pb[ARM[k].format(s=side)].head for k in ("shoulder", "elbow", "wrist"))
    fin = M @ pb[ARM["wrist"].format(s=side)].tail
    spine = [n for n in ("spine_05", "spine_04", "spine_03", "spine_02", "spine_01") if n in pb]
    up = ((M @ pb[spine[0]].tail) - (M @ pb["spine_01"].head)).normalized()
    ua, fa, ha = el - sh, wr - el, fin - wr
    inside = sum(1 for i in range(21) if (d := inside_depth(el + fa * (i / 20), skin, dg)) is not None and d < 0)
    return {"status": "MEASURED", "side": side, "elbow_above_shoulder_mm": round(1000 * ua.dot(up), 1),
            "elbow_angle_deg": round(float(np.degrees(ua.angle(fa))), 1), "wrist_bend_deg": round(float(np.degrees(fa.angle(ha))), 1),
            "forearm_inside_head_of_21": inside}


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
        geo = geometry(rig, hand, dg, skin) if rig else {"status": "NOT_APPLICABLE", "why": "no RIG_HERO"}
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
        if row["clearance_mm"] < REQ["clearance_mm_min"]:
            bad.append(f"clearance {row['clearance_mm']} mm < {REQ['clearance_mm_min']}")
        if geo["status"] == "MEASURED":
            if geo["elbow_above_shoulder_mm"] > REQ["elbow_above_shoulder_mm_max"]:
                bad.append(f"elbow {geo['elbow_above_shoulder_mm']} mm above the shoulder > {REQ['elbow_above_shoulder_mm_max']}")
            lo, hi = REQ["elbow_angle_deg_range"]
            if not lo <= geo["elbow_angle_deg"] <= hi:
                bad.append(f"elbow angle {geo['elbow_angle_deg']} outside {lo}-{hi}")
            if geo["wrist_bend_deg"] > REQ["wrist_bend_deg_max"]:
                bad.append(f"wrist bend {geo['wrist_bend_deg']} > {REQ['wrist_bend_deg_max']}")
            if geo["forearm_inside_head_of_21"]:
                bad.append(f"forearm inside the head on {geo['forearm_inside_head_of_21']}/21 samples")
        row["failed"] = bad
        rows.append(row)
        if bad:
            failed.append(f)
        g = (f"elbow {geo['elbow_above_shoulder_mm']:+.0f}mm angle {geo['elbow_angle_deg']:.0f} wrist {geo['wrist_bend_deg']:.0f} "
             f"forearm_in_head {geo['forearm_inside_head_of_21']}/21") if geo["status"] == "MEASURED" else "joints=NOT_APPLICABLE"
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
