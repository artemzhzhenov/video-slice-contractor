"""Linear model of the face distance (contractor, burst 3). Face mask and RMS exactly as the owner's
slice/measurements/face_shape_distance.py; the basis = one build per MPFB target at weight W (basis/<target>.npz)."""
import json, glob, os, itertools
import numpy as np
C = os.path.dirname(os.path.abspath(__file__)); W = 0.4
def load(name): return np.load(f"{C}/basis/{name}.npz")
d0 = load("real_v041"); v0, n0, eye_y = d0["v"], d0["n"], float(d0["eye_y"])
chin = v0[:, 1].min()
MASK = (n0[:, 2] > 0.3) & (v0[:, 1] > chin + 0.005) & (v0[:, 1] < eye_y + 0.035) & (v0[:, 2] > np.percentile(v0[:, 2], 40))
FW0, IO0 = float(d0["fw"]) * 1000, float(d0["io"]) * 1000
BASIS = {}
for f in sorted(glob.glob(f"{C}/basis/*.npz")):
    k = os.path.basename(f)[:-4]
    if k.startswith("real_") or k == "base": continue
    z = np.load(f); BASIS[k] = ((z["v"] - v0) / W, (float(z["fw"]) * 1000 - FW0) / W, (float(z["io"]) * 1000 - IO0) / W)
def rms(a, b):
    d = (b - a)[MASK]; d = d - d.mean(0); return float(np.sqrt((np.linalg.norm(d, axis=1) ** 2).mean())) * 1e3
def face(weights):
    """weights: {target: weight} → (n×3 displacement from the default head, face width mm, interocular mm)"""
    D = np.zeros_like(v0); fw, io = FW0, IO0
    for t, w in weights.items():
        if abs(w) < 1e-9: continue
        dv, dfw, dio = BASIS[t]; D = D + w * dv; fw += w * dfw; io += w * dio
    return D, fw, io
def real(name):
    z = load(name); return z["v"] - v0, float(z["fw"]) * 1000, float(z["io"]) * 1000
