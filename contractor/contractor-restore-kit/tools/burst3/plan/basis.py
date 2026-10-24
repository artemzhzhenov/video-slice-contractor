"""Basis runner: one build per probe (a subject json with only the listed targets / sculpt bumps, short hair, no bangs,
no glasses), then face_vec.py. Resumable (basis/<key>.npz present → skipped); stops before the time budget."""
import json, os, subprocess, sys, time
B3 = "/home/claude/b3"; C = "/home/claude/calib"
ENV = dict(os.environ, PATH="/home/claude/bin:" + os.environ["PATH"],
           OCIO="/home/claude/vsc/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio")
base = json.load(open(f"{B3}/subject_02.json"))
base.update(subject="basis", seed=900, glasses=False, sculpt=[])
base["hair"] = {"class": "short_straight", "color_linear": [0.03, 0.02, 0.016], "bangs": False}
FOLDER = {"head": "head", "cheek": "cheek", "eye": "eyes", "nose": "nose", "chin": "chin", "forehead": "forehead", "mouth": "mouth", "eyebrows": "eyebrows"}
def targets_of(spec):
    out = []
    for name, w in spec:
        folder = FOLDER[name.split("-")[0]]
        if name.startswith(("cheek-", "eye-")):
            out += [[folder, "l-" + name, w], [folder, "r-" + name, w]]
        else:
            out.append([folder, name, w])
    return out
def build(key, spec, sculpt):
    j, bl, nz = f"{C}/basis/{key}.json", f"{C}/basis/{key}.blend", f"{C}/basis/{key}.npz"
    json.dump(dict(base, targets=targets_of(spec), sculpt=sculpt), open(j, "w"))
    r = subprocess.run(["blender", "-b", f"{B3}/template_SHOT_001.blend", "--python-exit-code", "2", "-P", f"{B3}/build_character.py",
                        "--", "--out", bl, "--subject", j], env=ENV, capture_output=True, text=True)
    if "BUILD_OK" not in r.stdout:
        return (r.stdout + r.stderr)[-400:]
    r = subprocess.run(["blender", "-b", bl, "--python-exit-code", "2", "-P", f"{C}/face_vec.py", "--", "--out", nz], env=ENV, capture_output=True, text=True)
    if not os.path.exists(nz):
        return (r.stdout + r.stderr)[-400:]
    if not os.environ.get("KEEP_BLEND"): os.remove(bl)
    return None
if __name__ == "__main__":
    os.makedirs(f"{C}/basis", exist_ok=True)
    probes = json.load(open(sys.argv[1])); budget = float(sys.argv[2]); t0 = time.time(); left = 0
    for p in probes:
        if os.path.exists(f"{C}/basis/{p['key']}.npz"): continue
        if time.time() - t0 > budget: left += 1; continue
        err = build(p["key"], p.get("spec", []), p.get("sculpt", []))
        print(p["key"], "ERR " + err if err else "ok", flush=True)
    print("LEFT", left)
