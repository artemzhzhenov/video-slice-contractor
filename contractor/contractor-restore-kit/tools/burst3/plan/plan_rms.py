"""Plan of subject_03..09 under the owner's rule (Q56): every pair of the nine children and the default head differs by
RMS >= RULE + MARGIN over the face (model), with moderate weights: minimise the sum of squared weights (the difference
spread over the whole face), weights in [0, CAP] (head-scale-* <= 0.2; mouth/eye position <= 0.3), face width 124-146 mm
and interocular 51-59 mm (the contractor's proposal for "no extreme faces"). Fixed: default, subject_01, subject_02 as built.
Projected gradient descent on a penalty function, several restarts; deterministic seeds."""
import sys, json, itertools
import numpy as np
sys.path.insert(0, "/home/claude/calib"); import model as M
TARGET = float(sys.argv[1]) if len(sys.argv) > 1 else 2.35; RESTARTS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
EXCLUDE = {"head-age-incr", "head-age-decr", "eyebrows-angle-up", "eyebrows-angle-down"}
KEYS = [k for k in sorted(M.BASIS) if k not in EXCLUDE]
CAP = np.array([0.15 if k.startswith(("head-scale", "mouth-trans", "eye-trans-up", "eye-trans-down", "nose-trans")) else 0.4 for k in KEYS])
nm = int(M.MASK.sum())
def cen(D): X = D[M.MASK]; return (X - X.mean(0)).ravel()
B = np.stack([cen(M.BASIS[k][0]) for k in KEYS])               # K × 3nm, centred
dFW = np.array([M.BASIS[k][1] for k in KEYS]); dIO = np.array([M.BASIS[k][2] for k in KEYS])
FIX = {"default": np.zeros(B.shape[1]), "subject_01": cen(M.real("real_s01")[0]), "subject_02": cen(M.real("real_s02")[0])}
NEW = [f"subject_0{i}" for i in range(3, 10)]
def dist(a, b): return np.sqrt(((a - b) ** 2).sum() / nm) * 1e3
def run(seed):
    rng = np.random.default_rng(seed); X = rng.uniform(0, 1, (7, len(KEYS))) * CAP * 0.5
    lr = 0.01; mu = 50.0
    for it in range(6000):
        F = X @ B; G = 2 * X                                   # gradient of sum w^2
        allF = list(FIX.values()) + [F[i] for i in range(7)]
        for i in range(7):
            for j, Fo in enumerate(allF):
                if j == 3 + i: continue
                d = dist(F[i], Fo)
                if d < TARGET:
                    # d(d)/dF = (F - Fo) * 1e6 / (nm d) ; penalty mu (T - d)^2
                    g = -2 * mu * (TARGET - d) * (F[i] - Fo) * 1e6 / (nm * max(d, 1e-6))
                    G[i] += B @ g * (1.0 if j < 3 else 1.0)
        fw = M.FW0 + X @ dFW; io = M.IO0 + X @ dIO
        for i in range(7):
            for val, lo, hi, dv in ((fw[i], 124, 146, dFW), (io[i], 51, 59, dIO)):
                if val < lo: G[i] += -2 * mu * 0.05 * (lo - val) * dv
                if val > hi: G[i] += 2 * mu * 0.05 * (val - hi) * dv
        X = np.clip(X - lr * G / max(1.0, np.abs(G).max()), 0, CAP)
        if it == 3000: lr *= 0.3
    return X
def report(X):
    F = X @ B; allF = {**FIX, **{NEW[i]: F[i] for i in range(7)}}
    pairs = {(a, b): dist(allF[a], allF[b]) for a, b in itertools.combinations(allF, 2)}
    worst_new = min(v for (a, b), v in pairs.items() if a in NEW or b in NEW)
    return pairs, worst_new, float((X ** 2).sum()), float(X.max())
best = None
for s in range(RESTARTS):
    X = run(s); X = np.where(X < 0.02, 0, np.round(X, 2)); pairs, w, ss, mx = report(X)
    print("seed", s, "worst new pair %.3f" % w, "sum w^2 %.2f" % ss, "max w %.2f" % mx, flush=True)
    if w >= TARGET - 0.02 and (best is None or ss < best[2]): best = (X, w, ss)
X = best[0] if best else X
np.save("/home/claude/calib/plan_rms_X.npy", X); json.dump(KEYS, open("/home/claude/calib/plan_rms_keys.json", "w"))
pairs, w, ss, mx = report(X)
fw = M.FW0 + X @ dFW; io = M.IO0 + X @ dIO
for i, n in enumerate(NEW):
    tw = {KEYS[k]: float(X[i, k]) for k in np.argsort(-X[i]) if X[i, k] > 0}
    print(n, "fw %.1f io %.1f" % (fw[i], io[i]), "n=%d" % len(tw), " ".join(f"{k}:{v:.2f}" for k, v in list(tw.items())[:9]), "…" if len(tw) > 9 else "")
print("worst pair with a new child %.3f; fixed pairs:" % w, {f"{a}–{b}": round(v, 3) for (a, b), v in pairs.items() if a not in NEW and b not in NEW})
