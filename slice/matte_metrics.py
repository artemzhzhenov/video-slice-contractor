"""Matte comparison for the D7 round-trip — pure numpy, unit-tested in CI (no Blender, no OIIO).
The rasteriser, the edge band and the silhouette metrics live here so composite.py and
roundtrip.py share one definition of "edge" and one definition of "distance"."""
import math

import numpy as np

SS = 4              # supersampling per axis (conventions.roundtrip.reprojection)
BAND_PX = 2


class MatteError(ValueError):
    pass


def iou_min_for(m, boundary_error_px, floor, ceiling):
    """The IoU floor a silhouette's own framing implies (conventions → roundtrip.gate.iou_rule).
    A flat iou_min is nearly free on a big silhouette and harsh on a small one, because the same
    boundary error costs 1 − IoU in proportion to boundary / area; the gate states that boundary
    error instead and resolves the threshold per frame. Already resolution-free: it does not scale
    with the render percentage."""
    a, b = m["silhouette_px"]["reference"], m["boundary_px"]
    if a <= 0 or b <= 0:
        raise MatteError("the reference silhouette has no area or no boundary — nothing to gate")
    return float(min(max(1.0 - boundary_error_px * b / a, floor), ceiling))


def edge_band(mask, band):
    """Pixels within `band` px (Chebyshev) of the mask's edge, without wrapping at the borders."""
    padded = np.pad(mask, band, mode="edge")
    h, w = mask.shape
    edge = np.zeros_like(mask)
    for dy in range(-band, band + 1):
        for dx in range(-band, band + 1):
            shifted = padded[band + dy: band + dy + h, band + dx: band + dx + w]
            edge |= shifted != mask
    return edge


def rasterize(tri_px, w, h):
    """Box coverage in [0, 1] of a triangle soup given in pixel coordinates (x right, y down,
    pixel (i, j) spans [i, i+1) × [j, j+1)), supersampled SS×SS. Orientation-agnostic."""
    W, H = w * SS, h * SS
    buf = np.zeros((H, W), dtype=bool)
    p = tri_px * SS
    for (x0, y0), (x1, y1), (x2, y2) in p:
        ax, ay = max(int(math.floor(min(x0, x1, x2))), 0), max(int(math.floor(min(y0, y1, y2))), 0)
        bx, by = min(int(math.ceil(max(x0, x1, x2))) + 1, W), min(int(math.ceil(max(y0, y1, y2))) + 1, H)
        if ax >= bx or ay >= by:
            continue
        xs = np.arange(ax, bx) + 0.5
        ys = (np.arange(ay, by) + 0.5)[:, None]
        e0 = (x1 - x0) * (ys - y0) - (y1 - y0) * (xs - x0)
        e1 = (x2 - x1) * (ys - y1) - (y2 - y1) * (xs - x1)
        e2 = (x0 - x2) * (ys - y2) - (y0 - y2) * (xs - x2)
        inside = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
        buf[ay:by, ax:bx] |= inside
    return buf.reshape(h, SS, w, SS).mean(axis=(1, 3), dtype=np.float32)


# ---------------------------------------------------------------- metrics

def boundary(mask):
    """Mask pixels with a 4-neighbour outside the mask. The image border is not a silhouette
    edge (a head cut by the frame is cut identically in both mattes)."""
    padded = np.pad(mask, 1, mode="edge")
    interior = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    return mask & ~interior


def upsample(cov, factor):
    """Bilinear upsampling of a coverage image so the 0.5 iso-contour is located to 1/factor px
    (review 2026-09-15: on binary masks the boundary distance took only the values 0, 1, √2 …
    and sat on the 1 px threshold; the contour of the interpolated coverage resolves below it).
    Sample positions are clamped to the image before interpolation — the outermost rows are
    replicated, never extrapolated (review round 2: extrapolation put a false contour along
    the frame border under any head cut by the frame)."""
    h, w = cov.shape
    ys = np.clip((np.arange(h * factor) + 0.5) / factor - 0.5, 0, h - 1)
    xs = np.clip((np.arange(w * factor) + 0.5) / factor - 0.5, 0, w - 1)
    y0 = np.floor(ys).astype(int); y1 = np.minimum(y0 + 1, h - 1); fy = (ys - y0)[:, None]
    x0 = np.floor(xs).astype(int); x1 = np.minimum(x0 + 1, w - 1); fx = (xs - x0)[None, :]
    c = cov.astype(np.float32)
    top = c[y0][:, x0] * (1 - fx) + c[y0][:, x1] * fx
    bot = c[y1][:, x0] * (1 - fx) + c[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


MAX_BOUNDARY_POINTS = 2_000_000


def nearest_distances(a_pts, b_pts):
    """For each point of a, the distance to the nearest point of b (chunked brute force). A
    boundary set beyond MAX_BOUNDARY_POINTS is a failure in itself, not hours of work."""
    if len(a_pts) > MAX_BOUNDARY_POINTS or len(b_pts) > MAX_BOUNDARY_POINTS:
        raise MatteError(f"boundary sets of {len(a_pts)} / {len(b_pts)} points exceed {MAX_BOUNDARY_POINTS} — the re-projection is grossly wrong or the image is not a matte")
    if len(b_pts) == 0 or len(a_pts) == 0:
        raise MatteError("a silhouette has no boundary (fills the frame or is empty)")
    out = np.empty(len(a_pts))
    step = max(1, int(2e7 // max(len(b_pts), 1)))
    b = b_pts.astype(np.float64)
    for i in range(0, len(a_pts), step):
        a = a_pts[i:i + step].astype(np.float64)
        d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
        out[i:i + step] = np.sqrt(d2.min(axis=1))
    return out


def metrics(cov, ref, exclude=None):
    """Silhouette metrics between a re-projected coverage image and a reference matte.
    p95 / max boundary distance in px are measured between the 0.5 iso-contours of both images
    upsampled ×SS (sub-pixel) inside a crop around the union of both silhouettes (the full
    still frame ×16 would need ~10 GB); the centroid uses the coverage weights; IoU and the
    band use the ≥0.5 masks at pixel resolution. `exclude` (bool HxW) marks pixels the caller
    cannot compare (body or environment in front of the head): they are dropped from every
    sum, and contour points inside them (dilated 1 px) are not queried — while every contour
    point stays a target, so the exclusion outline never becomes a contour and never leaves a
    gap that reads as distance."""
    a, b = cov >= 0.5, ref >= 0.5
    if exclude is None:
        exclude = np.zeros(cov.shape, bool)
    # The exclusion is dilated by 1 px for every sum: HEAD_HOLDOUT is cut wherever the body has
    # ANY coverage, so the fractional-coverage halo around an excluded region is incomparable
    # too (review round 3 measured a 0.245 px centroid artefact on a perfect re-projection
    # with half the head excluded when the halo was kept).
    exclude = edge_band(exclude, 1) | exclude
    keep = ~exclude
    if not (b & keep).any():
        raise MatteError("reference HEAD_HOLDOUT has no ≥0.5 pixel outside the exclusion — nothing to compare")
    if not (a & keep).any():
        raise MatteError("re-projected head has no ≥0.5 pixel outside the exclusion — the head is off-frame or degenerate")
    ys_any, xs_any = np.where(a | b)
    margin = BAND_PX + 2
    y_lo, y_hi = max(int(ys_any.min()) - margin, 0), min(int(ys_any.max()) + margin + 1, cov.shape[0])
    x_lo, x_hi = max(int(xs_any.min()) - margin, 0), min(int(xs_any.max()) + margin + 1, cov.shape[1])
    crop = (slice(y_lo, y_hi), slice(x_lo, x_hi))
    ua, ub = upsample(cov[crop], SS) >= 0.5, upsample(ref[crop], SS) >= 0.5
    # Query points inside the exclusion (dilated 1 px) are dropped; the TARGET contours stay
    # complete. Dropping targets too made a kept point next to a dropped stretch measure the
    # distance to the stretch's far end (measured 176 px on a 5 px perturbation, round 3).
    ex_up = np.repeat(np.repeat(exclude[crop], SS, axis=0), SS, axis=1)
    ba_all, bb_all = np.argwhere(boundary(ua)), np.argwhere(boundary(ub))
    ba, bb = np.argwhere(boundary(ua) & ~ex_up), np.argwhere(boundary(ub) & ~ex_up)
    d = np.concatenate([nearest_distances(ba, bb_all), nearest_distances(bb, ba_all)]) / SS
    ys, xs = np.mgrid[0:cov.shape[0], 0:cov.shape[1]]
    ck, rk = np.where(keep, cov, 0.0), np.where(keep, ref, 0.0)

    def centroid(img):
        s = float(img.sum())
        return np.array([float((xs * img).sum() / s), float((ys * img).sum() / s)])
    band = edge_band(b, BAND_PX) & keep
    return {"p95_boundary_px": float(np.percentile(d, 95)), "max_boundary_px": float(d.max()),
            "centroid_px": float(np.linalg.norm(centroid(ck) - centroid(rk))),
            "iou": float(((a & b) & keep).sum() / ((a | b) & keep).sum()),
            "mean_abs_coverage_in_band": float(np.abs(cov - ref)[band].mean()) if band.any() else 0.0,
            "silhouette_px": {"reprojected": int((a & keep).sum()), "reference": int((b & keep).sum()), "excluded": int(exclude.sum())},
            # The reference silhouette's boundary length in pixels. IoU is not a framing-free
            # number — the same boundary error costs 1 − IoU in proportion to boundary / area —
            # so the gate states its threshold as the boundary error it implies and needs this.
            "boundary_px": int((boundary(b) & keep).sum())}
