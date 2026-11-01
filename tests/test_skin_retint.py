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


Z_MAX = sr.P["direct_light_z_max"]
N = 64                                                                 # a layer the guard's 16 px blocks fit in


def light(n, shift=0.0, seed=0):
    """Direct light as a render has it: smooth over the image (a lamp, a window), per channel; `shift` moves it by px."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = np.asarray([0.0, 0.4, 0.9], np.float32)
    return (0.6 + 0.3 * np.sin((xx[..., None] + shift) / 7.0 + c) * np.cos(yy[..., None] / 9.0 + c)).astype(np.float32)


def square_skin(n):
    """A square of skin with a ring of partly covered pixels around it (pixels shared with cloth or hair)."""
    skin = np.zeros((n, n), np.float32)
    a, b = n // 8, n - n // 8
    skin[a:b, a:b] = 1.0
    skin[a - 1, a:b] = skin[b, a:b] = skin[a:b, a - 1] = skin[a:b, b] = 0.6
    return skin


def first_order(m, gain):
    sd = m["skin"][..., None] * m["col"] * (m["dir"] + m["ind"])
    out = m["comb"].copy()
    out[..., :3] += (gain - 1) * sd
    return out, sd


@pytest.mark.parametrize("target", [[0.2, 0.11, 0.07], [0.55, 0.38, 0.28], [0.9, 0.72, 0.62]])
def test_the_probe_re_tint_is_exact_where_skin_light_is_first_order_and_the_first_order_re_tint_is_not(target):
    m, p, t = scene(MASTER), scene(PROBE), scene(target)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    edge, shared = sr.edge_parts(m["skin"], m["col"], m["comb"], p["col"], p["comb"], MASTER, PROBE)
    gain, w = sr.gain_and_weight(target, MASTER, PROBE)
    _, sd = first_order(m, gain)
    got = sr.retint(m["comb"], sd, gain, w, rest, bounce, edge, shared)
    on = m["skin"] > 0.99
    assert np.abs(got - t["comb"])[on].max() < 1e-5
    c3, _ = first_order(m, gain)
    assert np.abs(c3 - t["comb"])[on].max() > 1e-3, "the 2026-09-29 re-tint misses the light skin threw on skin"


def test_at_the_masters_tone_nothing_changes_and_at_the_probes_the_probe_is_reproduced():
    m, p = scene(MASTER), scene(PROBE)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    edge, shared = sr.edge_parts(m["skin"], m["col"], m["comb"], p["col"], p["comb"], MASTER, PROBE)
    gain, w = sr.gain_and_weight(MASTER, MASTER, PROBE)
    assert np.all(w == 0) and np.allclose(gain, 1)
    _, sd = first_order(m, gain)
    assert np.array_equal(sr.retint(m["comb"], sd, gain, w, rest, bounce, edge, shared), m["comb"])
    gain, w = sr.gain_and_weight(PROBE, MASTER, PROBE)
    _, sd = first_order(m, gain)
    on = m["skin"] > 0                                                 # the partly covered edge too
    assert np.abs(sr.retint(m["comb"], sd, gain, w, rest, bounce, edge, shared) - p["comb"])[on].max() < 1e-5


def test_away_from_the_skin_the_probe_changes_nothing_and_alpha_never_changes():
    m, p = scene(MASTER), scene(PROBE)
    p["comb"][..., :3] += 0.01 * (1 - m["skin"][..., None])          # the probe differs off the skin (noise, cloth lit by skin)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    edge, shared = sr.edge_parts(m["skin"], m["col"], m["comb"], p["col"], p["comb"], MASTER, PROBE)
    off = m["skin"] == 0
    assert not rest[off].any() and not bounce[off].any() and not edge[off].any() and not shared[off].any()
    gain, w = sr.gain_and_weight([0.2, 0.11, 0.07], MASTER, PROBE)
    _, sd = first_order(m, gain)
    got = sr.retint(m["comb"], sd, gain, w, rest, bounce, edge, shared)
    assert np.array_equal(got[off], m["comb"][off]) and np.array_equal(got[..., 3], m["comb"][..., 3])


def shared_scene(albedo, s=0.6, cloth=0.3):
    """A layer whose skin shares a ring of pixels with cloth (coverage s), as Cycles renders such a pixel: its Diffuse
    Color is the two surfaces' colours mixed by coverage, its light each surface's own — the cloth lit by light off the
    skin, the skin by none. The pixel's light is linear in the albedo; what C2's SKIN_DIFFUSE calls its skin is not."""
    skin = square_skin(N)
    skin[skin == 0.6] = s
    d = light(N)
    i0 = 0.1 + 0.05 * light(N, shift=11.0)                           # indirect light from everything but skin
    a, sk = np.asarray(albedo, np.float32), skin[..., None]
    total = sk * a * (d + i0) + (1 - sk) * cloth * (d + i0 + 0.2 * a)  # each surface's colour × its own light
    col = sk * a + (1 - sk) * cloth
    comb = np.concatenate([0.02 + total, np.ones((N, N, 1), np.float32)], -1).astype(np.float32)
    return {"skin": skin, "col": col.astype(np.float32), "dir": d, "ind": (total / col - d).astype(np.float32), "comb": comb}


@pytest.mark.parametrize("target", [[0.2, 0.11, 0.07], [0.55, 0.38, 0.28], [0.9, 0.72, 0.62]])
def test_at_pixels_the_skin_shares_with_cloth_the_pixels_own_change_is_taken_and_is_exact_where_its_light_is_linear(target):
    """Measured 2026-11-01 (slice/measurements/skin_tone_interreflection_2026-10-31/README.md, "The gate with the probe,
    and the edge"): inside the skin the probe re-tint holds; 86–100 % of the gate's remaining error is the pixels the skin
    shares with cloth, where SKIN_DIFFUSE takes the cloth's share of the colour for the skin's. There the pixel's own
    change between the master and the probe is weighted instead (owner, 2026-11-01, decision 13 (A))."""
    m, p, t = shared_scene(MASTER), shared_scene(PROBE), shared_scene(target)
    rest, bounce = sr.probe_parts(m["skin"], m["col"], m["dir"], m["ind"], m["comb"], p["col"], p["dir"], p["ind"], p["comb"])
    edge, shared = sr.edge_parts(m["skin"], m["col"], m["comb"], p["col"], p["comb"], MASTER, PROBE)
    ring = (m["skin"] > 0) & (m["skin"] < 0.999)
    assert np.array_equal(shared[..., 0] > 0.5, ring), "shared: the pixels the skin covers in part, and only those here"
    gain, w = sr.gain_and_weight(target, MASTER, PROBE)
    sd = m["skin"][..., None] * m["col"] * (m["dir"] + m["ind"])
    got = sr.retint(m["comb"], sd, gain, w, rest, bounce, edge, shared)
    on = m["skin"] > 0
    assert np.abs(got - t["comb"])[on].max() < 1e-5
    interior_rule = sr.retint(m["comb"], sd, gain, w, rest, bounce, edge, np.zeros_like(shared))
    assert np.abs(interior_rule - t["comb"])[ring].max() > 1e-3, "the probe formula at the edge: the 2026-11-01 gate's error"


def test_a_fully_covered_pixel_whose_colour_is_not_the_skins_alone_is_shared():
    """Coverage alone does not see every shared pixel: where the probe's Diffuse Color over the master's is off the
    albedos' ratio, the pixel's colour holds another surface's (conventions → skin_tone.probe.edge)."""
    m, p = scene(MASTER), scene(PROBE)
    lim = sr.P["edge"]["colour_ratio_off_max"]
    p["col"][3, 4] *= 1.0 + 2 * lim                                   # inside the skin: a colour off the ratio
    p["col"][3, 5] *= 1.0 + lim / 2                                   # ... and one within it
    _, shared = sr.edge_parts(m["skin"], m["col"], m["comb"], p["col"], p["comb"], MASTER, PROBE)
    assert m["skin"][3, 4] == 1.0 and shared[3, 4, 0] == 1.0
    assert m["skin"][3, 5] == 1.0 and shared[3, 5, 0] == 0.0
    assert shared[2:6, 9, 0].all(), "the partly covered edge"
    assert not shared[m["skin"] == 0].any()


def test_the_edge_parts_refuse_non_finite_passes():
    m, p = scene(MASTER), scene(PROBE)
    p["comb"][3, 9, 0] = np.nan                                       # at the partly covered edge (inside, REST refuses it)
    with pytest.raises(sr.SkinRetintError, match="EDGE"):
        sr.edge_parts(m["skin"], m["col"], m["comb"], p["col"], p["comb"], MASTER, PROBE)


def noisy(d, sigma, seed):
    """A render's direct light with independent per-pixel sampling noise of relative size sigma (zero mean)."""
    return (d * (1.0 + np.random.default_rng(seed).normal(0.0, sigma, d.shape))).astype(np.float32)


M = 128                                                                # a layer with many of the guard's blocks


def test_a_probe_that_is_not_the_masters_render_at_another_tone_is_refused():
    skin, d = square_skin(M), light(M)
    z = np.zeros((M, M, 3), np.float32)
    comb = np.ones((M, M, 4), np.float32)
    for wrong in (noisy(d * 1.05, 0.009, 2), noisy(light(M, shift=3.0), 0.009, 2)):   # another light; the next frame
        with pytest.raises(sr.SkinRetintError, match="noise"):
            sr.probe_parts(skin, z + 0.8, noisy(d, 0.009, 1), z, comb, z + 0.15, wrong, z, comb)


@pytest.mark.parametrize("scale", [1.0, 0.25, 0.1])
@pytest.mark.parametrize("sigma", [0.005, 0.02, 0.08])
def test_an_honest_probe_is_of_order_one_in_noise_units_at_any_scale_and_any_noise(scale, sigma):
    """Burst 6 review Q79-2 (2026-11-01): the absolute guard's honest value grew as the blocks shrank with the render's
    scale (at the gate's 25 % 1.0–1.5e-3 against 0.002) and with the noise (CPU, fewer samples). In units of its own
    noise the master's render at another albedo is of order 1 whatever the block, the samples or the device."""
    skin, d = square_skin(M), light(M)
    got = sr.direct_mismatch(skin, noisy(d, sigma, 1), noisy(d, sigma, 2), scale)
    assert got is not None and got < 0.75 * Z_MAX, "white noise is about 1; the renders' blue noise 0.37–0.77 (2026-11-01)"


@pytest.mark.parametrize("scale", [1.0, 0.25])
def test_a_light_two_percent_brighter_or_the_next_frame_is_refused_at_the_production_and_the_gates_scale(scale):
    """Measured on SHOT_003 (2026-11-01, archive reviews/burst-6_review_2026-11-01): light ×1.02 10–68, the next frame
    14–830, the honest probe 0.4–0.8. The synthetic noise here is the measured 0.9 % per pixel."""
    skin, d = square_skin(M), light(M)
    m = noisy(d, 0.009, 1)
    assert sr.direct_mismatch(skin, m, noisy(d * 1.02, 0.009, 2), scale) > Z_MAX
    assert sr.direct_mismatch(skin, m, noisy(light(M, shift=2.0), 0.009, 2), scale) > Z_MAX


def test_sampling_noise_inside_the_skin_and_colour_weighted_light_at_its_edge_are_not_another_render():
    """Measured 2026-11-01 on the master's probe (slice/measurements/skin_tone_interreflection_2026-10-31/): inside the
    skin the probe's direct light is 0.5–0.9 % per pixel off the master's with a zero mean — sampling noise; at pixels the
    skin shares with cloth, Cycles' direct pass is the light weighted by each surface's colour, so a darker skin moves it
    by 4–11 %. Neither is another light, frame or scene: the edge is outside the interior the guard measures."""
    skin, d = square_skin(M), light(M)
    p = noisy(d, 0.009, 2)
    p[(skin > 0.5) & (skin < 0.999)] *= 1.3
    got = sr.direct_mismatch(skin, noisy(d, 0.009, 1), p)
    assert got is not None and got < 0.75 * Z_MAX
    z = np.zeros((M, M, 3), np.float32)
    sr.probe_parts(skin, z + 0.8, noisy(d, 0.009, 1), z, np.ones((M, M, 4), np.float32), z + 0.15, p, z, np.ones((M, M, 4), np.float32))


def test_identical_blocks_are_zero_and_a_change_without_noise_is_refused():
    """A bit-identical probe (the control at the master's own tone) is 0; a difference with no noise in it at all is no
    sampling noise — infinitely many noise units."""
    skin, d = square_skin(M), light(M)
    assert sr.direct_mismatch(skin, d, d) == 0.0
    assert sr.direct_mismatch(skin, d, d * 1.01) > Z_MAX
    assert sr.direct_mismatch(skin, d, d + np.float32(0.001)) > Z_MAX


def test_the_guards_grain_is_set_at_100_percent_follows_the_renders_scale_and_keeps_four_pixels_a_side():
    """block_px and erode_px are image area at 100 %: a render at 25 % measures the same skin with 4 px blocks, 1 px in.
    Below 25 % the block stays 4 px: a block of 2 × 2 px leaves its noise estimate one or three degrees of freedom, and
    the honest probe's z heavy tails (Q79-2)."""
    assert sr.grain(1.0)[0] == 16 and sr.grain(0.25)[0] == 4 and sr.grain(0.1)[0] == 4
    skin = np.zeros((M, M), np.float32)
    skin[20:60, 20:60] = 1.0                                           # 40 px: a few 16 px blocks, many of 4 px
    d = light(M)
    assert sr.direct_mismatch(skin, d, d * 1.01) is None
    assert sr.direct_mismatch(skin, d, noisy(d, 0.009, 2), scale=0.25) is not None
    assert sr.direct_mismatch(skin, d, d, scale=0.25) == 0.0


def test_a_layer_with_fewer_blocks_than_the_minimum_is_not_measured():
    """A root mean square over a handful of blocks is a handful of normal draws: the honest probe's chance over the bound
    is then not small (2026-11-01: min_blocks 20 — the three shots' layers have 57–365 at 100 %, 40–850 at 25 %)."""
    k, need = sr.grain(1.0)[0], sr.P["direct_light_interior"]["min_blocks"]
    side = int(np.ceil(np.sqrt(need))) * k
    d = light(M)
    few = np.zeros((M, M), np.float32)
    few[0:k * 2 + 2, 0:k * 2 + 2] = 1.0                                # 4 blocks
    assert sr.direct_mismatch(few, d, d * 1.5) is None
    enough = np.zeros((side + 8, side + 8), np.float32)
    enough[:] = 1.0
    dd = light(side + 8)
    assert sr.direct_mismatch(enough, dd, noisy(dd, 0.009, 2)) is not None


def test_skin_without_an_interior_block_is_not_measured_and_not_refused():
    skin = np.zeros((N, N), np.float32)
    skin[20:23, :] = 1.0                                               # a 3 px strip: no interior once 2 px are taken off
    d = light(N)
    assert sr.direct_mismatch(skin, d, d * 1.5) is None
    z = np.zeros((N, N, 3), np.float32)
    rest, bounce = sr.probe_parts(skin, z + 0.8, d, z, np.ones((N, N, 4), np.float32), z + 0.15, d * 1.5, z, np.ones((N, N, 4), np.float32))
    assert rest.shape == (N, N, 3) and bounce.shape == (N, N, 3)


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
