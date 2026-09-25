"""The back under the head's lower edge — ADR-0002 amendment 2026-09-24 (A1 SEAM_EXTEND, A2 the
seam criterion). numpy only, so CI tests it on synthetic plates; slice/composite.py (criterion 3,
default head) and slice/composite_order.py (every order) call it.

The head and the body meet vertex to vertex at the socket ring (D1), so nothing of the body lies
behind the head's lower edge: the body plate under the head holdout shows the open neck — the
torso's dark interior — and the head's partial-coverage edge pixels let it through, a dark line
along the neck in every layered composite (measured on SHOT_001 v01 and SHOT_002 v01, every
frame; slice/measurements/shot_002_v01_acceptance_2026-09-24.json).

    FINAL = FRONT over (HEAD over SEAM_EXTEND(BACK))

SEAM_EXTEND replaces the back plate only inside the head holdout and only within the seam zone,
with the body's own surface grown from outside the holdout, ring by ring (the mean of the already
known 8-neighbours). The seam zone is the pixels within `zone_px` of the projected socket boundary
rings — the head ring, rigid on the socket, and the body ring as exported per frame — so it
follows the ring wherever it dips (the 2026-09-23 lesson: a ring is read by its geometry, and its
controls make it dip). Behind the rest of the silhouette the plate already holds the right thing
and is left alone: an unrestricted extend was measured worse there.

Distances are in the RENDER's pixels: the edge that mixes with the back is the reconstruction
filter's width, a pixel quantity at every scale. Parameters: conventions.json →
compositor.seam_extend (PROVISIONAL)."""
import numpy as np


class SeamError(RuntimeError):
    pass


def _centre(frame_record):
    for s in frame_record["samples"]:
        if s["offset"] == 0.0:
            return s
    raise SeamError(f"frame {frame_record.get('frame')}: no centre sample")


def facing_camera(ring, cam_pos, grazing_sin):
    """Which points of a closed ring round the (convex) neck face the camera: the outward radial
    normal — the point's offset from the ring's centroid, taken in the ring's best-fit plane — has a
    positive component towards the camera, or is within grazing_sin of perpendicular (the neck's
    silhouette, where the head's edge still borders the body). The back arc — behind the neck, seen
    only through the open neck in the body plate — does not face it. Geometry, not the depth pass,
    so no depth convention is assumed."""
    c = ring.mean(axis=0)
    axis = np.linalg.svd(ring - c)[2][-1]                      # the ring plane's normal (the neck axis)
    radial = (ring - c) - np.outer((ring - c) @ axis, axis)
    to_cam = cam_pos - ring
    dot = np.einsum("ij,ij->i", radial, to_cam)
    return dot >= -grazing_sin * np.linalg.norm(radial, axis=1) * np.linalg.norm(to_cam, axis=1)


def ring_polylines_px(boundary, sock_by_frame, cam_by_frame, frame, profile, scale_percent, grazing_sin=0.1, weld_m=1e-4):
    """The head ring and the body ring of socket_boundary.json at `frame`, projected through that
    frame's camera (centre samples) at the profile's pixel intrinsics scaled to the render — two
    closed polylines as (points (N, 2) of (u right, v down) in pixels, mask (N,) bool) — and a
    summary for the report. A point's mask is set when it faces the camera AND the seam is closed
    there: the head ring's point and the body ring's corresponding point lie within weld_m of each
    other. Where the rings are apart the master's own seam is open — the full render shows a gap —
    and SEAM_EXTEND must not paint over it (measured 2026-09-25: the contractor's asset keeps every
    point within 0.000 mm on all 240 frames of SHOT_001 and SHOT_002; the template's placeholder,
    a rigid unskinned body, opens by millimetres as its head turns). Pinhole as
    slice/camera_model.project; a ring point at or behind the camera is an error. The pipeline
    passes grazing_sin and weld_m from conventions.json → compositor.seam_extend."""
    if frame not in sock_by_frame or frame not in cam_by_frame:
        raise SeamError(f"frame {frame} is not in the exports")
    rest = boundary["rest_frame"]
    if rest not in sock_by_frame:
        raise SeamError(f"the boundary's rest frame {rest} is not in socket.json")
    s_now = np.asarray(_centre(sock_by_frame[frame])["matrix_4x4"], float)
    s_rest = np.asarray(_centre(sock_by_frame[rest])["matrix_4x4"], float)
    head = np.asarray(boundary["head_ring_rest"], float)
    head_now = (s_now @ np.linalg.inv(s_rest) @ np.c_[head, np.ones(len(head))].T).T[:, :3]  # the head ring rides the socket rigidly
    body_rows = {r["frame"]: r["points_m"] for r in boundary.get("body_ring_per_frame", [])}
    if frame not in body_rows:
        raise SeamError(f"frame {frame}: socket_boundary.json carries no body ring for it")
    body_now = np.asarray(body_rows[frame], float)
    if body_now.shape != head_now.shape:
        raise SeamError(f"frame {frame}: the head ring has {len(head_now)} points and the body ring {len(body_now)} — the rings must correspond point for point")
    gap = np.linalg.norm(head_now - body_now, axis=1)
    welded = gap <= weld_m
    cam = cam_by_frame[frame]
    cam_m = np.asarray(_centre(cam)["extrinsic_matrix_4x4"], float)
    c_inv = np.linalg.inv(cam_m)
    px = cam["intrinsics"]["px_by_profile"][profile]
    f = scale_percent / 100.0
    (fx, fy), (cx, cy) = [v * f for v in px["focal_length_px"]], [v * f for v in px["principal_point_px"]]
    out, seen = [], np.zeros(len(head_now), bool)
    for ring in (head_now, body_now):
        c = (c_inv @ np.c_[ring, np.ones(len(ring))].T)[:3]
        depth = -c[2]
        if (depth <= 0).any():
            raise SeamError(f"frame {frame}: a ring point is at or behind the camera")
        facing = facing_camera(ring, cam_m[:3, 3], grazing_sin)
        seen |= facing
        out.append((np.stack([cx + fx * c[0] / depth, cy - fy * c[1] / depth], 1), facing & welded))
    info = {"points": int(len(head_now)), "visible_points": int(seen.sum()), "visible_open_points": int((seen & ~welded).sum()),
            "max_gap_mm_visible": float(gap[seen].max() * 1000) if seen.any() else 0.0, "weld_mm": weld_m * 1000}
    return out, info


def zone_mask(polylines, shape, zone_px):
    """Pixels whose centre lies within zone_px of any segment of the closed polylines. A polyline
    is an array (N, 2) — every segment counts — or a pair (array, facing mask) from
    ring_polylines_px — only segments whose both ends face the camera count, so the hidden back
    arc of the ring adds nothing."""
    h, w = shape
    zone = np.zeros((h, w), bool)
    for entry in polylines:
        poly, facing = entry if isinstance(entry, tuple) else (entry, np.ones(len(entry), bool))
        for a, b, fa, fb in zip(poly, np.roll(poly, -1, axis=0), facing, np.roll(facing, -1)):
            if not (fa and fb):
                continue
            x0, x1 = int(np.floor(min(a[0], b[0]) - zone_px)), int(np.ceil(max(a[0], b[0]) + zone_px))
            y0, y1 = int(np.floor(min(a[1], b[1]) - zone_px)), int(np.ceil(max(a[1], b[1]) + zone_px))
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
            if x0 > x1 or y0 > y1:
                continue
            ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            p = np.stack([xs + 0.5, ys + 0.5], -1)
            ab = b - a
            t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
            d = np.linalg.norm(p - (a + t[..., None] * ab), axis=-1)
            zone[y0:y1 + 1, x0:x1 + 1] |= d <= zone_px
    return zone


def extend(arrays, holdout, zone, extend_px, holdout_known_max):
    """SEAM_EXTEND. `arrays`: the back plate and anything that must travel with it (the blur's
    vectors and depth), each (H, W, C). To fill: the zone where the head holdout is at or above
    holdout_known_max. Sources: only pixels outside the head (holdout below it) — the body the
    head's edge actually borders; the plate under the head outside the zone (more of the open
    neck) is neither a source nor changed. Filled pixels are grown from the sources ring by ring
    for extend_px rings; a pixel to fill that no ring reaches keeps its value and is counted (it
    lies deeper under the head than any edge pixel). Returns (arrays', stats)."""
    todo = zone & (holdout >= holdout_known_max)
    stats = {"zone_px": int(zone.sum()), "to_fill_px": int(todo.sum()), "replaced_px": 0, "unreached_px": 0}
    if not todo.any():
        return [a.copy() for a in arrays], stats
    ys, xs = np.where(todo)
    m = extend_px + 1
    y0, y1 = max(0, ys.min() - m), min(holdout.shape[0], ys.max() + m + 1)
    x0, x1 = max(0, xs.min() - m), min(holdout.shape[1], xs.max() + m + 1)
    todo = todo[y0:y1, x0:x1]
    known = holdout[y0:y1, x0:x1] < holdout_known_max
    vals = [np.where(known[..., None], a[y0:y1, x0:x1].astype(np.float64), 0.0) for a in arrays]
    filled = np.zeros_like(todo)
    h, w = known.shape
    for _ in range(extend_px):
        cnt = np.zeros((h, w))
        acc = [np.zeros_like(v) for v in vals]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                src = (slice(max(0, dy), h + min(0, dy)), slice(max(0, dx), w + min(0, dx)))
                dst = (slice(max(0, -dy), h + min(0, -dy)), slice(max(0, -dx), w + min(0, -dx)))
                kk = known[src]
                cnt[dst] += kk
                for a, v in zip(acc, vals):
                    a[dst] += v[src] * kk[..., None]
        grow = todo & ~known & (cnt > 0)
        if not grow.any():
            break
        for a, v in zip(acc, vals):
            v[grow] = a[grow] / cnt[grow, None]
        known = known | grow
        filled |= grow
    out = []
    for a, v in zip(arrays, vals):
        o = a.copy()
        o[y0:y1, x0:x1][filled] = v[filled].astype(a.dtype)
        out.append(o)
    stats["replaced_px"] = int(filled.sum())
    stats["unreached_px"] = stats["to_fill_px"] - stats["replaced_px"]
    return out, stats


MIXED = (0.01, 0.99)   # the pipeline passes conventions.json → compositor.seam_extend.seam_mixed_coverage


def seam_criterion(comp, full, band, zone, holdout, mixed=MIXED):
    """A2: the signed mean of (composite − full) over the seam's MIXED pixels — the precomp test's
    boundary band, inside the seam zone, where the head's coverage is fractional. Those are the
    only pixels where HEAD over BACK lets the back through, i.e. where the line lives; the band's
    fully covered and fully uncovered pixels carry no error and would dilute the mean (measured:
    a 5-px band on SHOT_002 1121 at 25 % holds 928 px against ~280 mixed ones, and took the line
    from −0.15 to −0.05). A systematic darkening is a line; noise averages out."""
    lo, hi = mixed
    seam = band & zone & (holdout > lo) & (holdout < hi)
    n = int(seam.sum())
    if not n:
        return {"seam_band_px": 0, "signed_mean": None, "within_5e-2": None, "median_abs": None}
    signed = (comp[..., :3] - full[..., :3]).mean(-1)[seam]
    err = np.abs(comp[..., :3] - full[..., :3]).max(-1)[seam]
    return {"seam_band_px": n, "signed_mean": float(signed.mean()), "within_5e-2": float((err <= 0.05).mean()), "median_abs": float(np.median(err))}
