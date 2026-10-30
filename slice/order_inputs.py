"""The per-order composite's inputs from the order's own renders, in the configuration the owner decided on 2026-10-29
(ADR-0002 amendment 2026-10-29; conventions.json → order_render): (a) the head layer rendered in its screen box and
completed outside it, (b) the shadow layer rendered at half resolution, its multiply formed there by the master's own
formula and returned to full resolution bilinearly. Plain numpy, no renderer: slice/order_render.py renders and calls
these; slice/composite.py forms the master's multiply with the same shadow_multiply.

Nothing here substitutes a value it cannot prove: the region Blender rendered is read back and must be the rectangle it
was given, a box that cut the head stops the frame, and the values written outside the box are read from the box's own
empty pixels."""
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
UNRENDERED = CONV["order_render"]["head_box"]["blender_unrendered"]
SNAP_TOL_PX = 1e-6   # an edge within a millionth of a pixel of a whole pixel is that pixel
BORDER_OFFSET_PX = 0.25   # border_of: where truncation and rounding of a float32 edge × size agree


class OrderInputError(RuntimeError):
    pass


def upsample2_bilinear(img):
    """2× in both directions, bilinear, pixel centres aligned: full-resolution pixel j (centre j + ½) sits at
    half-resolution coordinate j/2 − ¼, i.e. ¾ of the nearer half pixel and ¼ of the next; at the frame's edge the edge
    pixel is held. The interpolation OpenImageIO's resize with filter 'triangle' computes (the filter measured on
    2026-10-29), in float64 and so without that resize's float32 coordinate drift (conventions → order_render.upsample).
    A convex combination: the result never leaves the range of the input."""
    a = np.asarray(img)
    if a.ndim not in (2, 3) or a.shape[0] < 2 or a.shape[1] < 2:
        raise OrderInputError(f"upsample: {a.shape} is not a picture of at least 2 x 2 pixels")
    if not np.isfinite(a).all():
        raise OrderInputError("upsample: non-finite values")
    out = a.astype(np.float64)
    for axis in (0, 1):
        n = out.shape[axis]
        i = np.arange(2 * n)
        near = i // 2
        far = np.clip(np.where(i % 2 == 0, near - 1, near + 1), 0, n - 1)
        out = 0.75 * np.take(out, near, axis) + 0.25 * np.take(out, far, axis)
    return out.astype(np.float32)


def shadow_multiply(shadowed_rgb, body_rgb, eps):
    """conventions → compositor.derived.HEAD_SHADOW_MULTIPLY: the shadowed body over the body, per channel; 1 where the
    body is under epsilon (no information, no darkening); clamped to [0, 1], the clipped fraction reported. The master's
    QC multiply (slice/composite.py) and the order's (slice/order_render.py) are this one function."""
    eps = np.float32(eps)
    safe = body_rgb >= eps
    ratio = np.where(safe, shadowed_rgb / np.where(safe, body_rgb, 1.0), 1.0)
    if not np.isfinite(ratio).all():
        raise OrderInputError("HEAD_SHADOW_MULTIPLY: non-finite ratio — the body plates carry NaN or Inf")
    report = {"clipped_fraction": float(np.mean((ratio < 0) | (ratio > 1))),
              "epsilon_branch_pixel_fraction": float((~safe).any(axis=-1).mean())}
    return np.clip(ratio, 0.0, 1.0).astype(np.float32), report


def _grow(mask, r):
    out = mask.copy()
    for _ in range(r):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def fill_hidden_back(half_rgb, hidden_full, filter_reach_px):
    """The half-resolution multiply with every pixel that can see the hidden back — the back under the order's opaque
    head or the master's opaque front plate — filled from its neighbours that cannot, before the bilinear return. A half
    pixel sees the hidden back when its 2x2 footprint touches it or lies within the render's pixel filter of it
    (filter_reach_px half pixels); its value mixes the visible body with what is hidden, and at the seam that is the open
    neck in deep shadow, which the return would carry onto the visible collar (ADR-0002 amendment 2026-10-29). Each pass
    gives an unfilled pixel the mean of its filled 3x3 neighbours, for at most filter_reach_px + 2 passes — the band a
    visible pixel along the head's outline reads (its own half pixel and the next, beyond the filter's reach). A visible
    pixel deeper inside — a hole enclosed by the head: the mouth seen in profile, a gap in the hair — shows the surface the
    head hides around it, so its half-resolution value stands and is counted (kept_px), never replaced by a value carried
    in from outside the head. Pixels that cannot see the hidden back are returned unchanged; a mean of neighbours never
    leaves their range."""
    h2, w2 = hidden_full.shape[0] // 2, hidden_full.shape[1] // 2
    if half_rgb.shape[:2] != (h2, w2):
        raise OrderInputError(f"the half-resolution multiply {half_rgb.shape[:2]} is not half of the mask {hidden_full.shape}")
    blocks = hidden_full[:2 * h2, :2 * w2].reshape(h2, 2, w2, 2)
    invalid = _grow(blocks.any((1, 3)), filter_reach_px)
    needed = _grow((~blocks).any((1, 3)), 1) & invalid
    reach = filter_reach_px + 2
    m = half_rgb.astype(np.float64).copy()
    filled = ~invalid
    n = 0
    while n < reach and (needed & ~filled).any():
        idx = np.flatnonzero(~filled)
        r, c = idx // w2, idx % w2
        num, den = np.zeros((idx.size, m.shape[-1])), np.zeros(idx.size)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    rr, cc = r + dy, c + dx
                    ok = (rr >= 0) & (rr < h2) & (cc >= 0) & (cc < w2)
                    rr, cc = np.clip(rr, 0, h2 - 1), np.clip(cc, 0, w2 - 1)
                    wgt = filled[rr, cc] & ok
                    num += m[rr, cc] * wgt[:, None]
                    den += wgt
        got = den > 0
        m[r[got], c[got]] = num[got] / den[got][:, None]
        filled[r[got], c[got]] = True
        n += 1
    out = np.where(filled[..., None], m, half_rgb.astype(np.float64))
    return out.astype(np.float32), {"touching_px": int(blocks.any((1, 3)).sum()), "filled_px": int((invalid & filled).sum()),
                                    "kept_px": int((needed & ~filled).sum()), "passes": n, "reach_px": reach,
                                    "filter_reach_px": filter_reach_px}


def _without_contour(mask, edge_px):
    """mask less its contour band of Chebyshev width edge_px (8-neighbour growth of the outside; the frame's edge counts as
    outside)."""
    out = ~mask
    for _ in range(edge_px):
        g = np.pad(out, 1, constant_values=True)
        out = np.logical_or.reduce([g[1 + dy:1 + dy + out.shape[0], 1 + dx:1 + dx + out.shape[1]] for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    return mask & ~out


def head_fill(head_alpha, silhouette, holdout, seam_zone, fill=0.5, edge_px=0, seam_edge_px=0):
    """The per-order gate's fill (owner 2026-10-30, ADR-0002 amendment 2026-10-30): the head layer must fill the ORDER
    head's own silhouette (silhouette: its coverage as L_HEAD sees it — the default head's is HEAD_HOLDOUT, any other
    head's comes from its mattes), and, inside the seam zone only, the default head's silhouette too — there the body
    plate shows the open neck. Fractions of the silhouette's (resp. the zone's default-silhouette) pixels >= fill where
    the head layer's alpha < fill; None where there is nothing to fill. The default head's silhouette beyond the zone is
    reported, not gated: a narrower jaw or other hair is a legitimate head, and behind it the body plate (L_BODY, the head
    excluded) shows what is behind the head. edge_px: the own silhouette's contour band left out (a geometric silhouette
    against a filtered render); seam_edge_px: the default silhouette's contour band left out at the seam (another head's
    neck contour a pixel inside the default one's is not the open neck)."""
    shapes = {np.shape(head_alpha), np.shape(silhouette), np.shape(holdout), np.shape(seam_zone)}
    if len(shapes) != 1:
        raise OrderInputError(f"head_fill: shapes differ {sorted(shapes)}")
    a = np.asarray(head_alpha) >= fill
    own, dflt = np.asarray(silhouette) >= fill, np.asarray(holdout) >= fill
    if edge_px:      # a geometric silhouette's contour and a filtered render's differ by up to a pixel in any direction
        own = _without_contour(own, edge_px)
    # at the seam another head's neck contour may lie a pixel inside the default one's; a gap is still a gap
    seam = (_without_contour(dflt, seam_edge_px) if seam_edge_px else dflt) & np.asarray(seam_zone, bool)
    frac = lambda m: float((m & ~a).sum() / m.sum()) if m.any() else None  # noqa: E731
    return {"unfilled_fraction": frac(own) if own.any() else 1.0, "seam_unfilled_fraction": frac(seam),
            "default_silhouette_unfilled_fraction": frac(dflt), "beyond_default_silhouette_fraction": float((a & ~dflt).sum() / max(int(dflt.sum()), 1)),
            "silhouette_px": int(own.sum()), "seam_zone_default_px": int(seam.sum())}


def pixel_rect(box, width, height):
    """(c0, c1, r0, r1) — columns, then rows top-down, ends exclusive — of a box (x0, x1, y0, y1) in frame fractions with
    y up: widened outward to whole pixels and clipped to the frame."""
    x0, x1, y0, y1 = box
    c0 = math.floor(x0 * width + SNAP_TOL_PX)
    c1 = math.ceil(x1 * width - SNAP_TOL_PX)
    r0 = math.floor((1 - y1) * height + SNAP_TOL_PX)
    r1 = math.ceil((1 - y0) * height - SNAP_TOL_PX)
    return max(0, c0), min(width, c1), max(0, r0), min(height, r1)


def border_of(rect, width, height):
    """The border (min_x, max_x, min_y, max_y; y up) that makes Blender render exactly a whole-pixel rectangle. Blender
    keeps each edge as float32 and turns edge × size into a pixel edge: given exactly c / size an edge can land one pixel
    short (measured 2026-10-29: 971/3840 rendered from column 970), so each edge is given a quarter pixel past its pixel
    edge, where truncation and rounding both land on it; the frame's own edges are 0 and 1."""
    c0, c1, r0, r1 = rect
    at = lambda p, size: min(1.0, (p + BORDER_OFFSET_PX) / size) if p else 0.0
    return at(c0, width), at(c1, width), at(height - r1, height), at(height - r0, height)


def complete_boxed_head(rgba, vec, depth, rect, cut_edge_px):
    """A head layer rendered inside `rect` (a border, the rest of the frame left unrendered) completed into the layer a
    full-frame render would have written: outside the rectangle colour 0, vectors 0 and the empty depth — what the
    full-frame L_HEAD holds wherever the head's alpha is 0. Refused, never guessed: when the region Blender rendered is
    not `rect`; when colour lies outside it; when the head reaches a side of the rectangle that is not the frame's edge
    (the box cut it); when the rectangle's own empty pixels disagree on the depth or carry motion. Returns copies and a
    report for the manifest."""
    H, W = depth.shape
    c0, c1, r0, r1 = rect
    unrendered = (vec == np.float32(UNRENDERED["vector"])).all(axis=-1)
    rows, cols = np.flatnonzero((~unrendered).any(axis=1)), np.flatnonzero((~unrendered).any(axis=0))
    if rows.size == 0:
        raise OrderInputError("the boxed head render rendered nothing")
    seen = (int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1)
    inside = np.zeros((H, W), bool)
    inside[r0:r1, c0:c1] = True
    if seen != tuple(rect) or unrendered[inside].any():
        raise OrderInputError(f"rendered region {list(seen)} (columns, rows, ends exclusive) is not the box asked for {list(rect)} "
                              f"— Blender rounded the border another way or left pixels inside it unrendered")
    outside = ~inside
    if outside.any() and (rgba[outside] != np.float32(UNRENDERED["colour"])).any():
        raise OrderInputError(f"colour outside the rendered region {list(rect)}: {int((rgba[outside] != 0).any(-1).sum())} px")
    alpha = rgba[..., 3]
    e = cut_edge_px
    bands = {"left": alpha[r0:r1, c0:c0 + e] if c0 > 0 else None, "right": alpha[r0:r1, c1 - e:c1] if c1 < W else None,
             "top": alpha[r0:r0 + e, c0:c1] if r0 > 0 else None, "bottom": alpha[r1 - e:r1, c0:c1] if r1 < H else None}
    edge_max = {side: float(b.max()) for side, b in bands.items() if b is not None}
    cut = {side: v for side, v in edge_max.items() if v > 0}
    if cut:
        raise OrderInputError(f"the box {list(rect)} cut the head: alpha on its {', '.join(cut)} edge "
                              f"(max {max(cut.values()):.4g} within {e} px) — widen the margin (conventions → order_render.head_box)")
    report = {"rendered_region": list(rect), "interior_sides": sorted(edge_max), "edge_alpha_max": edge_max,
              "filled_px": int(outside.sum()), "empty_depth": None,
              "left_outside_by_blender": {"depth": sorted({float(v) for v in np.unique(depth[outside])[:4]}) if outside.any() else []}}
    rgba, vec, depth = rgba.copy(), vec.copy(), depth.copy()
    if not outside.any():
        return rgba, vec, depth, report
    empty = inside & (alpha == 0)
    if not empty.any():
        raise OrderInputError(f"the box {list(rect)} has no empty pixel to read the empty depth from")
    depths = np.unique(depth[empty])
    if depths.size != 1 or (vec[empty] != 0).any():
        raise OrderInputError(f"the box's empty pixels disagree: {depths.size} depths ({depths[:4].tolist()}…), "
                              f"{int((vec[empty] != 0).any(-1).sum())} carry motion — the empty value cannot be read, so the outside is not filled")
    rgba[outside] = 0.0
    vec[outside] = 0.0
    depth[outside] = depths[0]
    report["empty_depth"] = float(depths[0])
    return rgba, vec, depth, report


# ---- the output directory: one idempotency key per directory; frames verified in staging are kept across a failure

def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verified(root, outputs):
    return all((root / o["path"]).exists() and sha256_file(root / o["path"]) == o["sha256"] for o in outputs.values())


def prepare_output(out, key, kind):
    """The staging directory to render into under `key`, or None when <out> already holds a PASS under this key whose
    every file is what its manifest recorded (a verified no-op). Another key's manifest or staging is refused: an
    output directory belongs to one (order, inputs, settings, code)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    mpath, staging = out / f"{kind}_manifest.json", out / ".staging"
    if mpath.exists():
        prev = json.loads(mpath.read_text())
        if prev.get("idempotency_key") != key:
            raise OrderInputError(f"{out} holds {kind} output under idempotency key {str(prev.get('idempotency_key'))[:12]}, not this run's "
                                  f"{key[:12]} — one output directory per key; use another directory")
        if prev.get("status") == "PASS" and all(_verified(out, fr["outputs"]) for fr in prev["frames"]):
            return None
    if staging.exists():
        kf = staging / "KEY"
        if not kf.exists() or kf.read_text() != key:
            raise OrderInputError(f"{staging} was staged under another key — remove it or use another directory")
    else:
        staging.mkdir()
        (staging / "KEY").write_text(key)
    return staging


def staged_frame(staging, frame):
    """The record of a frame already rendered under this staging's key, if every output it lists is there with its hash."""
    rec = Path(staging) / f"frame.{frame:04d}.json"
    if not rec.exists():
        return None
    r = json.loads(rec.read_text())
    return r if _verified(Path(staging), r["outputs"]) else None


def finish_output(out, staging, manifest, kind, keep_raw):
    """Every frame passed: move the outputs into <out>, keep raw renders only when asked, write the manifest PASS."""
    import shutil
    out, staging = Path(out), Path(staging)
    for r in manifest["frames"]:
        for o in r["outputs"].values():
            dst = out / o["path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            (staging / o["path"]).replace(dst)
    if keep_raw and (staging / "raw").exists():
        if (out / "raw").exists():
            shutil.rmtree(out / "raw")
        (staging / "raw").replace(out / "raw")
    shutil.rmtree(staging)
    manifest["status"] = "PASS"
    (out / f"{kind}_manifest.json").write_text(json.dumps(manifest, indent=1, allow_nan=False) + "\n")
