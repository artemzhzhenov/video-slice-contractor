"""The master's supported skin-tone range, measured — ADR-0002 D4, its amendment of 2026-09-29 (C4) as amended on
2026-10-31 (the re-tint between the master and its skin probe). Plain Python orchestrating Blender:

    .venv/bin/python slice/check_skin_tone.py --blend <shot.blend> --shot SHOT_002 --renders <check_asset out>/renders \
        --out <dir>

Per shot, on the video frames the conformant run rendered (its bundle manifests), at the gate's scale and samples:
- the master rendered again with its skin passes;
- its skin probe — the two skin layers with every hero skin material at skin_tone.probe.tone (render_passes.py
  --skin-probe on a copy made by slice/skin_probe.py set-tone), derived into the gate's own SKIN_PROBE_BUNDLE
  (slice/skin_probe.py derive);
- the truths: the shot with every hero skin material at each gate tone (conventions.json → skin_tone.gate.tones),
  nothing else changed.

The master is re-tinted to each tone exactly as an order is (slice/skin_retint.py) and compared with the truth on each
layer's visible skin. Visible skin: the layer's own skin matte > 0.5, the layer opaque; for the back, where neither the
front plate nor the head's holdout covers it — under the head the body plate shows the open neck, which no head lets
through. The comparison runs over 4×4 blocks holding at least `block_min_skin_px` of that skin, each block's mean taken
over those pixels alone, so a thin strip of neck is measured. Per frame, tone and layer with `min_skin_blocks` blocks: the
mean, the 99th percentile and the maximum of the largest channel difference relative to the truth's mean. The
first-order re-tint (2026-09-29, C3) is recorded beside them, not judged.

Verdicts:
- PASS when every case's mean is within `relative_error_max`, its 99th percentile within `relative_error_p99_max`, and no
  re-tint is not within the mean bound (the negative control on every measured case).
- NOT_JUDGED while the owner has not set `relative_error_p99_max`: the measurements are recorded, the bundles not marked,
  exit 2; `--recompare` judges them again once it is set.
- VACUOUS when no case has the blocks.
- FAIL otherwise.

On PASS / VACUOUS the gate is written into the run's bundle manifests as `skin_tone` (method `probe`, the supported range
— the per-channel box between the passing tones), which composite_order.py requires before it re-tints. The record is
<out>/check_skin_tone.json.

The truth and probe renders are a MASTER_COST line per master version, never per order. --frames measures the named
frames of the bundle only (slice/frame_subset.py; the master's full-range render, owner 2026-10-30: option (c)), and the
record says how many of the bundle's frames they are. --profiles names the bundles the record goes into (default video
and still; the full-range render replaces the video bundle alone)."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice.frame_subset import select  # noqa: E402
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
G = CONV["skin_tone"]["gate"]
PROBE = CONV["skin_tone"]["probe"]
OCIO = ROOT / "benchmarks" / "bakeoff" / "01J7B000000000000000BAKEXP" / "slice" / "ocio" / "studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio"


class SkinToneError(RuntimeError):
    pass


def compare(argv):
    """Runs under Blender's Python: the re-tint against the truths, per frame, tone and layer."""
    sys.path.insert(0, str(ROOT))
    import numpy as np
    from slice import skin_retint as sr
    from slice.composite import read_parts, skin_diffuse, layer_skin, retint
    out, master_albedo = Path(argv[0]), np.array(json.loads(argv[1]), np.float32)
    material = CONV["skin_tone"]["material_body"]
    mdir = out / "master" / "renders" / "video"
    bm = json.loads(next(mdir.glob("bundle_manifest.*.json")).read_text())

    def frames(d, bundle):
        b = json.loads(next((d / "renders" / "video").glob("bundle_manifest.*.json")).read_text())
        return {r["frame"]: d / "renders" / "video" / bundle / r["file"] for r in b["bundles"][bundle]["frames"]}
    comp, skin, probe = frames(out / "master", "COMPOSITE_BUNDLE"), frames(out / "master", "SKIN_BUNDLE"), frames(out / "master", PROBE["bundle"])
    probe_albedo = bm["bundles"][PROBE["bundle"]]["probe"]["albedo"]
    res = {"frames": {}}
    for frame in sorted(comp):
        mp, sp, pp = read_parts(comp[frame]), read_parts(skin[frame]), read_parts(probe[frame])
        front_a = mp["FOREGROUND_PLATE"][0][..., 3]
        head_a = mp["HEAD_HOLDOUT"][0][..., 0]
        res["frames"][frame] = {}
        for tone, rgb in G["tones"].items():
            tp = read_parts(frames(out / tone, "COMPOSITE_BUNDLE")[frame])
            gain, weight = sr.gain_and_weight(rgb, master_albedo, probe_albedo)
            res["frames"][frame][tone] = {}
            for layer, side, part in (("BODY", "BACK", "BODY_BEAUTY"), ("FRONT", "FRONT", "FOREGROUND_PLATE")):
                m = layer_skin(sp, layer, material)
                if m is None:
                    continue
                src = mp[part][0].astype(np.float32)
                # the back is seen where neither the front plate nor a head covers it: under the head the body plate
                # shows the open neck, which no head lets through (the seam's SEAM_EXTEND replaces its edge)
                seen = ((front_a < 0.01) & (head_a < 0.01)) if layer == "BODY" else np.ones_like(m, bool)
                mask = (m > 0.5) & (src[..., 3] > 0.99) & seen
                sd = skin_diffuse(sp, layer, material)[0]
                got = sr.retint(src, sd, gain, weight, pp[f"REST_{side}"][0], pp[f"BOUNCE_{side}"][0])
                truth = tp[part][0].astype(np.float32)
                r = sr.measure(got, truth, src, mask, G["block_px"], G["block_min_skin_px"])
                if r is None or r["blocks"] < G["min_skin_blocks"]:
                    continue
                first = sr.measure(retint(src, sd, gain), truth, src, mask, G["block_px"], G["block_min_skin_px"])
                r["first_order_relative_error"] = first["relative_error"]
                r["first_order_relative_error_p99"] = first["relative_error_p99"]
                res["frames"][frame][tone][part] = r
    (out / "compare.json").write_text(json.dumps(res, indent=1) + "\n")
    print("SKIN_TONE_COMPARED")


def run(cmd, env, log):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env, timeout=12 * 3600)
    log.write_text(r.stdout[-20000:] + "\n--- stderr\n" + r.stderr[-20000:])
    if r.returncode != 0:
        raise SkinToneError(f"{Path(str(cmd[4] if len(cmd) > 4 else cmd[0])).name} failed (rc {r.returncode}) — {log}")
    return r


def verdict(res, lim=None, lim99=None):
    """(status, over, blind): over lists (frame, tone, layer, 'mean' | 'p99', value) past a bound; blind the cases no
    re-tint would pass (the negative control). NOT_JUDGED while the 99th percentile's bound is not set."""
    lim = G["relative_error_max"] if lim is None else lim
    lim99 = G["relative_error_p99_max"] if lim99 is None else lim99
    cases = [(f, t, l, v) for f, ts in res["frames"].items() for t, ls in ts.items() for l, v in ls.items()]
    if not cases:
        return "VACUOUS", [], []
    over = [(f, t, l, "mean", round(v["relative_error"], 4)) for f, t, l, v in cases if v["relative_error"] > lim]
    if lim99 is not None:
        over += [(f, t, l, "p99", round(v["relative_error_p99"], 4)) for f, t, l, v in cases if v["relative_error_p99"] > lim99]
    blind = [(f, t, l, round(v["no_retint_relative_error"], 4)) for f, t, l, v in cases if v["no_retint_relative_error"] <= lim]
    if lim99 is None:
        return "NOT_JUDGED", over, blind
    return ("PASS" if not over and not blind else "FAIL"), over, blind


def record_in_bundles(renders, profiles, record, out):
    """The gate's verdict into each named profile's bundle manifest — what composite_order.py reads before it re-tints.
    Every named bundle must exist; nothing is written unless all do."""
    paths = [Path(renders) / prof / f"bundle_manifest.{prof}.json" for prof in profiles]
    missing = [str(p) for p in paths if not p.exists()]
    if missing or not paths:
        raise SkinToneError(f"no bundle manifest to record the gate in: {missing or profiles}")
    keys = ("status", "method", "master_albedo", "probe_albedo", "supported_range", "relative_error_max", "relative_error_p99_max", "tones",
            "scale_percent", "frames_gated", "frames_in_bundle", "coverage")
    for bp in paths:
        bm = json.loads(bp.read_text())
        bm["skin_tone"] = {k: record[k] for k in keys} | {"record": str(Path(out) / "check_skin_tone.json")}
        bp.write_text(json.dumps(bm, indent=1) + "\n")


def main(argv):
    ap = argparse.ArgumentParser()
    for k in ("--blend", "--shot", "--renders", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--recompare", action="store_true", help="the renders in --out exist: compare and judge again only")
    ap.add_argument("--frames", default=None, help="comma list: measure these frames of the bundle only (default: every frame)")
    ap.add_argument("--profiles", default="video,still", help="the bundles the record goes into")
    a = ap.parse_args(argv)
    out, renders = Path(a.out), Path(a.renders)
    if out.exists() and any(out.iterdir()) and not a.recompare:
        raise SkinToneError(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rm = json.loads((renders / "video" / "render_manifest.video.json").read_text())
    sm = rm.get("skin_material", {})
    if sm.get("status") != "RE-TINTABLE":
        raise SkinToneError(f"the master's skin material is {sm.get('status', 'NOT RECORDED')!r} — rendered before contract v5, or a gain cannot re-tint it")
    try:
        gated, coverage = select([r["frame"] for r in rm["frames"]], a.frames)
    except ValueError as e:
        raise SkinToneError(str(e)) from None
    frames = ",".join(str(f) for f in gated)
    env = dict(os.environ, OCIO=str(OCIO), PYTHONDONTWRITEBYTECODE="1", CYCLES_METAL_DISABLE_BINARY_ARCHIVES="1")
    B = ["blender", "-b", "--python-exit-code", "2"]
    tones = {"probe": PROBE["tone"], **G["tones"]}
    for tone in ([] if a.recompare else ["master"] + list(tones)):
        d = out / tone
        d.mkdir()
        blend = d / f"{a.shot}_{tone}.blend"
        if tone == "master":
            shutil.copy2(a.blend, blend)
        else:
            run(["blender", "-b", a.blend, "--python-exit-code", "2", "-P", ROOT / "slice/skin_probe.py", "--", "set-tone",
                 "--tone", ",".join(str(v) for v in tones[tone]), "--out", blend], env, d / "set_tone.log")
        run(["blender", "-b", blend, "--python-exit-code", "2", "-P", ROOT / "slice/render_passes.py", "--", "--shot", a.shot, "--profile", "video",
             "--frames", frames, "--samples", G["samples"], "--scale", G["scale_percent"], "--out", d / "renders",
             *(["--skin-probe"] if tone == "probe" else []),
             *(["--exports", renders.parent / "exports"] if rm["settings"].get("gaze_aim", {}).get("mode") == "TARGET_POINT" else [])], env, d / "render.log")
        if tone != "probe":
            run(B + ["-P", ROOT / "slice/split_bundles.py", "--", d / "renders" / "video", "--no-plus-files"], env, d / "split.log")
    if not (out / "master" / "renders" / "video" / PROBE["bundle"]).exists():
        run(B + ["-P", ROOT / "slice/skin_probe.py", "--", "derive", out / "master" / "renders" / "video", out / "probe" / "renders" / "video"],
            env, out / "derive.log")
    run(B + ["-P", Path(__file__).resolve(), "--", "--compare", out, json.dumps(sm["base_color"])], env, out / "compare.log")
    res = json.loads((out / "compare.json").read_text())
    status, over, blind = verdict(res)
    rng = {"min": [min(t[i] for t in G["tones"].values()) for i in range(3)], "max": [max(t[i] for t in G["tones"].values()) for i in range(3)]}
    record = {"gate": "skin_tone", "shot": a.shot, "status": status, "method": "probe", "master_albedo": sm["base_color"],
              "probe_albedo": PROBE["tone"], "tones": G["tones"], "frames": frames,
              "scale_percent": G["scale_percent"], "samples": G["samples"], "relative_error_max": G["relative_error_max"],
              "relative_error_p99_max": G["relative_error_p99_max"], "block_px": G["block_px"], "block_min_skin_px": G["block_min_skin_px"],
              "min_skin_blocks": G["min_skin_blocks"], "over_the_bound": over, "negative_control_within_the_bound": blind,
              "supported_range": rng if status in ("PASS", "VACUOUS") else None, "measured": res["frames"], "rule": G["rule"], **coverage}
    (out / "check_skin_tone.json").write_text(json.dumps(record, indent=1) + "\n")
    cases = [v for ts in res["frames"].values() for ls in ts.values() for v in ls.values()]
    worst = (max(v["relative_error"] for v in cases), max(v["relative_error_p99"] for v in cases)) if cases else None
    if status == "NOT_JUDGED":
        raise SkinToneError(f"{a.shot}: measured — worst mean {worst[0]:.4f}, worst 99th percentile {worst[1]:.4f} — but relative_error_p99_max "
                            f"is not set (the owner sets it from {out / 'compare.json'}); then --recompare. Over the mean bound: {over}")
    if status == "FAIL":
        raise SkinToneError(f"{a.shot}: over the bound {over}; the negative control within it {blind}")
    record_in_bundles(renders, [x for x in a.profiles.split(",") if x], record, out)
    print(f"SKIN_TONE_{status} {a.shot}: " + (f"worst re-tint error {worst[0]:.4f} mean, {worst[1]:.4f} at the 99th percentile (bounds "
                                              f"{G['relative_error_max']}, {G['relative_error_p99_max']})" if worst else "no body skin in view")
          + f"; supported range {rng['min']}–{rng['max']} -> {out / 'check_skin_tone.json'}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        if argv and argv[0] == "--compare":
            compare(argv[1:])
        else:
            main(argv)
    except SkinToneError as e:
        print(f"SKIN_TONE_ERROR {e}", file=sys.stderr)
        sys.exit(2)
