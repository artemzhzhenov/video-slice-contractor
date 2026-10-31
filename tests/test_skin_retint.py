"""slice/skin_retint.py — the skin re-tint between the master and a probe render (ADR-0002 amendment 2026-10-31; CI, numpy
only). A synthetic layer whose light is known: the rest and the skin's indirect light linear in the skin albedo — light
that bounced off skin once — and the direct light independent of it."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import skin_retint as sr  # noqa: E402

MASTER = np.array([0.8, 0.55, 0.45], np.float32)
PROBE = np.array([0.15, 0.08, 0.05], np.float32)
H, W = 8, 12


def scene(albedo, seed=0):
    """One layer rendered at a skin albedo: skin coverage, the diffuse colour, direct and indirect light, Combined RGBA."""
    rng = np.random.default_rng(seed)
    skin = np.zeros((H, W), np.float32)
    skin[2:6, 3:9] = 1.0
    skin[2:6, 9] = 0.6                                # a partly covered edge
    d = rng.uniform(0.2, 1.0, (H, W, 3)).astype(np.float32)           # direct light: no skin on its path
    i0 = rng.uniform(0.05, 0.2, (H, W, 3)).astype(np.float32)         # indirect light from everything but skin
    i1 = rng.uniform(0.0, 0.3, (H, W, 3)).astype(np.float32)          # ... and from skin, once: ∝ the albedo
    r0 = rng.uniform(0.0, 0.05, (H, W, 3)).astype(np.float32)         # specular and the rest
    r1 = rng.uniform(0.0, 0.04, (H, W, 3)).astype(np.float32)         # ... the skin's reflection of skin
    a = np.asarray(albedo, np.float32)
    col = skin[..., None] * a + (1 - skin[..., None]) * 0.3           # Cycles' Diffuse Color: the albedo where skin is
    ind = i0 + i1 * a
    rgb = r0 + r1 * a + col * (d + ind)
    comb = np.concatenate([rgb, np.ones((H, W, 1), np.float32)], -1)
    return {"skin": skin, "col": col, "dir": d, "ind": ind, "comb": comb}


def first_order(m, gain):
    sd = m["skin"][..., None] * m["col"] * (m["dir"] + m["ind"])
    out = m["comb"].copy()
    out[..., :3] += (gain - 1) * sd
    return out, sd


@pytest.mark.parametrize("target", [[0.2, 0.11, 0.07], [0.55, 0.38, 0.28], [0.9, 0.72, 0.62]])
def test_the_probe_re_tint_is_exact_where_skin_light_is_first_order_and_the_first_order_re_tint_is_not(target):
    m, p, t = scene(MASTER), scene(PROBE), scene(target)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    gain, w = sr.gain_and_weight(target, MASTER, PROBE)
    _, sd = first_order(m, gain)
    got = sr.retint(m["comb"], sd, gain, w, rest, bounce)
    on = m["skin"] > 0.99
    assert np.abs(got - t["comb"])[on].max() < 1e-5
    c3, _ = first_order(m, gain)
    assert np.abs(c3 - t["comb"])[on].max() > 1e-3, "the 2026-09-29 re-tint misses the light skin threw on skin"


def test_at_the_masters_tone_nothing_changes_and_at_the_probes_the_probe_is_reproduced():
    m, p = scene(MASTER), scene(PROBE)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    gain, w = sr.gain_and_weight(MASTER, MASTER, PROBE)
    assert np.all(w == 0) and np.allclose(gain, 1)
    _, sd = first_order(m, gain)
    assert np.array_equal(sr.retint(m["comb"], sd, gain, w, rest, bounce), m["comb"])
    gain, w = sr.gain_and_weight(PROBE, MASTER, PROBE)
    _, sd = first_order(m, gain)
    on = m["skin"] > 0.99
    assert np.abs(sr.retint(m["comb"], sd, gain, w, rest, bounce) - p["comb"])[on].max() < 1e-5


def test_away_from_the_skin_the_probe_changes_nothing_and_alpha_never_changes():
    m, p = scene(MASTER), scene(PROBE)
    p["comb"][..., :3] += 0.01 * (1 - m["skin"][..., None])          # the probe differs off the skin (noise, cloth lit by skin)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    off = m["skin"] == 0
    assert not rest[off].any() and not bounce[off].any()
    gain, w = sr.gain_and_weight([0.2, 0.11, 0.07], MASTER, PROBE)
    _, sd = first_order(m, gain)
    got = sr.retint(m["comb"], sd, gain, w, rest, bounce)
    assert np.array_equal(got[off], m["comb"][off]) and np.array_equal(got[..., 3], m["comb"][..., 3])


def test_a_probe_that_is_not_the_masters_render_at_another_tone_is_refused():
    m, p = scene(MASTER), scene(PROBE)
    p["dir"] = p["dir"] * 1.05                                         # another light, another frame, another scene
    with pytest.raises(sr.SkinRetintError, match="direct"):
        sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])


def test_a_probe_at_the_masters_tone_in_any_channel_is_refused():
    with pytest.raises(sr.SkinRetintError, match="probe"):
        sr.gain_and_weight([0.2, 0.11, 0.07], MASTER, [0.15, 0.55, 0.05])


def test_blocks_average_the_skin_pixels_so_a_thin_strip_is_measured():
    mask = np.zeros((16, 16), bool)
    mask[5:7, :] = True                                                # 2 px wide: no 4×4 block is all skin
    img = np.zeros((16, 16, 3), np.float32)
    img[mask] = 0.5
    img[~mask] = 9.0                                                   # never read
    n, mean = sr.blocks(img, mask, 4)
    assert n.max() == 8 and (n == 16).sum() == 0
    assert np.allclose(mean[n > 0], 0.5)


def test_the_measure_reports_mean_and_percentile_over_the_counted_blocks():
    mask = np.ones((16, 16), bool)
    truth = np.full((16, 16, 3), 0.5, np.float32)
    got = truth.copy()
    got[:4, :4] += 0.25                                                # one block of 16 off by 50 %
    r = sr.measure(got, truth, truth, mask, k=4, min_px=8)
    assert r["blocks"] == 16
    assert r["relative_error"] == pytest.approx(0.5 / 16)
    assert r["relative_error_p99"] == pytest.approx(np.percentile([0.5] + [0.0] * 15, 99))
    assert r["no_retint_relative_error"] == 0.0
    assert sr.measure(got, truth, truth, np.zeros((16, 16), bool), k=4, min_px=8) is None
