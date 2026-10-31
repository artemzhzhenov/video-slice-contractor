"""The bake-off's composite-domain negative controls (preregistration §6, protocol §8) — pure numpy on the default head's
layers; the drivers composite the result through the production per-order composite (slice/composite_order.py), so a
control is the order path with one declared thing wrong. FREE: no render.

    M3  flicker      +-amplitude scene-linear luma on alternate frames inside HEAD_HOLDOUT (gross 3 %, near 1 %);
        jitter_layer the near-boundary edge jitter: the layer moved 1 px on odd frames
    M4  shift_layer  SEAM_SHIFTED — the head layer (and its vectors and depth) moved n px along the camera x axis
        scale_layer  HEAD_SCALED — about the silhouette centroid by 1 + n / r_eff
    M6  head_over    the head layer composited over FINAL, i.e. in front of the hand that covered it
    M7  tone_step    the body's tone one step (or a fraction of one) along the master's tone ladder; the head untouched"""
import numpy as np


def shift_layer(arr, dx):
    """arr: H x W x C, moved dx whole pixels along +x; what enters is 0 (transparent, no motion, no depth)."""
    dx = int(dx)
    out = np.zeros_like(arr)
    if dx > 0:
        out[:, dx:] = arr[:, :-dx]
    elif dx < 0:
        out[:, :dx] = arr[:, -dx:]
    else:
        out[:] = arr
    return out


def jitter_layer(arr, px, frame):
    """M3's near-boundary edge jitter: the layer moved px along x on odd frames, left alone on even ones."""
    return shift_layer(arr, px) if int(frame) % 2 else arr.copy()


def _bilinear(arr, xs, ys):
    h, w = arr.shape[:2]
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = (xs - x0)[..., None], (ys - y0)[..., None]
    out = np.zeros(xs.shape + arr.shape[2:], np.float64)
    for oy, wy in ((0, 1 - fy), (1, fy)):
        for ox, wx in ((0, 1 - fx), (1, fx)):
            xi, yi = x0 + ox, y0 + oy
            ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
            v = np.zeros(xs.shape + arr.shape[2:], np.float64)
            v[ok] = arr[yi[ok], xi[ok]]
            out += v * wx * wy
    return out.astype(arr.dtype)


def scale_layer(rgba, grow_px, extra=()):
    """The layer scaled about its silhouette's centroid (alpha >= 0.5) so that its effective radius sqrt(area / pi)
    grows by grow_px; extra layers (vectors, depth) resampled by the same map. Returns (layer, factor[, extras])."""
    m = rgba[..., 3] >= 0.5
    y, x = np.nonzero(m)
    r_eff = np.sqrt(m.sum() / np.pi)
    factor = 1.0 + grow_px / r_eff
    if grow_px == 0:
        return (rgba.copy(), 1.0, [e.copy() for e in extra]) if extra else (rgba.copy(), 1.0)
    cx, cy = x.mean(), y.mean()
    yy, xx = np.mgrid[0:rgba.shape[0], 0:rgba.shape[1]].astype(np.float64)
    xs, ys = cx + (xx - cx) / factor, cy + (yy - cy) / factor
    out = _bilinear(rgba, xs, ys)
    if extra:
        return out, factor, [_bilinear(e, xs, ys) for e in extra]
    return out, factor


def flicker(rgb, holdout, amplitude, frame):
    """FINAL's rgb with the head's luma scaled by 1 - amplitude on even frames and 1 + amplitude on odd ones, weighted
    by HEAD_HOLDOUT's coverage — a gain on all three channels is a gain on luma."""
    sign = 1.0 if int(frame) % 2 else -1.0
    return (rgb * (1.0 + sign * amplitude * holdout[..., None])).astype(rgb.dtype)


def head_over(final_rgba, head_rgba):
    """The head layer over FINAL: wherever the hand (or any front plate) covered the head, the head now covers it."""
    return (head_rgba + final_rgba * (1.0 - head_rgba[..., 3:4])).astype(final_rgba.dtype)


def tone_step(tone, ladder, fraction, off_ladder=None):
    """ladder: {"lightest", "middle", "darkest": linear albedo}. One step from an end is the middle; from the middle it
    is the lightest (declared). fraction scales the step in linear albedo (0.25 = the near-boundary level). A tone off
    the ladder (the default head's own albedo) is refused unless off_ladder="darker": then the step is the ladder's
    upper step (middle - lightest) added to it."""
    t = np.asarray(tone, np.float64)
    names = {k: np.asarray(v, np.float64) for k, v in ladder.items()}
    at = [k for k, v in names.items() if np.allclose(v, t, atol=1e-6)]
    if not at:
        if off_ladder != "darker":
            raise ValueError(f"tone {tone} is not on the ladder {ladder}")
        return (t + fraction * (names["middle"] - names["lightest"])).tolist()
    to = names["lightest"] if at[0] == "middle" else names["middle"]
    return (t + fraction * (to - t)).tolist()
