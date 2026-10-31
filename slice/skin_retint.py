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
the residual is the light that did so twice."""
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


def direct_mismatch(skin, dir_m, dir_p):
    """The mean relative difference of the probe's direct diffuse light from the master's on the skin (> 0.5); 0 off it."""
    on = np.asarray(skin) > 0.5
    if not on.any():
        return 0.0
    ref = float(np.abs(dir_m[on]).mean())
    return float(np.abs(dir_p[on] - dir_m[on]).mean()) / ref if ref > 0 else 0.0


def probe_parts(skin, col_m, dir_m, ind_m, comb_m, col_p, dir_p, ind_p, comb_p):
    """(REST, BOUNCE) of one layer, RGB, zero off the skin. Refused when the probe's direct diffuse light on the skin is
    not the master's — then the probe is not the master's render at another albedo (another light, frame or scene)."""
    s = np.asarray(skin, np.float32)[..., None]
    off = direct_mismatch(skin, dir_m, dir_p)
    if off > P["direct_light_match_max"]:
        raise SkinRetintError(f"the probe's direct diffuse light on the skin is {off:.2e} off the master's (at most "
                              f"{P['direct_light_match_max']}) — not the master's render at another albedo")
    rest_m = comb_m[..., :3] - s * col_m * (dir_m + ind_m)
    rest_p = comb_p[..., :3] - s * col_p * (dir_p + ind_p)
    rest = s * (rest_p - rest_m)
    bounce = s * col_m * (ind_p - ind_m)
    if not (np.isfinite(rest).all() and np.isfinite(bounce).all()):
        raise SkinRetintError("REST / BOUNCE: non-finite — a pass carries NaN or Inf")
    return rest.astype(np.float32), bounce.astype(np.float32)


def retint(layer_rgba, skin_diffuse_rgb, gain, weight, rest, bounce):
    """The order's skin tone on one premultiplied layer; alpha and everything off the skin unchanged."""
    g, w = np.asarray(gain, np.float32), np.asarray(weight, np.float32)
    out = np.asarray(layer_rgba, np.float32).copy()
    out[..., :3] += (g - 1.0) * skin_diffuse_rgb[..., :3] + w * rest[..., :3] + g * w * bounce[..., :3]
    return out


def blocks(img, mask, k):
    """Per k×k block: the number of mask pixels and the mean of `img` over them (a block of a thin strip of skin is
    measured on its skin alone — the 2026-09-29 gate's low-pass needed all k² pixels and could not see one)."""
    h, w = mask.shape[0] // k * k, mask.shape[1] // k * k
    m = mask[:h, :w].astype(np.float32)
    n = m.reshape(h // k, k, w // k, k).sum((1, 3))
    s = (img[:h, :w] * m[..., None]).reshape(h // k, k, w // k, k, -1).sum((1, 3))
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
