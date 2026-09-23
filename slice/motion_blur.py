"""Time-sampled layered motion blur — the post-composite blur of ADR-0002 D5 (amendment
2026-09-22), applied after the head is in place.

Blurring the layers and compositing afterwards is wrong whenever the head and the plate behind it
move differently during the shutter: "over" of two time-averaged layers is not the time average of
the composite, and the error lands exactly on the head/body seam (measured on SHOT_001 v01: the
precomp gate failed 5 of the 13 laugh-peak frames and at 100 % the seam ring was visible).

So: each sharp layer is forward-warped along its OWN vectors to K instants of the shutter, the
layers are composited at every instant, and the K composites are averaged.

Two details are measured, not assumed, and live in conventions.json → post_composite_blur:
the sign convention of Cycles' two vector pairs, and a quadratic motion path through the
previous / current / next positions (a straight line over-blurs at the turning points of a laugh
bounce and lost to no blur at all on 4 of 13 frames).

Plain numpy: this is the reference implementation the gates measure, not a production renderer.
Cost is reported per frame so the per-order number is never a guess."""
import json
import math
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
PB = CONV["post_composite_blur"]


class BlurError(RuntimeError):
    pass


def displacement(vec, t, conv=None):
    """Pixel displacement (dx right, dy down, array coordinates) at shutter time t in frames,
    0 = the frame's centre. `vec` is the Cycles Vector pass: the first pair points at the previous
    frame, the second at the next, with the sign conventions measured on Blender 5.2.1."""
    c = conv or PB["vector_convention"]
    sxp, syp = c["previous_pair_signs"]
    sxn, syn = c["next_pair_signs"]
    dpx, dpy = vec[..., 0] * sxp, vec[..., 1] * syp
    dnx, dny = vec[..., 2] * sxn, vec[..., 3] * syn
    # p(t) through the three known positions: p(-1) = Dp, p(0) = 0, p(+1) = Dn
    return (t * (dnx - dpx) / 2 + t * t * (dnx + dpx) / 2,
            t * (dny - dpy) / 2 + t * t * (dny + dpy) / 2)


def longest_path_px(layers, shutter_frames):
    """The longest distance any pixel travels during the shutter, over all layers."""
    worst = 0.0
    half = shutter_frames / 2
    for _, vec, _ in layers:
        for t in (-half, half):
            dx, dy = displacement(vec, t)
            worst = max(worst, float(np.hypot(dx, dy).max()))
    return worst * 2  # the path runs from one end of the shutter to the other


def samples_for(path_px):
    s = PB["samples"]
    k = math.ceil(path_px / s["px_per_sample"]) if path_px > 0 else s["min_samples"]
    return int(min(max(k, s["min_samples"]), s["max_samples"]))


def warp(img, depth, dx, dy, ztol=None):
    """Forward-splat premultiplied RGBA along (dx, dy) with bilinear weights and a soft z-test
    (the nearest surface wins a target pixel). Holes — where a layer stretches and no splat lands —
    are filled by normalised 3×3 averaging. Returns (warped image, holes filled)."""
    ztol = PB["depth_test_relative_tolerance"] if ztol is None else ztol
    h, w = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    tx, ty = xs + dx, ys + dy
    x0, y0 = np.floor(tx).astype(np.int64), np.floor(ty).astype(np.int64)
    fx, fy = tx - x0, ty - y0
    z = np.asarray(depth, dtype=np.float64)
    zmin = np.full(h * w, np.inf)
    xr = np.clip(np.rint(tx).astype(np.int64), 0, w - 1)
    yr = np.clip(np.rint(ty).astype(np.int64), 0, h - 1)
    np.minimum.at(zmin, (yr * w + xr).ravel(), z.ravel())
    c = img.shape[2]
    acc = np.zeros((h * w, c))
    wsum = np.zeros(h * w)
    src = img.reshape(-1, c).astype(np.float64)
    zf = z.ravel()
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
    for _ in range(4):
        if filled_mask.all():
            break
        num = np.zeros_like(out)
        den = np.zeros_like(filled_mask)
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                num += np.roll(np.roll(out * filled_mask[..., None], oy, 0), ox, 1)
                den += np.roll(np.roll(filled_mask, oy, 0), ox, 1)
        fill = (filled_mask == 0) & (den > 0)
        out[fill] = num[fill] / den[fill][:, None]
        filled_mask = np.where(fill, 1.0, filled_mask)
    return out.astype(np.float32), holes


def over(front, back):
    return front + back * (1 - front[..., 3:4])


def blur(layers, shutter_frames, samples=None):
    """layers: [(rgba_premultiplied, vector, depth)] ordered FRONT first, as they composite.
    Returns (image, report). The shutter is centred: t runs over ±shutter_frames/2."""
    if not layers:
        raise BlurError("no layers to blur")
    if shutter_frames <= 0:
        raise BlurError(f"shutter_frames {shutter_frames} is not an exposure — a sharp frame is not blurred here")
    path = longest_path_px(layers, shutter_frames)
    k = samples or samples_for(path)
    t0 = time.time()
    ts = [(-0.5 + (i + 0.5) / k) * shutter_frames for i in range(k)]
    accum = None
    holes = 0
    for t in ts:
        comp = None
        for img, vec, dep in reversed(layers):          # BACK first, then over
            dx, dy = displacement(vec, t)
            w, hole = warp(img, dep, dx, dy)
            holes += hole
            comp = w if comp is None else over(w, comp)
        accum = comp.astype(np.float64) if accum is None else accum + comp
    img = (accum / len(ts)).astype(np.float32)
    report = {"samples": k, "longest_path_px": round(path, 2), "shutter_frames": shutter_frames,
              "px_per_sample": round(path / k, 3) if k else None,
              "samples_rule": PB["samples"]["rule"], "samples_status": PB["samples"]["status"] if "status" in PB["samples"] else PB["status"],
              "holes_filled": holes, "seconds": round(time.time() - t0, 2),
              "layers": len(layers), "model": PB["model"]}
    return img, report
