"""The synthetic set's home advantage measured by us (docs/experiments/synthetic-reference-set.md, "Home advantage"): how
much of each child's face the MPFB targets alone reproduce. The children are built in the same parametric family as the
default head, so each one's identity has to carry a deviation outside that family; the residual of the best fit of the
child's face by the MPFB target fields is that deviation, reported per child (not a gate until a calibration exists).
Runs under Blender:

    blender -b --python-exit-code 2 -P slice/measurements/home_advantage.py -- \
        --default character_v04_1.blend --subjects subject_01_character.blend ... --basis face_basis_v2.npz \
        --json home_advantage.json

The face and its field are those of the distinctness rule (slice/measurements/face_shape_distance.py: HERO_HEAD with
every channel at 0, the socket's frame, the face fixed on the default head, the mean displacement removed). The target
fields are the contractor's basis (burst 3, Q57: one build per MPFB target at weight 0.4, per unit weight, the same face
and frame) — its face must be our face vertex for vertex (checked, or the run stops); its rows of the default head and of
01 and 02 as built on 2026-10-24 are reported against ours (the default's must be 0; 01 and 02 were rebuilt after the
basis was written, Q58–Q60, so theirs need not be). That the fields are in our frame is shown by the fit itself: a
child's field computed here, in our frame, fits to a few hundredths of a mm only if they are. The fit: the child's
field by the 96 target fields, weights
within +-1 (the build's range; projected gradient to the optimum, its KKT residual reported) and without bounds; the
residual's RMS over the face vertices, in mm, beside the face's own distance from the default head.

Controls (the metric's own): a field made of the targets with random weights in +-1 — residual ~0; a smooth local bump
of the sculpt's kind (Gaussian, 2 mm forward, sigma 6 mm) at random places on the face — the fit must leave most of it."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def field(v, v0, face):
    d = v[face] - v0[face]
    d -= d.mean(0)
    return d.ravel()


def rms_mm(f, nm):
    return float(np.sqrt((f ** 2).sum() / nm)) * 1e3


def fit_bounded(B, f, lo=-1.0, hi=1.0, iters=20000):
    """min |w B - f|^2 with lo <= w <= hi: accelerated projected gradient (FISTA); returns w and the KKT residual."""
    G = B @ B.T
    c = B @ f
    L = float(np.linalg.eigvalsh(G).max())
    w = np.clip(np.linalg.lstsq(B.T, f, rcond=None)[0], lo, hi)
    y, t = w.copy(), 1.0
    for _ in range(iters):
        w_new = np.clip(y - (G @ y - c) / L, lo, hi)
        t_new = (1 + np.sqrt(1 + 4 * t * t)) / 2
        y = w_new + (t - 1) / t_new * (w_new - w)
        w, t = w_new, t_new
    g = G @ w - c                                           # the gradient; zero where free, signed at a bound
    kkt = np.where(w <= lo + 1e-9, np.minimum(g, 0), np.where(w >= hi - 1e-9, np.maximum(g, 0), g))
    return w, float(np.abs(kkt).max() / max(np.abs(c).max(), 1e-30))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--default", required=True)
    ap.add_argument("--subjects", nargs="+", required=True)
    ap.add_argument("--basis", required=True)
    ap.add_argument("--json", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(HERE))
    import face_shape_distance as fsd              # Blender's: the heads are read with bpy (the fit below is plain numpy)
    z = np.load(a.basis, allow_pickle=False)
    keys = [str(k) for k in z["keys"]]
    targets = [i for i, k in enumerate(keys) if not k.startswith("trial")]
    B = z["B"][targets]
    v0, n0, eye_y = fsd.head(a.default)
    face = fsd.face_mask(v0, n0, eye_y)
    nm = int(face.sum())
    checks = {"face_vertices": nm, "basis_face_vertices": int(z["nm"]),
              "basis_face_equals_ours": bool(z["mask"].shape == face.shape and (z["mask"] == face).all()),
              "basis_rows": len(keys), "target_rows": len(targets), "other_rows": [k for k in keys if k.startswith("trial")]}
    if not checks["basis_face_equals_ours"]:
        raise SystemExit(f"HOME_ADVANTAGE_FAIL the basis's face is not ours: {checks}")
    fields = {}
    for p in a.subjects:
        v, _, _ = fsd.head(p)
        fields[Path(p).stem.replace("_character", "")] = field(v, v0, face)
    fixed = {}
    for i, n in enumerate(z["fixed_names"]):
        n = str(n)
        ours = np.zeros(3 * nm) if n == "default" else fields.get(n)
        if ours is not None:
            fixed[n] = round(float(np.abs(z["fixed"][i] - ours).max()) * 1e3, 5)
    checks["fixed_fields_max_abs_mm"] = fixed
    rows = []
    for n, f in fields.items():
        wb, kkt = fit_bounded(B, f)
        wu = np.linalg.lstsq(B.T, f, rcond=None)[0]
        rows.append({"subject": n, "face_rms_mm": round(rms_mm(f, nm), 3),
                     "residual_bounded_mm": round(rms_mm(f - wb @ B, nm), 3),
                     "residual_unbounded_mm": round(rms_mm(f - wu @ B, nm), 3),
                     "residual_share_of_face": round(rms_mm(f - wb @ B, nm) / rms_mm(f, nm), 3),
                     "weights_at_bound": int((np.abs(wb) >= 1 - 1e-9).sum()), "kkt_rel": kkt})
    rng = np.random.default_rng(20261030)
    pos = []
    for _ in range(5):
        f = rng.uniform(-1, 1, len(targets)) @ B
        wb, _ = fit_bounded(B, f)
        pos.append(round(rms_mm(f - wb @ B, nm) / rms_mm(f, nm), 4))
    fv = v0[face]
    neg = []
    for _ in range(8):
        c = fv[rng.integers(len(fv))]
        g = 0.002 * np.exp(-((fv - c) ** 2).sum(1) / (2 * 0.006 ** 2))
        d = np.zeros_like(fv)
        d[:, 2] = g
        d -= d.mean(0)
        f = d.ravel()
        wb, _ = fit_bounded(B, f)
        neg.append(round(rms_mm(f - wb @ B, nm) / rms_mm(f, nm), 3))
    rec = {"what": __doc__.split("\n\n")[0].replace("\n", " "), "definition": __doc__.split("\n\n")[2].replace("\n", " "),
           "default": a.default, "basis": a.basis, "checks": checks, "children": rows,
           "controls": {"targets_with_random_weights_residual_share": pos,
                        "local_bump_2mm_sigma6mm_residual_share": neg}}
    Path(a.json).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    print(f"HOME_ADVANTAGE checks {json.dumps(checks)}")
    for r in rows:
        print(f"HOME_ADVANTAGE {r['subject']:<11s} face {r['face_rms_mm']:.3f} mm  residual {r['residual_bounded_mm']:.3f} mm "
              f"(unbounded {r['residual_unbounded_mm']:.3f}, share {r['residual_share_of_face']:.3f}, kkt {r['kkt_rel']:.1e})")
    print(f"HOME_ADVANTAGE controls: targets {pos}; local bumps {neg}")
    print("HOME_ADVANTAGE_DONE")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
