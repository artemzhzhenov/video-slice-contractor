"""The cheek strand, measured on the model — acceptance of burst-1 v04 (QUESTIONS Q22, Q31, Q32).

    blender -b <character or shot .blend> --python-exit-code 2 -P slice/measure_cheek_strand.py -- \
        --out <dir> [--side R|L] [--frames all|rest|1001,1090]

Why it exists: on 2026-09-17 a strand lying on the cheek was agreed and the owner approved it; the
burst-1 report then described temple strands reaching the outer corner of the eye, and v02 and v03
were accepted without anyone measuring it. Neither version has any hair within 55 mm of either
cheek (`slice/measurements/cheek_strand_character_v02_v03.json`). Acceptance now measures the model.

What it measures, with the thresholds Q31 set:

* **presence** — hair vertices over the cheek on the named side: within 15 mm of the head surface,
  between mouth height and just above the eye, outside the eye and inside the ear line. The window
  is wider than the press limit on purpose: a strand floating off the cheek is still the strand and
  must fail on press, not be reported as absent. A strand is "there" when at least `min_vertices`
  of them exist;
* **press** — the gap between the skin and the strand's INNER side, per 3 mm section along the
  strand (limit 3 mm). Not every vertex: a strand has thickness, and its root is meant to tuck under
  the hair mass. The depth the inner side sinks into the skin is reported and limited at 2 mm;
* **clearance** — the smallest distance from ANY hair vertex near the face to the eye on that side,
  to the brow mesh and to the mouth, in the rest pose and on every frame requested (limit 5 mm).
  Eyes rotate and brows move with the performance, so the rest pose alone is not the answer. The
  mouth is represented by the teeth and tongue meshes — the lip corner has no object of its own, so
  this distance is a lower bound on the clearance to the mouth interior, stated as such.

Hair is rigid on SOCKET_HEAD, so the strand cannot drift; what moves around it is the face.

Controls, run on 2026-09-24 against the delivered v03 and three strands added to copies of it
(`slice/measurements/cheek_strand_controls_2026-09-24.json`): no strand → "no strand"; a strand
on the cheek → PASS; the same strand brushing the outer eye corner → FAIL at 0.43 mm; the strand
floating 6 mm off the skin → FAIL on press. The first near-eye control was degenerate — moving the
path toward the eye centre along the projection ray landed on the same skin — and returned the
good strand's numbers; a control that agrees with the positive case proves nothing.

Exit 0 with STRAND_OK, exit 2 with STRAND_ERROR and the failing measure named."""
import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

LIMITS = {"press_mm_max": 3.0, "clearance_mm_min": 5.0, "min_vertices": 20, "sunk_mm_max": 2.0,
          "status": "PROVISIONAL — Q31 (2026-09-23): press ≤ 3 mm on the cheek, ≥ 5 mm from eye, brow and mouth"}


PRESENCE_WINDOW_MM = 15.0
SECTION_MM = 3.0


class StrandError(Exception):
    pass


def fail(msg):
    print(f"STRAND_ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def tree_of(objs, dg):
    """One BVH tree over the evaluated meshes, in world space — built WITHOUT writing into any mesh.

    The first version wrote the world-space coordinates back into the mesh `to_mesh()` returned
    and read them from there. For an object with no modifiers Blender hands back the object's own
    mesh, not a copy, so every call moved the original again: on 2026-09-24, over the 120 frames
    of a shot the brow mesh drifted until the hair seemed 0.01 mm from it and then left the scene,
    while a single-frame run said 21.69 mm. The transform now happens on a private bmesh copy."""
    bm = bmesh.new()
    for o in objs:
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        part = bmesh.new()
        part.from_mesh(me)                   # a copy: the mesh itself is never written
        eo.to_mesh_clear()
        part.transform(eo.matrix_world)
        scratch = bpy.data.meshes.new("_tree_of_scratch")
        part.to_mesh(scratch)
        part.free()
        bm.from_mesh(scratch)
        bpy.data.meshes.remove(scratch)
    if not bm.faces:
        bm.free()
        return None, None
    bm.normal_update()
    return BVHTree.FromBMesh(bm), bm


def world_verts(o, dg):
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    mw = eo.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    eo.to_mesh_clear()
    return pts


def new_hair_vertices(hair, reference_blend):
    """Indices of the HERO_HAIR vertices absent from the reference character's hair, compared in the
    mesh's own (socket-parented) space, where a rebuild of unchanged strands lands on the same
    coordinates. Loads only the reference's hair mesh, never its scene."""
    from mathutils.kdtree import KDTree
    name = hair.data.name
    before = set(bpy.data.meshes)
    with bpy.data.libraries.load(reference_blend, link=False) as (src, dst):
        if name not in src.meshes:
            raise StrandError(f"{Path(reference_blend).name} has no mesh {name} to compare the hair with")
        dst.meshes = [name]
    ref = next(m for m in bpy.data.meshes if m not in before)
    kd = KDTree(len(ref.vertices))
    for i, v in enumerate(ref.vertices):
        kd.insert(v.co, i)
    kd.balance()
    new = [i for i, v in enumerate(hair.data.vertices) if kd.find(v.co)[2] > 1e-5]
    bpy.data.meshes.remove(ref)
    if not new:
        raise StrandError(f"HERO_HAIR is identical to {Path(reference_blend).name}: there is no new strand")
    return new


def obj(name):
    o = bpy.data.objects.get(name)
    if o is None:
        raise StrandError(f"object {name} missing — this is not the slice character")
    return o


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--side", choices=["R", "L"], default="R",
                    help="the cheek the strand lies on; R = HERO_EYE_R side (-X), the one SHOT_002 shows")
    ap.add_argument("--frames", default="all")
    ap.add_argument("--reference", default=None,
                    help="a character .blend WITHOUT the strand (v03). The strand is then every HERO_HAIR vertex "
                         "that is not in the reference, wherever it lies — root included. Without it the strand is "
                         "whatever hair lies over the cheek zone, which misses a root tucked back behind the temple "
                         "(v04.1, 2026-09-24: 91 of its 228 vertices lay outside the zone)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        sc = bpy.data.scenes.get("SLICE") or fail("scene SLICE missing")
        # Evaluate in the SLICE scene's full view layer, explicitly. The depsgraph comes from the
        # context, and a shot file opened on another scene or view layer evaluates the face drivers
        # there: on 2026-09-24 that gave brow distances jumping 0.01 -> 6.2 mm between frames and 16
        # frames with no brow at all, where a direct per-vertex check found 16-22 mm on every frame.
        bpy.context.window.scene = sc
        bpy.context.window.view_layer = sc.view_layers["L_FULL"]
        head, hair = obj("HERO_HEAD"), obj("HERO_HAIR")
        eye = obj("HERO_EYE_R" if args.side == "R" else "HERO_EYE_L")
        other_eye = obj("HERO_EYE_L" if args.side == "R" else "HERO_EYE_R")
        brows = obj("HERO_BROWS")
        mouth = [o for o in (bpy.data.objects.get(n) for n in ("HERO_TEETH_UPPER", "HERO_TEETH_LOWER", "HERO_TONGUE")) if o]
        if not mouth:
            raise StrandError("no teeth or tongue meshes to stand for the mouth")
        sign = -1.0 if args.side == "R" else 1.0

        arms = [o for o in sc.objects if o.type == "ARMATURE"]
        was = [(a, a.data.pose_position) for a in arms]
        for a in arms:
            a.data.pose_position = "REST"
        sc.frame_set(sc.frame_start)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()

        # --- presence and press, in the rest pose (hair is rigid, the shell is the rest shell) ---
        e = eye.matrix_world.translation.copy()
        e2 = other_eye.matrix_world.translation.copy()
        face_dir = ((e + e2) / 2 - head.matrix_world.translation)
        face_dir.z = 0
        face_dir.normalize()
        ht, hbm = tree_of([head], dg)
        mouth_z = min(p.z for o in mouth for p in world_verts(o, dg))
        hair_pts = world_verts(hair, dg)

        def in_cheek_zone(p):
            return (p.x * sign >= abs(e.x) * 0.5                      # on the named side, outside the nose
                    and mouth_z - 0.005 < p.z < e.z + 0.005            # mouth height up to just above the eye
                    and (p - e).dot(face_dir) >= -0.035)               # no further back than the ear line

        strand_from_reference = None
        if args.reference:
            strand_from_reference = new_hair_vertices(hair, args.reference)
        cheek, in_zone = [], set()
        candidates = strand_from_reference if strand_from_reference is not None else range(len(hair_pts))
        for i in candidates:
            p = hair_pts[i]
            zone = in_cheek_zone(p)
            if strand_from_reference is None and not zone:
                continue
            loc, nrm, _, d = ht.find_nearest(p, 0.05)
            # a wide window on purpose: a strand floating 6 mm off the cheek is still the strand,
            # and it must fail on press, not be reported as absent
            if loc is None or (strand_from_reference is None and d * 1000 > PRESENCE_WINDOW_MM):
                continue
            cheek.append((i, d * 1000))
            if zone:
                in_zone.add(i)
        # Press is the gap between the skin and the strand's INNER side, section by section along
        # the strand. Measured on the delivered v04 (2026-09-24): taking every vertex counts the
        # strand's own thickness (2.4-5.3 mm, tapering) and the root tucked under the hair mass
        # (8.9 mm) as "standing off the skin", while the inner side lies at 0.0-0.45 mm the whole way.
        signed = {}
        for i, _ in cheek:
            loc, nrm, _, _ = ht.find_nearest(hair_pts[i], 0.02)
            signed[i] = (hair_pts[i] - loc).dot(nrm) * 1000.0
        hbm.free()
        sections = []
        if len(cheek) >= 3:
            pts_c = [hair_pts[i] for i, _ in cheek]
            centre = sum(pts_c, pts_c[0] * 0) / len(pts_c)
            # principal direction of the strand: the farthest pair gives it without numpy
            far = max(pts_c, key=lambda q: (q - centre).length)
            axis = (far - centre).normalized()
            bins = {}
            for (i, d), q in zip(cheek, pts_c):
                bins.setdefault(int((q - centre).dot(axis) * 1000 // SECTION_MM), []).append(d)
            sections = [{"section": k, "vertices": len(v), "inner_gap_mm": round(min(v), 2), "outermost_mm": round(max(v), 2)}
                        for k, v in sorted(bins.items())]
        gaps = [sct["inner_gap_mm"] for sct in sections]
        # Sinking is limited only where the strand is on the face: a root that dips into the skin
        # under the hair mass is invisible (v04.1: 3 mm at the ear), a tip that dips into the cheek
        # disappears on camera.
        inside = [v for i, v in signed.items() if v < 0 and i in in_zone]
        inside_hidden = [v for i, v in signed.items() if v < 0 and i not in in_zone]
        presence = {"vertices_on_the_cheek": len(in_zone),
                    "strand_selection": (f"every HERO_HAIR vertex not in {Path(args.reference).name}: "
                                         f"{len(strand_from_reference)}") if strand_from_reference is not None
                    else "hair over the cheek zone",
                    "strand_vertices_measured": len(cheek),
                    "sunk_outside_the_face_zone": {"vertices": len(inside_hidden),
                                                   "deepest_mm": round(min(inside_hidden), 2) if inside_hidden else 0.0,
                                                   "note": "reported, not limited: under the hair mass it cannot be seen"},
                    "press_mm": {"inner_gap_max": max(gaps), "inner_gap_p50": sorted(gaps)[len(gaps) // 2],
                                 "sections": len(sections), "definition": "per 3 mm section along the strand, the vertex closest to the skin"} if gaps else None,
                    "sunk_into_skin": {"vertices": len(inside), "deepest_mm": round(min(inside), 2) if inside else 0.0,
                                       "note": "the inner side crossing the skin is a stable intersection, not coplanar; reported, limited only beyond sunk_mm_max"},
                    "sections": sections}
        # candidates for the clearance check: hair within 40 mm of the eye, brow or mouth at rest
        near = [i for i, p in enumerate(hair_pts)
                if min((p - e).length, min((p - b).length for b in world_verts(brows, dg)[::7]) if brows else 1,
                       min((p - m).length for o in mouth for m in world_verts(o, dg)[::5])) < 0.04]
        for a, pos in was:
            a.data.pose_position = pos

        # --- clearance, rest and every requested frame ---
        if args.frames == "rest":
            frames = []
        elif args.frames == "all":
            frames = list(range(sc.frame_start, sc.frame_end + 1))
        else:
            frames = [int(f) for f in args.frames.split(",")]

        def clearance(dg_, label):
            et, ebm = tree_of([eye], dg_)
            bt, bbm = tree_of([brows], dg_)
            mt, mbm = tree_of(mouth, dg_)
            pts = world_verts(hair, dg_)
            res = {}
            for name, t in (("eye", et), ("brow", bt), ("mouth", mt)):
                best = None
                for i in near:
                    loc, _, _, d = t.find_nearest(pts[i], 0.2) if t else (None, None, None, None)
                    if loc is not None and (best is None or d < best):
                        best = d
                res[name] = round(best * 1000, 2) if best is not None else None
            for b in (ebm, bbm, mbm):
                if b:
                    b.free()
            return res

        for a in arms:
            a.data.pose_position = "REST"
        sc.frame_set(sc.frame_start)
        bpy.context.view_layer.update()
        rest = clearance(bpy.context.evaluated_depsgraph_get(), "rest")
        for a, pos in was:
            a.data.pose_position = pos
        per_frame = []
        for f in frames:
            sc.frame_set(f)
            per_frame.append({"frame": f, **clearance(bpy.context.evaluated_depsgraph_get(), f)})
        # Repeatability, checked on the spot: replay the first frame after all the others and require
        # the same numbers. The first version of the helpers wrote into Blender's evaluated meshes,
        # and over a 120-frame run the brows drifted until hair "touched" them (0.01 mm) while a
        # single-frame run gave 21.69 mm. A placeholder scene would not reproduce it, so the check
        # lives here, where the real asset is measured.
        if per_frame:
            sc.frame_set(per_frame[0]["frame"])
            replay = clearance(bpy.context.evaluated_depsgraph_get(), "replay")
            drift = {k: (None if replay[k] is None or per_frame[0][k] is None else abs(replay[k] - per_frame[0][k]))
                     for k in ("eye", "brow", "mouth")}
            if any(v is None and per_frame[0][k] is not None for k, v in drift.items()) or \
               any(v is not None and v > 1e-3 for v in drift.values()):
                raise StrandError(f"the measurement is not repeatable: frame {per_frame[0]['frame']} gave "
                                  f"{per_frame[0]} first and {replay} after the run — something wrote into "
                                  "the evaluated meshes")
        worst, worst_frame, unmeasured = {}, {}, {}
        for k in ("eye", "brow", "mouth"):
            rows = [("rest", rest[k])] + [(r["frame"], r[k]) for r in per_frame]
            known = [(f, v) for f, v in rows if v is not None]
            # a frame with no hair within reach of the feature is not "far enough": it is unmeasured,
            # and it is counted and reported rather than dropped
            unmeasured[k] = [f for f, v in rows if v is None]
            if known:
                f, v = min(known, key=lambda fv: fv[1])
                worst[k], worst_frame[k] = v, f
            else:
                worst[k], worst_frame[k] = None, None

        failed = []
        if presence["vertices_on_the_cheek"] < LIMITS["min_vertices"]:
            failed.append(f"no strand on the {args.side} cheek: {presence['vertices_on_the_cheek']} hair vertices on its skin "
                          f"(need ≥ {LIMITS['min_vertices']})")
        elif presence["press_mm"]["inner_gap_max"] > LIMITS["press_mm_max"]:
            failed.append(f"the strand stands off the skin: its inner side is {presence['press_mm']['inner_gap_max']} mm "
                          f"away in the worst section (limit {LIMITS['press_mm_max']})")
        elif -presence["sunk_into_skin"]["deepest_mm"] > LIMITS["sunk_mm_max"]:
            failed.append(f"the strand sinks {-presence['sunk_into_skin']['deepest_mm']} mm into the skin "
                          f"(limit {LIMITS['sunk_mm_max']}): its thin tip can vanish into the cheek")
        for k, v in worst.items():
            if v is not None and v < LIMITS["clearance_mm_min"]:
                failed.append(f"hair {v} mm from the {k} on frame {worst_frame[k]} (limit {LIMITS['clearance_mm_min']})")
        report = {"measure": "cheek_strand", "status": "FAIL" if failed else "PASS", "failed": failed,
                  "side": args.side, "limits": LIMITS, "presence_rest_pose": presence,
                  "clearance_mm_rest": rest, "clearance_mm_worst": worst, "worst_frame": worst_frame,
                  "frames_measured": len(frames), "unmeasured_frames": unmeasured,
                  "mouth_note": "the mouth is the teeth and tongue meshes: a lower bound on the clearance to the lip corner",
                  "per_frame": per_frame}
        (out / "cheek_strand_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
        if failed:
            fail("; ".join(failed) + f" -> {out / 'cheek_strand_report.json'}")
        print(f"STRAND_OK {presence['vertices_on_the_cheek']} vertices on the {args.side} cheek, inner gap max "
              f"{presence['press_mm']['inner_gap_max']} mm over {presence['press_mm']['sections']} sections, sunk "
              f"{presence['sunk_into_skin']['deepest_mm']} mm; clearance worst eye {worst['eye']} / brow {worst['brow']} / mouth "
              f"{worst['mouth']} mm over rest + {len(frames)} frames -> {out / 'cheek_strand_report.json'}")
    except StrandError as ex:
        fail(str(ex))


if __name__ == "__main__":
    main()
