"""Validate one shot's export directory outside Blender (repo venv, jsonschema):

    .venv/bin/python slice/check_exports.py <pkg>/shots/SHOT_001/exports

Load-bearing checks only — each one can fail on a real defect:
- files present exactly as conventions.exports.files; manifest hashes match the disk;
- no NaN / Infinity token anywhere in the JSON files;
- performance_track.json validates against schemas/performance_track.json; its socket rows equal
  socket.json's centre samples; channel set equals channel_map; values inside output ranges;
- camera / socket / joints cover exactly the shot range with the declared offsets; measured
  scale within 1e-6 of 1 (the exporter records the measured value, not a literal); rotations
  proper; quaternion w >= 0;
- frame-to-frame continuity of the socket and camera centre samples (position step < 0.05 m,
  quaternion dot > 0.99 — a hemisphere flip or a jump fails);
- sub-frame samples are distinct on the majority of frames (a copied centre sample fails);
- intrinsics_constant flag agrees with the per-frame intrinsics;
- joints: every spine bone and both shoulders in every sample, proper rotations;
- socket boundary rings: equal count, rest gap below 5 mm, per-frame rings present;
- lighting: at least one light or an HDRI, unit directions; proxies.abc and proxies_rest.obj
  non-empty; abc_to_socket matrix present; default_head_rest.obj non-empty, socket-local, counts
  equal to the manifest's; camera px_by_profile present for every render profile;
- default_head_deformed.npy: float32 of shape [frames, offsets, C_HEAD vertices, 3] as the
  manifest declares, finite, its C_HEAD objects the first objects of the rest OBJ, and its
  rest-frame centre sample equal to default_head_rest.obj within the rigid tolerance (same
  vertex order, same frame).
Exit 0 on success; exit 1 with the list of failures."""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_fixtures import load_schemas  # noqa: E402
from slice import socketspace as ss  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
SMAP = json.loads((ROOT / "slice" / "state_map.json").read_text())
CONTINUITY_POS_M = 0.05
CONTINUITY_QDOT = 0.99
REST_GAP_M = 0.005


def qdot(a, b):
    return abs(sum(x * y for x, y in zip(a, b)))


def check(out_dir):
    out = Path(out_dir)
    fails = []
    ok = lambda c, m: None if c else fails.append(m)  # noqa: E731
    names = sorted(f.name for f in out.iterdir())
    ok(names == sorted(CONV["exports"]["files"]), f"files {names}")
    man = json.loads((out / "export_manifest.json").read_text())
    for name, h in man["files"].items():
        p = out / name
        ok(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == h, f"manifest hash mismatch or missing: {name}")
    ok(man.get("socket_space_root_world_matrix_4x4_blender") is not None, "manifest lacks the root matrix")
    ok(len(man.get("ocio_config_sha256", "")) == 64, "manifest: ocio_config_sha256 missing — the export ran without a verified OCIO config")
    for name in names:
        if name.endswith(".json"):
            ok(not re.search(r"\b(NaN|Infinity)\b", (out / name).read_text()), f"{name}: non-finite token")
    shot = man["shot_id"]
    fr = CONV["shots"][shot]["frame_range"]
    frames = list(range(fr["start"], fr["end"] + 1))
    offsets = CONV["exports"]["sub_frame_offsets_frames"]

    def check_samples(name, rec, mat_key):
        ok([f["frame"] for f in rec["frames"]] == frames, f"{name}: frame list is not the shot range")
        distinct = 0
        prev = None
        for f in rec["frames"]:
            ok([s["offset"] for s in f["samples"]] == offsets, f"{name} f{f['frame']}: offsets")
            for s in f["samples"]:
                q = s["quaternion"]
                ok(abs(math.sqrt(sum(v * v for v in q)) - 1) < 1e-6 and q[3] >= 0, f"{name} f{f['frame']}: quaternion {q}")
                ok(abs(s["scale"] - 1.0) < 1e-6, f"{name} f{f['frame']}: measured scale {s['scale']}")
                ok(abs(ss.det3([r[:3] for r in s[mat_key][:3]]) - 1) < 1e-6, f"{name} f{f['frame']}: det != +1")
            if len({json.dumps(s["position_m"]) + json.dumps(s["quaternion"]) for s in f["samples"]}) == len(offsets):
                distinct += 1
            c = next(s for s in f["samples"] if s["offset"] == 0.0)
            if prev is not None:
                ok(math.dist(prev["position_m"], c["position_m"]) < CONTINUITY_POS_M, f"{name} f{f['frame']}: position jump")
                ok(qdot(prev["quaternion"], c["quaternion"]) > CONTINUITY_QDOT, f"{name} f{f['frame']}: rotation jump or hemisphere flip")
            prev = c
        # A held pose legitimately yields identical samples, so this is a majority test, not an
        # all-frames test: it catches "centre sample copied three times", which affects every frame.
        ok(distinct > len(frames) / 2, f"{name}: sub-frame samples identical on {len(frames) - distinct}/{len(frames)} frames — copied centre samples?")

    cam = json.loads((out / "camera.json").read_text())
    check_samples("camera.json", cam, "extrinsic_matrix_4x4")
    intr = [json.dumps(f["intrinsics"], sort_keys=True) for f in cam["frames"]]
    ok(cam["intrinsics_constant"] == (len(set(intr)) == 1), "camera.json: intrinsics_constant flag disagrees with the per-frame intrinsics")
    ok(all(isinstance(f["intrinsics"]["focal_length_px"][0], float) and f["intrinsics"]["focal_length_px"][0] > 0 for f in cam["frames"]), "camera.json: focal_length_px")
    for f in cam["frames"]:
        pbp = f["intrinsics"].get("px_by_profile", {})
        ok(set(pbp) == set(CONV["render_profiles"]), f"camera.json f{f['frame']}: px_by_profile profiles {sorted(pbp)}")
        for prof, px in pbp.items():
            ok(px["resolution_px"] == CONV["render_profiles"][prof]["resolution"] and px["focal_length_px"][0] > 0 and len(px["principal_point_px"]) == 2, f"camera.json f{f['frame']}: px_by_profile[{prof}]")
    sock = json.loads((out / "socket.json").read_text())
    check_samples("socket.json", sock, "matrix_4x4")
    joints = json.loads((out / "joints.json").read_text())
    ok([f["frame"] for f in joints["frames"]] == frames, "joints.json: frame list")
    spine_n = len(CONV["scene_naming"]["bones"]["spine"])
    for f in joints["frames"]:
        ok([s["offset"] for s in f["samples"]] == offsets, f"joints f{f['frame']}: offsets")
        for s in f["samples"]:
            ok(len(s["spine"]) == spine_n and s["shoulder_l"] and s["shoulder_r"], f"joints f{f['frame']}: incomplete")
            for e in s["spine"] + [s["shoulder_l"], s["shoulder_r"]]:
                if e:
                    ok(abs(ss.det3([r[:3] for r in e["matrix_4x4"][:3]]) - 1) < 1e-6 and abs(e["scale"] - 1) < 1e-6, f"joints f{f['frame']} {e['bone']}: not a proper unit transform")
    sb = json.loads((out / "socket_boundary.json").read_text())
    ok(sb["count"] == len(sb["head_ring_rest"]) == len(sb["body_ring_rest"]) and sb["count"] >= 8, "socket_boundary: ring counts")
    ok(sb["rest_gap_m"]["max"] < REST_GAP_M, f"socket_boundary: rest gap {sb['rest_gap_m']['max']:.4f} m ≥ {REST_GAP_M}")
    ok([r["frame"] for r in sb["body_ring_per_frame"]] == frames and all(len(r["points_m"]) == sb["count"] for r in sb["body_ring_per_frame"]), "socket_boundary: per-frame rings")
    env = sb["envelope_socket_local"]
    ok(all(env["max_m"][i] > env["min_m"][i] for i in range(3)), "socket_boundary: envelope degenerate")
    light = json.loads((out / "lighting_ref.json").read_text())
    ok(light["lights"] or light["hdri"] != "NONE", "lighting_ref: empty")
    for L in light["lights"]:
        ok(abs(math.sqrt(sum(v * v for v in L["direction_socket_space"])) - 1) < 1e-6, f"light {L['name']}: direction not unit")
    ok((out / "proxies.abc").stat().st_size > 0 and (out / "proxies_rest.obj").stat().st_size > 0, "proxies files empty")
    head_obj = (out / "default_head_rest.obj").read_text().splitlines()
    n_v, n_f = sum(l.startswith("v ") for l in head_obj), sum(l.startswith("f ") for l in head_obj)
    ok(n_v >= 4 and n_f >= 4, f"default_head_rest.obj: {n_v} vertices, {n_f} faces")
    ok(man.get("default_head_rest", {}).get("vertices") == n_v and man["default_head_rest"].get("faces") == n_f, "manifest default_head_rest counts differ from the file")
    # Same frame as the envelope (socket-local): every vertex must lie inside the exported
    # envelope, which was measured from the same head — a root or socket term left in the OBJ
    # moves it out of its own bounding box.
    vs = [[float(t) for t in l.split()[1:4]] for l in head_obj if l.startswith("v ")]
    env_lo, env_hi = sb["envelope_socket_local"]["min_m"], sb["envelope_socket_local"]["max_m"]
    ok(vs and all(env_lo[i] - 1e-6 <= v[i] <= env_hi[i] + 1e-6 for v in vs for i in range(3)), "default_head_rest.obj: vertices outside the exported socket-local envelope — the OBJ is not in the socket's local frame")
    ok(vs and all(abs(min(v[i] for v in vs) - env_lo[i]) < 1e-5 and abs(max(v[i] for v in vs) - env_hi[i]) < 1e-5 for i in range(3)), "default_head_rest.obj: bounding box differs from the exported envelope")
    dh = man.get("default_head_deformed")
    ok(dh is not None, "manifest lacks default_head_deformed")
    if dh is not None and (out / dh["file"]).exists():
        import numpy as np
        arr = np.load(out / dh["file"], allow_pickle=False)
        rest_objs = man["default_head_rest"]["objects"]
        n_head = sum(o["vertices"] for o in dh["objects"])
        ok(arr.dtype == np.dtype("<f4"), f"default_head_deformed: dtype {arr.dtype}")
        ok(list(arr.shape) == dh["shape"] == [len(frames), len(offsets), n_head, 3], f"default_head_deformed: shape {arr.shape} vs manifest {dh['shape']} / {len(frames)} frames × {len(offsets)} offsets × {n_head} vertices")
        ok([(o["object"], o["vertices"]) for o in rest_objs[:len(dh["objects"])]] == [(o["object"], o["vertices"]) for o in dh["objects"]]
           and all(o["collection"] == "C_HEAD" for o in rest_objs[:len(dh["objects"])])
           and sorted(dh["rigid_objects"] + [o["object"] for o in dh["objects"]]) == sorted(o["object"] for o in rest_objs),
           "default_head_deformed: objects are not the C_HEAD prefix of default_head_rest.obj plus the rigid rest")
        ok(bool(np.isfinite(arr).all()), "default_head_deformed: non-finite vertex")
        if arr.shape[:3] == (len(frames), len(offsets), n_head) and len(vs) >= n_head:
            dev = float(np.abs(arr[0, offsets.index(0.0)].astype(np.float64) - np.asarray(vs[:n_head])).max())
            ok(dev <= CONV["exports"]["default_head_deformed"]["rigid_tolerance_m"], f"default_head_deformed: rest-frame centre sample differs from default_head_rest.obj by {dev:.2e} m — vertex order or frame differ")
    ok((out / "proxies.abc.meta.json").exists() and len(json.loads((out / "proxies.abc.meta.json").read_text()).get("proxies_geometry_sha256", "")) == 64, "proxies meta: proxies_geometry_sha256 missing")
    meta = json.loads((out / "proxies.abc.meta.json").read_text())
    ok(len(meta.get("abc_to_socket_matrix_4x4", [])) == 4, "proxies meta: abc_to_socket matrix missing")
    track = json.loads((out / "performance_track.json").read_text())
    errors = list(load_schemas(ROOT / "schemas")["performance_track"].iter_errors(track))
    ok(not errors, "performance_track.json: " + "; ".join(e.message[:120] for e in errors[:5]))
    ok([f["frame"] for f in track["frames"]] == frames, "performance_track: frame list")
    ranges = {c["channel"]: c["output_range"] for c in CMAP["channels"]}
    centre = {f["frame"]: next(s for s in f["samples"] if s["offset"] == 0.0) for f in sock["frames"]}
    for f in track["frames"]:
        ok(set(f["channels"]) == set(ranges), f"track f{f['frame']}: channel set differs from channel_map")
        for k, v in f["channels"].items():
            if k in ranges:
                lo, hi = ranges[k]
                ok(lo - 1e-9 <= v <= hi + 1e-9, f"track f{f['frame']}: {k}={v} outside {ranges[k]}")
        c = centre.get(f["frame"])
        ok(c is not None and f["socket"]["position_m"] == c["position_m"] and f["socket"]["quaternion"] == c["quaternion"], f"track f{f['frame']}: socket row differs from socket.json centre sample")
    return fails


if __name__ == "__main__":
    fails = check(sys.argv[1])
    print(json.dumps({"checks_failed": fails}, indent=1))
    sys.exit(1 if fails else 0)
