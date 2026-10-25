"""Pick each child's sculpt seed (Q57): seeds 1000*N + j, j = 0, 1, ...; the first seed whose site set differs from
every earlier child's and keeps every pair with this child >= 2.3 mm by the model (later children counted with their
targets only until picked); each site on at most two children. Final check over all 45 pairs."""
import sys, json, itertools, numpy as np
sys.path.insert(0, "/home/claude/calib"); import model as M, sculpt_bumps as SB
D = dict(np.load("bump_data.npz"))
plan = json.load(open("/home/claude/out/scripts/burst3/subjects_plan.json"))
rows = {s["subject"]: s for s in plan["subjects"]}
F = {"default": np.zeros_like(M.v0), "subject_01": M.real("real_s01")[0], "subject_02": M.real("real_s02")[0]}
NEW = [f"subject_0{i}" for i in range(3, 10)]
for n in NEW: F[n] = M.face(rows[n]["feature_targets"])[0]
used, picks = [], {}
for k, n in enumerate(NEW):
    base = M.face(rows[n]["feature_targets"])[0]
    for j in range(200):
        seed = 1000 * (k + 3) + j; b, sites = SB.bumps_from_seed(seed, D)
        if sorted(sites) in used: continue
        if any(sum(s in u for u in used) >= 2 for s in sites): continue  # each site on at most two children
        Fn = base + SB.field(b, D)
        worst = min(M.rms(Fn, F[o]) for o in F if o != n)
        if worst >= 2.3:
            F[n] = Fn; used.append(sorted(sites)); picks[n] = {"seed": seed, "bumps": b, "sites": sites, "worst": worst}; break
    print(n, "seed", picks[n]["seed"], picks[n]["sites"], "amps mm", [round(float(np.linalg.norm(x["offset"])) * 1e3, 2) for x in picks[n]["bumps"]], "worst %.3f" % picks[n]["worst"])
allw = min(M.rms(F[a], F[b]) for a, b in itertools.combinations(F, 2) if a in NEW or b in NEW)
print("final: worst pair with a planned child %.3f mm (model)" % allw)
json.dump(picks, open("bump_picks.json", "w"), indent=1)
