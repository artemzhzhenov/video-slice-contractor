"""The order's skin tone between two renders of the master — its own and a probe with the hero skin at a darker tone
(ADR-0002 amendment 2026-10-31, amending 2026-09-29's C3). numpy only: the per-order composite, the master's derivation
of SKIN_PROBE_BUNDLE (slice/skin_probe.py) and the skin-tone gate (slice/check_skin_tone.py) all call these.

Per pixel and channel the skin's indirect diffuse light and the layer's non-diffuse rest are taken as linear in the skin
albedo, through the master (a_m) and the probe (a_p); the direct light does not depend on it. With
gain g = a_t / a_m and weight w = (a_t − a_m) / (a_p − a_m) for the order's albedo a_t:

    LAYER' = LAYER + (g − 1)·SKIN_DIFFUSE + w·REST + g·w·BOUNCE
    BOUNCE = skin · DiffCol_m · (DiffInd_p − DiffInd_m)
    REST   = skin · [(C_p − skin·DiffCol_p·(DiffDir_p + DiffInd_p)) − (C_m − skin·DiffCol_m·(DiffDir_m + DiffInd_m))]

skin the layer's own body-skin coverage, C the layer's Combined RGB. Exact where light reached the skin off skin once;
the residual is the light that did so twice.

At the pixels the skin shares with another surface (SHARED — conventions → skin_tone.probe.edge; owner 2026-11-01,
decision 13 (A)) the Diffuse Color is the surfaces' colours mixed, and SKIN_DIFFUSE takes all of it for the skin's.
There the pixel's own change between the two renders is weighted instead — exact where its light is linear in the albedo:

    LAYER' = LAYER + w·EDGE        EDGE = C_p − C_m"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
P = json.loads((ROOT / "slice" / "conventions.json").read_text())["skin_tone"]["probe"]


class SkinRetintError(RuntimeError):
    pass


def gain_and_weight(target, master, probe):
    """Per channel: the gain on the master's diffuse light and the weight of the probe's difference."""
    t, m, p = (np.asarray(x, np.float32) for x in (target, master, probe))
    if t.shape != (3,) or m.shape != (3,) or p.shape != (3,):
        raise SkinRetintError(f"three channels each: target {t.tolist()}, master {m.tolist()}, probe {p.tolist()}")
    if (np.abs(p - m) < 1e-6).any() or (m <= 0).any():
        raise SkinRetintError(f"the probe's albedo {p.tolist()} must differ from the master's {m.tolist()} in every channel, the master's be positive")
    return t / m, (t - m) / (p - m)


def grain(scale=1.0):
    """(block px, erode px) at a render's scale: direct_light_interior's are image area at 100 %."""
    c = P["direct_light_interior"]
    return max(2, int(c["block_px"] * scale + 0.5)), int(c["erode_px"] * scale + 0.5)


def interior(skin, scale=1.0):
    """The skin's interior: full coverage, the erode px in from every pixel that is not (P → direct_light_interior)."""
    c = P["direct_light_interior"]
    full = np.asarray(skin) >= c["coverage_min"]
    r = grain(scale)[1]
    pad = np.pad(full, r, constant_values=False)
    out = full.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out &= pad[r + dy:r + dy + full.shape[0], r + dx:r + dx + full.shape[1]]
    return out


def direct_mismatch(skin, dir_m, dir_p, scale=1.0):
    """How far the probe's direct diffuse light is from the master's inside the skin: over the blocks of the interior, the
    mean of |the block's mean difference| (channels averaged) relative to the master's mean there; None when no block
    is interior enough to measure. Inside the skin the albedo leaves the direct light alone but for sampling noise, which
    the blocks average away; at pixels the skin shares with another surface Cycles' pass weights the light by each
    surface's colour, so the edge is left out (measured 2026-11-01, conventions → direct_light_interior_note). `scale`:
    the render's resolution_percentage / 100."""
    c = P["direct_light_interior"]
    inner = interior(skin, scale)
    k = grain(scale)[0]
    d_m = np.asarray(dir_m, np.float32)[..., :3]
    n, diff = blocks(np.asarray(dir_p, np.float32)[..., :3] - d_m, inner, k)
    _, ref = blocks(np.abs(d_m), inner, k)
    keep = n >= c["block_min_fraction"] * k * k
    if not keep.any():
        return None
    ref = float(ref[keep].mean())
    return float(np.abs(diff[keep]).mean()) / ref if ref > 0 else 0.0


def probe_parts(skin, col_m, dir_m, ind_m, comb_m, col_p, dir_p, ind_p, comb_p, scale=1.0):
    """(REST, BOUNCE) of one layer, RGB, zero off the skin. Refused when the probe's direct diffuse light inside the skin
    is not the master's — then the probe is not the master's render at another albedo (another light, frame or scene).
    A layer whose skin has no interior to measure is not refused here; the caller counts what was measured."""
    s = np.asarray(skin, np.float32)[..., None]
    off = direct_mismatch(skin, dir_m, dir_p, scale)
    if off is not None and off > P["direct_light_match_max"]:
        raise SkinRetintError(f"the probe's direct diffuse light on the skin is {off:.2e} off the master's (at most "
                              f"{P['direct_light_match_max']}) — not the master's render at another albedo")
    rest_m = comb_m[..., :3] - s * col_m * (dir_m + ind_m)
    rest_p = comb_p[..., :3] - s * col_p * (dir_p + ind_p)
    rest = s * (rest_p - rest_m)
    bounce = s * col_m * (ind_p - ind_m)
    if not (np.isfinite(rest).all() and np.isfinite(bounce).all()):
        raise SkinRetintError("REST / BOUNCE: non-finite — a pass carries NaN or Inf")
    return rest.astype(np.float32), bounce.astype(np.float32)


def edge_parts(skin, col_m, comb_m, col_p, comb_p, master_albedo, probe_albedo):
    """(EDGE RGB, SHARED H×W×1) of one layer: SHARED 1 on the pixels the skin shares with another surface — its coverage
    above 0 and below edge.coverage_min, or the probe's Diffuse Color over the master's off the albedos' ratio by more
    than edge.colour_ratio_off_max in a channel — and EDGE = C_p − C_m there, both zero elsewhere."""
    e = P["edge"]
    s = np.asarray(skin, np.float32)
    want = np.asarray(probe_albedo, np.float32) / np.asarray(master_albedo, np.float32)
    off = np.abs(np.asarray(col_p, np.float32)[..., :3] / np.maximum(np.asarray(col_m, np.float32)[..., :3], 1e-6) / want - 1.0).max(-1)
    shared = (s > 0) & ((s < e["coverage_min"]) | (off > e["colour_ratio_off_max"]))
    edge = np.where(shared[..., None], np.asarray(comb_p, np.float32)[..., :3] - np.asarray(comb_m, np.float32)[..., :3], 0.0)
    if not np.isfinite(edge).all():
        raise SkinRetintError("EDGE: non-finite — a pass carries NaN or Inf")
    return edge.astype(np.float32), shared[..., None].astype(np.float32)


def retint(layer_rgba, skin_diffuse_rgb, gain, weight, rest, bounce, edge, shared):
    """The order's skin tone on one premultiplied layer: the probe formula inside the skin, the pixel's own change at
    the pixels it shares (SHARED); alpha and everything off the skin unchanged."""
    g, w = np.asarray(gain, np.float32), np.asarray(weight, np.float32)
    out = np.asarray(layer_rgba, np.float32).copy()
    inside = (g - 1.0) * skin_diffuse_rgb[..., :3] + w * rest[..., :3] + g * w * bounce[..., :3]
    out[..., :3] += np.where(np.asarray(shared)[..., :1] > 0.5, w * edge[..., :3], inside)
    return out


def blocks(img, mask, k):
    """Per k×k block: the number of mask pixels and the mean of `img` over them (a block of a thin strip of skin is
    measured on its skin alone — the 2026-09-29 gate's low-pass needed all k² pixels and could not see one)."""
    h, w = mask.shape[0] // k * k, mask.shape[1] // k * k
    m = mask[:h, :w].astype(np.float32)
    n = m.reshape(h // k, k, w // k, k).sum((1, 3))
    s = (img[:h, :w] * m[..., None]).reshape(h // k, k, w // k, k, img.shape[-1]).sum((1, 3))
    return n, s / np.maximum(n, 1.0)[..., None]


def measure(got, truth, src, mask, k, min_px):
    """The gate's numbers for one layer, tone and frame: over the k×k blocks holding at least min_px mask pixels, the
    largest channel difference of the block means relative to the truth's mean — its mean, 99th percentile and maximum —
    and the same for the master without a re-tint (the negative control). None when no block counts."""
    n, gm = blocks(np.asarray(got, np.float32)[..., :3], mask, k)
    _, tm = blocks(np.asarray(truth, np.float32)[..., :3], mask, k)
    _, sm = blocks(np.asarray(src, np.float32)[..., :3], mask, k)
    sel = n >= min_px
    if not sel.any():
        return None
    scale = float(tm[sel].mean())
    e = np.abs(gm - tm).max(-1)[sel] / scale
    e0 = np.abs(sm - tm).max(-1)[sel] / scale
    return {"blocks": int(sel.sum()), "relative_error": float(e.mean()), "relative_error_p99": float(np.percentile(e, 99)),
            "relative_error_max": float(e.max()), "no_retint_relative_error": float(e0.mean())}
