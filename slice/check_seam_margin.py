"""Seam overlap margin — the measured form of ADR-0002 §D1 (amendment 2026-09-22, corrected
2026-09-23).

    blender -b <scene.blend> --python-exit-code 2 -P slice/check_seam_margin.py -- --out <dir>

A head technology MAY continue its shell below the socket boundary curve to close cracks from
inside. Where it does, that geometry has to stay inside the body neck: otherwise the two surfaces
fight for depth and a layered composite draws a line across the neck. So on EVERY frame of the
shot — not in the rest pose, which is where such a defect hides — every band vertex sits at least
`margin_mm` inside the body surface, ramped from 0 at the curve to the full margin `ramp_mm`
below it.

The slice's own head has no such geometry: it ends exactly at the curve, welded to the body ring
(0.000 mm), so this gate passes vacuously on it and says so. It is written for the bake-off, where
a candidate that does bring an overlap band must keep it inside. The thresholds are PROVISIONAL
and have never been calibrated against a head that has one.

Two readings of the asset are load-bearing here, and both were got wrong once (2026-09-23):
  * the curve is the MEMBERSHIP of the SOCKET_BOUNDARY group, never a weight threshold — the
    weight is the ring ORDER (`export_shot.py` refuses non-distinct weights because the order
    defines the polyline). Reading `weight > 0.5` keeps one contiguous half-arc and invents a band
    out of ordinary head skin;
  * which vertices form the band is decided in the rig's REST pose: classified per frame, the chin
    joins the band the moment the head nods.

Hair is not the seam band (ADR-0002 D3: the head technology replaces it, it has free edges and it
legitimately falls over the shoulders), so C_HAIR is not measured. Proxies are not surfaces.

Exit 0 with SEAM_MARGIN_OK; exit 2 with SEAM_MARGIN_ERROR and the worst offenders named."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
N = CONV["scene_naming"]
SM = CONV["seam_margin"]


class SeamMarginError(Exception):
    pass


def fail(msg):
    print(f"SEAM_MARGIN_ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def meshes(collection):
    coll = bpy.data.collections.get(collection)
    if coll is None:
        raise SeamMarginError(f"collection {collection} missing — this is not a slice scene")
    return [o for o in coll.all_objects if o.type == "MESH" and o.name not in N["proxies"]]


def body_surface(bodies, dg):
    """One BVH tree over every evaluated body mesh, in world space."""
    bm = bmesh.new()
    for o in bodies:
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        tmp = bmesh.new()
        tmp.from_mesh(me)
        tmp.transform(eo.matrix_world)
        tmp.to_mesh(me)                      # bake the transform, then merge
        bm.from_mesh(me)
        tmp.free()
        eo.to_mesh_clear()
    if not bm.faces:
        bm.free()
        raise SeamMarginError("the body collections carry no faces")
    bm.normal_update()
    return BVHTree.FromBMesh(bm), bm


def ring_of(body, dg):
    """World positions of the SOCKET_BOUNDARY vertex group on the evaluated body.

    Membership is the group, NOT a weight threshold. The weight in this group carries the ring
    ORDER (i/N — `export_shot.py` refuses non-distinct weights because that is what orders the
    polyline). Reading it as `weight > 0.5` keeps the half of the ring whose order index is high,
    which is one contiguous arc: on the contractor's v03 that is 21 of 42 vertices spanning
    z 1.1972–1.2108 while the real curve runs 1.1813–1.2108. Everything below that phantom curve
    then looks like head geometry hanging under the seam. Found by the contractor, 2026-09-23."""
    gi = body.vertex_groups.get(N["vertex_group_socket_boundary"])
    if gi is None:
        return None
    eb = body.evaluated_get(dg)
    mw = eb.matrix_world
    idx = [v.index for v in body.data.vertices if any(g.group == gi.index for g in v.groups)]
    if not idx:
        return None
    return [mw @ eb.data.vertices[i].co for i in idx]


def ring_geometry(ring):
    """Neck axis, the curve's own radius and a per-angle height (the ring is not horizontal)."""
    cx = sum(p.x for p in ring) / len(ring)
    cy = sum(p.y for p in ring) / len(ring)
    radius = sum(math.hypot(p.x - cx, p.y - cy) for p in ring) / len(ring)

    def ring_z(p):
        a = math.atan2(p.x - cx, p.y - cy)
        return min(ring, key=lambda r: abs(math.remainder(math.atan2(r.x - cx, r.y - cy) - a, 2 * math.pi))).z

    return cx, cy, ring_z, radius


def band_indices(heads, ring_owner, radius_factor, scene):
    """The overlap band, defined ONCE in the rig's REST pose: which head vertices continue below
    the boundary curve is a property of the shell, not of a pose. Measured the hard way on
    SHOT_001 v01: classifying per frame calls the chin a band vertex as soon as the head nods
    (vertex 746 sits 90 mm from the neck axis at rest and 79 mm on frame 1073), and the gate then
    fails on a chin that is supposed to be outside the neck. Returns {object name: {index: depth
    below the curve, metres}}."""
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    was = [(a, a.data.pose_position) for a in arms]
    for a in arms:
        a.data.pose_position = "REST"
    try:
        scene.frame_set(scene.frame_start)
        dg = bpy.context.evaluated_depsgraph_get()
        ring = ring_of(ring_owner, dg)
        if ring is None:
            raise SeamMarginError("the socket boundary group is empty in the rest pose")
        cx, cy, ring_z, ring_radius = ring_geometry(ring)
        reach = ring_radius * radius_factor
        out = {}
        for o in heads:
            eo = o.evaluated_get(dg)
            me = eo.to_mesh()
            mw = eo.matrix_world
            found = {}
            for v in me.vertices:
                p = mw @ v.co
                depth = ring_z(p) - p.z
                if depth > 0 and math.hypot(p.x - cx, p.y - cy) <= reach:
                    found[v.index] = depth
            eo.to_mesh_clear()
            if found:
                out[o.name] = found
        return out
    finally:
        for a, pos in was:
            a.data.pose_position = pos
        scene.frame_set(scene.frame_start)


def margins_on_frame(heads, bodies, band, dg, ramp_mm, margin_mm):
    """Signed distance of every band vertex to the body surface (+ = outside the skin, mm) against
    the margin its rest depth below the curve requires."""
    tree, bm = body_surface(bodies, dg)
    out = []
    unreached = 0
    try:
        for o in heads:
            idx = band.get(o.name)
            if not idx:
                continue
            eo = o.evaluated_get(dg)
            me = eo.to_mesh()
            mw = eo.matrix_world
            for i, depth in idx.items():
                p = mw @ me.vertices[i].co
                loc, nrm, _, _ = tree.find_nearest(p, 0.05)
                if loc is None:
                    unreached += 1
                    continue
                signed_mm = (p - loc).dot(nrm) * 1000.0
                required_mm = -margin_mm * min(1.0, (depth * 1000.0) / ramp_mm)
                out.append((o.name, i, signed_mm, required_mm, depth * 1000.0))
            eo.to_mesh_clear()
    finally:
        bm.free()
    return out, unreached


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default=None, help="'1001,1090' or '1001-1010'; default: the shot's whole range")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    scene = bpy.data.scenes.get("SLICE") or fail("scene SLICE missing — this is not a slice scene")
    bpy.context.window.scene = scene
    if args.frames:
        frames = [int(x) for x in args.frames.split(",")] if "," in args.frames or "-" not in args.frames \
            else list(range(int(args.frames.split("-")[0]), int(args.frames.split("-")[1]) + 1))
    else:
        frames = list(range(scene.frame_start, scene.frame_end + 1))

    try:
        heads = [o for c in SM["collections"] for o in meshes(c)]
        bodies = [o for c in SM["body_collections"] for o in meshes(c)]
        if not heads or not bodies:
            raise SeamMarginError(f"no meshes to measure: head {[o.name for o in heads]}, body {[o.name for o in bodies]}")
        ring_owner = next((o for o in bodies if o.vertex_groups.get(N["vertex_group_socket_boundary"])), None)
        if ring_owner is None:
            raise SeamMarginError(f"no body mesh carries the {N['vertex_group_socket_boundary']} vertex group")

        margin, ramp, tol = SM["margin_mm"], SM["ramp_mm"], SM["tolerance_mm"]
        radius_factor = SM["radius_factor_of_ring"]
        band_def = band_indices(heads, ring_owner, radius_factor, scene)
        per_frame, offenders, band_sizes, unreached_total = [], [], [], 0
        for f in frames:
            scene.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            band, unreached = margins_on_frame(heads, bodies, band_def, dg, ramp, margin)
            unreached_total += unreached
            band_sizes.append(len(band))
            worst = None
            for name, vi, signed, required, depth in band:
                slack = required - signed          # > 0 means inside by more than required
                if worst is None or slack < worst[0]:
                    worst = (slack, name, vi, signed, required, depth)
                if signed > required + tol:
                    offenders.append({"frame": f, "object": name, "vertex": vi, "signed_mm": round(signed, 3),
                                      "required_mm": round(required, 3), "depth_below_curve_mm": round(depth, 3)})
            per_frame.append({"frame": f, "band_vertices": len(band),
                              "worst_slack_mm": round(worst[0], 3) if worst else None,
                              "worst_signed_mm": round(worst[3], 3) if worst else None,
                              "worst_object": worst[1] if worst else None})
        band_max = max(band_sizes) if band_sizes else 0
        offenders.sort(key=lambda o: o["signed_mm"] - o["required_mm"], reverse=True)
        report = {
            "gate": "seam_margin",
            "status": "FAIL" if offenders else "PASS",
            "rule": SM["rule"],
            "thresholds": {"margin_mm": margin, "ramp_mm": ramp, "radius_factor_of_ring": radius_factor,
                           "tolerance_mm": tol, "status": SM["status"]},
            "scene": {"shot": scene.get("shot_id"), "frames": [frames[0], frames[-1]], "frame_count": len(frames),
                      "head_meshes": [o.name for o in heads], "body_meshes": [o.name for o in bodies]},
            "band": {"defined_in": "the rig's REST pose — which head vertices continue below the curve is a property of the shell, not of a pose",
                     "vertices_per_object": {k: len(v) for k, v in band_def.items()}},
            "band_vertices_max": band_max,
            "vacuous": band_max == 0,
            "vertices_with_no_body_surface_within_50mm": unreached_total,
            "offending_vertices": len(offenders),
            "worst_offenders": offenders[:20],
            "per_frame": per_frame,
        }
        (out / "seam_margin_report.json").write_text(json.dumps(report, indent=1) + "\n")
        if offenders:
            w = offenders[0]
            fail(f"the head's overlap band is not inside the body neck: {len(offenders)} vertex-frames out of "
                 f"{band_max} band vertices × {len(frames)} frames; worst {w['object']} vertex {w['vertex']} on frame "
                 f"{w['frame']} at {w['signed_mm']:+.2f} mm where {w['required_mm']:.2f} mm or less is required "
                 f"(ADR-0002 D1 overlap margin, {SM['status']}) -> {out / 'seam_margin_report.json'}")
        if band_max == 0:
            print(f"SEAM_MARGIN_OK vacuous: no head geometry below the socket boundary curve on {len(frames)} frames "
                  f"(nothing to tuck) -> {out / 'seam_margin_report.json'}")
        else:
            tight = min(p["worst_slack_mm"] for p in per_frame if p["worst_slack_mm"] is not None)
            print(f"SEAM_MARGIN_OK {band_max} band vertices on {len(frames)} frames, tightest {tight:+.2f} mm "
                  f"beyond the required margin -> {out / 'seam_margin_report.json'}")
    except (SeamMarginError, KeyError) as e:
        fail(str(e))


if __name__ == "__main__":
    main()
