"""Time-sampled layered motion blur — the post-composite blur of ADR-0002 D5 (amendment
2026-09-22), applied after the head is in place.

Blurring the layers and compositing afterwards is wrong whenever the head and the plate behind it
move differently during the shutter: "over" of two time-averaged layers is not the time average of
the composite, and the error lands exactly on the head/body seam (measured on SHOT_001 v01: the
precomp gate failed 5 of the 13 laugh-peak frames and at 100 % the seam ring was visible).

So: each sharp layer is forward-warped along its OWN vectors to K instants of the shutter, the
layers are composited at every instant, and the K composites are averaged.

Three details are measured, not assumed, and live in conventions.json → post_composite_blur:
the sign convention of Cycles' two vector pairs; a quadratic motion path through the two
positions the vectors point at and the current one (a straight line over-blurs at the turning
points of a laugh bounce and lost to no blur at all on 4 of 13 frames); and WHERE the vectors
point — since the ADR-0002 amendment of 2026-09-25 at the shutter's own open and close instants,
not at the previous and next frame: a laugh nod shorter than a frame put the true shutter ends
6 px away from a path through frame ±1 (SHOT_002 1209 at 4K), and the gate failed at 0.057 where
the same code through shutter-end vectors reads 0.018. Every call states the vectors' reach — how
far in frames they point — so plates of either kind are never mixed up silently.

Plain numpy: this is the reference implementation the gates measure, not a production renderer.
Cost is reported per frame so the per-order number is never a guess."""
import json
import math
import multiprocessing
import os
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
PB = CONV["post_composite_blur"]


class BlurError(RuntimeError):
    pass


def displacement(vec, u, conv=None):
    """Pixel displacement (dx right, dy down, array coordinates) at path parameter u: 0 = the
    frame's centre, -1 and +1 = the two instants the vectors point at (u = t / reach, t in frames).
    `vec` is the Cycles Vector pass: the first pair points at the earlier instant, the second at the
    later one, with the sign conventions measured on Blender 5.2.1."""
    c = conv or PB["vector_convention"]
    sxp, syp = c["previous_pair_signs"]
    sxn, syn = c["next_pair_signs"]
    dpx, dpy = vec[..., 0] * sxp, vec[..., 1] * syp
    dnx, dny = vec[..., 2] * sxn, vec[..., 3] * syn
    # p(u) through the three known positions: p(-1) = Dp, p(0) = 0, p(+1) = Dn
    return (u * (dnx - dpx) / 2 + u * u * (dnx + dpx) / 2,
            u * (dny - dpy) / 2 + u * u * (dny + dpy) / 2)


def _reach(reach_frames):
    if not (isinstance(reach_frames, (int, float)) and reach_frames > 0):
        raise BlurError(f"vector reach {reach_frames!r} frames: state how far the vectors point (render manifest settings.vector_reach_frames)")
    return float(reach_frames)


def longest_path_px(layers, shutter_frames, reach_frames):
    """The longest distance any pixel travels during the shutter, over all layers."""
    worst = 0.0
    half = shutter_frames / 2 / _reach(reach_frames)
    for _, vec, _ in layers:
        for u in (-half, half):
            dx, dy = displacement(vec, u)
            worst = max(worst, float(np.hypot(dx, dy).max()))
    return worst * 2  # the path runs from one end of the shutter to the other


def samples_for(path_px):
    s = PB["samples"]
    k = math.ceil(path_px / s["px_per_sample"]) if path_px > 0 else s["min_samples"]
    return int(min(max(k, s["min_samples"]), s["max_samples"]))


def active_window(img, dx, dy, margin=2):
    """The rows and columns a layer can reach: its own non-transparent pixels grown by the largest
    displacement in the frame. A head layer covers about a quarter of a 4K frame, and an empty
    foreground plate covers none of it — splatting the other three quarters costs the same as the
    picture and produces zeros."""
    a = img[..., 3] if img.shape[2] == 4 else None
    if a is None:
        return (0, img.shape[0], 0, img.shape[1])
    rows = np.flatnonzero(a.any(axis=1))
    cols = np.flatnonzero(a.any(axis=0))
    if rows.size == 0:
        return None                                   # nothing to splat at all
    grow = int(np.ceil(max(float(np.abs(dx).max()), float(np.abs(dy).max())))) + margin
    return (max(0, int(rows[0]) - grow), min(img.shape[0], int(rows[-1]) + 1 + grow),
            max(0, int(cols[0]) - grow), min(img.shape[1], int(cols[-1]) + 1 + grow))


def warp(img, depth, dx, dy, ztol=None, window=None):
    """Forward-splat premultiplied RGBA along (dx, dy) with bilinear weights and a soft z-test
    (the nearest surface wins a target pixel). Holes — where a layer stretches and no splat lands —
    are filled by normalised 3×3 averaging. Returns (warped image, holes filled).

    `window` limits the work to the rows and columns the layer can reach (see active_window); the
    result outside it is transparent, which is what an empty region of a premultiplied layer is."""
    ztol = PB["depth_test_relative_tolerance"] if ztol is None else ztol
    H, W = img.shape[:2]
    c = img.shape[2]
    r0, r1, c0, c1 = window if window is not None else (0, H, 0, W)
    img_w = img[r0:r1, c0:c1]
    depth_w = depth[r0:r1, c0:c1]
    dx_w, dy_w = dx[r0:r1, c0:c1], dy[r0:r1, c0:c1]
    h, w = img_w.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    tx, ty = xs + dx_w, ys + dy_w
    x0, y0 = np.floor(tx).astype(np.int64), np.floor(ty).astype(np.int64)
    fx, fy = tx - x0, ty - y0
    z = np.asarray(depth_w, dtype=np.float64)
    zmin = np.full(h * w, np.inf)
    xr = np.clip(np.rint(tx).astype(np.int64), 0, w - 1)
    yr = np.clip(np.rint(ty).astype(np.int64), 0, h - 1)
    np.minimum.at(zmin, (yr * w + xr).ravel(), z.ravel())
    acc = np.zeros((h * w, c))
    wsum = np.zeros(h * w)
    src = img_w.reshape(-1, c)                          # float32, no copy: a float64 copy of a 4K
    zf = z.ravel()                                      # plate is 265 MB and this loop makes four
    for ox, oy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                       (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        X, Y = x0 + ox, y0 + oy
        inside = ((X >= 0) & (X < w) & (Y >= 0) & (Y < h)).ravel()
        idx = (np.clip(Y, 0, h - 1) * w + np.clip(X, 0, w - 1)).ravel()
        visible = inside & (zf <= zmin[idx] * (1 + ztol) + 1e-6)
        ww = wt.ravel() * visible
        wsum += np.bincount(idx, ww, minlength=h * w)
        for k in range(c):
            acc[:, k] += np.bincount(idx, src[:, k] * ww, minlength=h * w)
    out = (acc / np.maximum(wsum, 1e-8)[:, None]).reshape(h, w, c)
    filled_mask = (wsum > 1e-3).reshape(h, w).astype(np.float64)
    holes = int((filled_mask == 0).sum())
    # Fill the holes and only the holes: a 4K plate leaves a few tens of thousands of them, and
    # sweeping the whole frame nine times per pass moved gigabytes to touch 0.4 % of it (measured
    # 2026-09-23: 2.4 s of a 2.4 s warp). Each pass averages a hole's already-filled neighbours,
    # using the mask as it was at the start of the pass.
    out_flat = out.reshape(-1, c)
    filled_flat = filled_mask.ravel()
    hole_idx = np.flatnonzero(filled_flat == 0)
    for _ in range(4):
        if hole_idx.size == 0:
            break
        rows, cols = hole_idx // w, hole_idx % w
        num = np.zeros((hole_idx.size, c))
        den = np.zeros(hole_idx.size)
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                if oy == 0 and ox == 0:
                    continue
                r, cl = rows + oy, cols + ox
                ok = (r >= 0) & (r < h) & (cl >= 0) & (cl < w)
                nidx = np.clip(r, 0, h - 1) * w + np.clip(cl, 0, w - 1)
                m = filled_flat[nidx] * ok
                num += out_flat[nidx] * m[:, None]
                den += m
        fill = den > 0
        if not fill.any():
            break
        target = hole_idx[fill]
        out_flat[target] = num[fill] / den[fill][:, None]
        filled_flat[target] = 1.0
        hole_idx = hole_idx[~fill]
    if (r0, r1, c0, c1) == (0, H, 0, W):
        return out.astype(np.float32), holes
    full = np.zeros((H, W, c), np.float32)
    full[r0:r1, c0:c1] = out
    return full, holes


def over(front, back):
    return front + back * (1 - front[..., 3:4])


def composite_at(layers, u):
    """The picture at one instant of the shutter (path parameter u): every layer warped along its
    own vectors, then composited in order. Returns (image, holes filled, empty-layer passes)."""
    comp, holes, empty = None, 0, 0
    for img, vec, dep in reversed(layers):              # BACK first, then over
        dx, dy = displacement(vec, u)
        win = active_window(img, dx, dy)
        if win is None:                                 # a layer with no coverage adds nothing
            empty += 1
            if comp is None:
                comp = np.zeros_like(img)
            continue
        w, hole = warp(img, dep, dx, dy, window=win)
        holes += hole
        comp = w if comp is None else over(w, comp)
    return comp, holes, empty


_FORKED = {}


def _chunk(args):
    """Runs in a forked worker: the layers come from the parent's memory, not through a pipe."""
    ts = args
    layers = _FORKED["layers"]
    total, holes, empty = None, 0, 0
    for t in ts:
        comp, hole, e = composite_at(layers, t)
        holes += hole
        empty += e
        total = comp.astype(np.float32) if total is None else total + comp
    return total, holes, empty


def worker_count(shape, k, workers=None):
    """How many processes to spread the shutter instants over (conventions → post_composite_blur
    → workers). The default is one: measured 2026-09-23 on a 10-core laptop, eight workers on a 4K
    frame ran 2.5× SLOWER than one — the blur moves hundreds of megabytes per instant and is bound
    by memory bandwidth, not by cores, so the copies cost more than the parallelism buys. The
    option stays because a machine with more bandwidth per core may measure otherwise; it is
    switched on by measurement, not by hope."""
    if workers is not None:
        return max(1, int(workers))
    return int(PB["workers"].get("default", 1))


def blur(layers, shutter_frames, reach_frames, samples=None, workers=None):
    """layers: [(rgba_premultiplied, vector, depth)] ordered FRONT first, as they composite; their
    vectors point reach_frames away (0.25 at a 180° shutter since 2026-09-25: the shutter's ends;
    1.0 for plates whose vectors point at the previous and next frame). Returns (image, report). The
    shutter is centred: t runs over ±shutter_frames/2, the path parameter over ±t/reach."""
    if not layers:
        raise BlurError("no layers to blur")
    if shutter_frames <= 0:
        raise BlurError(f"shutter_frames {shutter_frames} is not an exposure — a sharp frame is not blurred here")
    reach = _reach(reach_frames)
    path = longest_path_px(layers, shutter_frames, reach)
    k = samples or samples_for(path)
    t0 = time.time()
    ts = [(-0.5 + (i + 0.5) / k) * shutter_frames / reach for i in range(k)]
    n = worker_count(layers[0][0].shape, k, workers)
    accum, holes, empty = None, 0, 0
    if n > 1:
        chunks = [ts[i::n] for i in range(n)]           # fixed split, fixed summation order
        _FORKED["layers"] = layers
        try:
            with multiprocessing.get_context("fork").Pool(n) as pool:
                results = pool.map(_chunk, chunks)
        finally:
            _FORKED.pop("layers", None)
        for total, hole, e in results:                  # added in chunk order, not arrival order
            accum = total.astype(np.float64) if accum is None else accum + total
            holes += hole
            empty += e
    else:
        for t in ts:
            comp, hole, e = composite_at(layers, t)
            holes += hole
            empty += e
            accum = comp.astype(np.float64) if accum is None else accum + comp
    img = (accum / len(ts)).astype(np.float32)
    report = {"samples": k, "longest_path_px": round(path, 2), "shutter_frames": shutter_frames, "vector_reach_frames": reach,
              "px_per_sample": round(path / k, 3) if k else None,
              "samples_rule": PB["samples"]["rule"], "samples_status": PB["samples"]["status"] if "status" in PB["samples"] else PB["status"],
              "holes_filled": holes, "empty_layer_passes_skipped": empty, "workers": n,
              "seconds": round(time.time() - t0, 2),
              "layers": len(layers), "model": PB["model"]}
    return img, report
