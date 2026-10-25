"""check_plan.py — the plan of nine against the owner's distinctness rule (Q56), by the contractor's linear model.

    python3 check_plan.py [--plan ../../scripts/burst3/subjects_plan.json] [--basis plan/face_basis_v2.npz] [--margin 0.3]

Rule (owner, 2026-10-24): every child differs from the default head and from every other child by an RMS of the
per-vertex face displacement >= 2.0 mm (slice/measurements/face_shape_distance.py: same face mask, same topology,
translation removed). This script predicts the 45 distances without building anything:
  face(child) = default head + sum over its feature_targets of weight × the target's displacement field.
The fields come from one build per MPFB target at weight 0.4 (tools/burst3/plan/face_basis_v2.npz, built by
basis.py + face_vec.py with build_character.py on the shot template; MakeHuman targets are linear in the weight).
v2 (Q57): + the row's sculpt bumps as their exact field (sculpt_bumps.field — build_character.py step 8b on the
default head's build positions, ring ramp included); bumps alone vs a build: 0.0000 mm, targets + bumps: 0.006 mm.
subject_01 and subject_02 are taken as built (they are accepted), not modelled.
Model vs the owner's script on trial builds: targets only (Q56) max |diff| 0.022 mm; targets + bumps (Q57) worst pair 2.325 model / 2.311 script.
Pass: every pair involving a child of the plan (03-09) >= 2.0 + margin; pairs among default / 01 / 02 are reported
against 2.0 (default–subject_02 is 2.000 as built — the owner's Q56 note). Exit 0 = PLAN_OK, 1 = PLAN_FAIL."""
import argparse, itertools, json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--plan", default=str(HERE.parents[1] / "scripts" / "burst3" / "subjects_plan.json"))
ap.add_argument("--basis", default=str(HERE / "plan" / "face_basis_v2.npz"))
ap.add_argument("--margin", type=float, default=0.3)
a = ap.parse_args()
z = np.load(a.basis)
sys.path.insert(0, str(HERE)); import sculpt_bumps as SB
BD = {"co": z["bump_co"], "ring": z["bump_ring"], "M": z["bump_M"], "eyeL": z["bump_eyeL"]}; MASK = z["mask"]
keys = [str(k) for k in z["keys"]]; B = z["B"]; nm = int(z["nm"])
idx = {k: i for i, k in enumerate(keys)}
F = {str(n): z["fixed"][i] for i, n in enumerate(z["fixed_names"])}
plan = json.load(open(a.plan)); rows = {}
for s in plan["subjects"]:
    n = s["subject"]
    if n in F: continue
    w = np.zeros(len(keys))
    for t, v in s["feature_targets"].items():
        if t not in idx: sys.exit(f"PLAN_FAIL {n}: target {t} has no basis field")
        w[idx[t]] = v
    Fn = w @ B
    if s.get("sculpt"):
        f = SB.field(s["sculpt"], BD)[MASK]; f = f - f.mean(0); Fn = Fn + f.ravel()
    F[n] = Fn
    rows[n] = {"bumps": len(s.get("sculpt", [])), "fw": float(z["fw0"] + w @ z["dfw"]), "io": float(z["io0"] + w @ z["dio"]), "max_w": float(w.max()), "n": int((w > 0).sum())}
rule = 2.0; need = rule + a.margin; fails = []
print(f"{'pair':<26s} {'RMS mm':>7s}  need")
for x, y in itertools.combinations(F, 2):
    d = float(np.sqrt(((F[x] - F[y]) ** 2).sum() / nm) * 1e3)
    planned = x in rows or y in rows; lim = need if planned else rule
    ok = d >= lim - 1e-9
    if not ok: fails.append(f"{x}–{y} {d:.3f}")
    print(f"{x + '–' + y:<26s} {d:7.3f}  {lim:.1f} {'ok' if ok else 'FAIL'}")
for n, r in rows.items():
    print(f"{n}: {r['n']} targets + {r['bumps']} bumps, max weight {r['max_w']:.2f}, model face width {r['fw']:.1f} mm, interocular {r['io']:.1f} mm")
print(("PLAN_OK" if not fails else "PLAN_FAIL") + f" {len(F)} heads, {len(F) * (len(F) - 1) // 2} pairs; planned children >= {need:.1f} mm (model), fixed pairs >= {rule:.1f}; failing: {fails or 'none'}")
sys.exit(1 if fails else 0)
