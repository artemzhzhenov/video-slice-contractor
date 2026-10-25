"""Sculpted deviation of a synthetic child (burst 3, owner Q57): 2-3 Gaussian bumps of 1.5-3 mm outside the MPFB
targets, at named sites of the face, drawn deterministically from a seed; and the bumps' exact displacement field
on the head, as build_character.py applies it (step 8b), for the plan model. numpy only.

Field (build_character.py 8b): a head vertex at its default build position co, depth d above the SOCKET_BOUNDARY ring
(the ring vertex nearest in angle around the ring centre), moves by  w(d) * sum_b offset_b * exp(-(|co - c_b| / r_b)^2)
with w = smoothstep(min(1, d / ramp)), c_b = ring centre + centre_b; the face_shape_distance frame applies M3."""
import json
import numpy as np

SITES = {  # name: (kind, anchor, base direction (+x = character's left / -y forward / +z up), radius m)
    "cheekbone":    ("pair", "front", (0.45, -0.75, 0.35), 0.020),
    "cheek_apple":  ("pair", "front", (0.15, -0.95, 0.0), 0.020),
    "brow_ridge":   ("pair", "front", (0.0, -0.85, 0.35), 0.016),
    "temple":       ("pair", "side", (1.0, 0.0, 0.0), 0.020),
    "jaw_angle":    ("pair", "side", (0.9, 0.0, -0.4), 0.022),
    "nasal_bridge": ("mid", "front", (0.0, -1.0, 0.0), 0.012),
    "forehead":     ("mid", "front", (0.0, -1.0, 0.2), 0.026),
    "chin":         ("mid", "front", (0.0, -0.8, -0.45), 0.018),
}

def site_points(D):
    """Skin points of the sites on the default head (build coordinates), from its eyes and chin."""
    co = D["co"]; eL = D["eyeL"]; ex, ey, ez = abs(eL[0]), eL[1], eL[2]
    front = co[:, 1] < ey + 0.03
    chin_z = co[(np.abs(co[:, 0]) < 0.01) & front, 2].min()
    def on_front(x, z):
        m = (np.abs(co[:, 0] - x) < 0.004) & (np.abs(co[:, 2] - z) < 0.004)
        return co[m][np.argmin(co[m][:, 1])]
    def on_side(y, z):
        m = (np.abs(co[:, 1] - y) < 0.004) & (np.abs(co[:, 2] - z) < 0.004) & (co[:, 0] > 0)
        return co[m][np.argmax(co[m][:, 0])]
    return {"cheekbone": on_front(ex + 0.014, ez - 0.024), "cheek_apple": on_front(ex + 0.002, ez - 0.040),
            "brow_ridge": on_front(ex, ez + 0.020), "temple": on_side(ey + 0.025, ez + 0.012),
            "jaw_angle": on_side(ey + 0.035, chin_z + 0.045), "nasal_bridge": on_front(0.0, ez),
            "forehead": on_front(0.0, ez + 0.050), "chin": on_front(0.0, chin_z + 0.012)}

def bumps_from_seed(seed, D, avoid=()):
    """2-3 bumps: one pair site, or two mid sites, or a pair and a mid site; amplitude 1.5-3.0 mm, mostly raised.
    Returns (bumps in subject json form — centre relative to the ring centre, metres —, the sites used)."""
    rng = np.random.default_rng(seed); P = site_points(D); rc = D["ring"].mean(0)
    pairs = [s for s, v in SITES.items() if v[0] == "pair"]; mids = [s for s, v in SITES.items() if v[0] == "mid"]
    pattern = rng.choice(["pair", "mid_mid", "pair_mid"], p=[0.25, 0.25, 0.5])
    if pattern == "pair": sites = [str(rng.choice(pairs))]
    elif pattern == "mid_mid": sites = [str(s) for s in rng.choice(mids, 2, replace=False)]
    else: sites = [str(rng.choice(pairs)), str(rng.choice(mids))]
    out = []
    for s in sites:
        kind, _, d, r = SITES[s]; amp = float(rng.uniform(0.0015, 0.0030)); sign = 1.0 if rng.random() < 0.7 else -1.0
        r = r * float(rng.uniform(0.9, 1.15)); d = np.array(d) / np.linalg.norm(d); p = P[s]
        for mx in ((1.0, -1.0) if kind == "pair" else (1.0,)):
            c = (p - rc) * np.array([mx, 1, 1]); off = sign * amp * d * np.array([mx, 1, 1])
            out.append({"site": s + ("" if kind == "mid" else ("_l" if mx > 0 else "_r")),
                        "centre": [round(float(x), 4) for x in c], "radius": round(r, 4), "offset": [round(float(x), 5) for x in off]})
    return out, sites

def field(bumps, D, ramp=0.035):
    """Displacement of every head vertex (n x 3) in the face_shape_distance frame."""
    co = D["co"]; ring = D["ring"]; rc = ring.mean(0)
    ra = np.arctan2(ring[:, 0] - rc[0], ring[:, 1] - rc[1]); va = np.arctan2(co[:, 0] - rc[0], co[:, 1] - rc[1])
    near = np.argmin(np.abs(np.remainder(va[:, None] - ra[None, :] + np.pi, 2 * np.pi) - np.pi), axis=1)
    depth = co[:, 2] - ring[near, 2]
    is_ring = (np.linalg.norm(co[:, None, :] - ring[None, :, :], axis=2) < 1e-9).any(1)
    t = np.clip(depth / ramp, 0, 1); w = np.where((depth > 0) & ~is_ring, t * t * (3 - 2 * t), 0.0)
    s = np.zeros_like(co)
    for b in bumps:
        c = np.array(b["centre"]) + rc; off = np.array(b["offset"]); r = b["radius"]
        s += off[None, :] * np.exp(-((np.linalg.norm(co - c, axis=1) / r) ** 2))[:, None]
    return (s * w[:, None]) @ D["M"][:3, :3].T
