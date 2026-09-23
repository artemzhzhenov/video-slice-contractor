"""Blur fidelity — ADR-0002 §Validation criterion 8 (amendment 2026-09-22).

    blender -b --python-exit-code 2 -P slice/check_blur_fidelity.py -- \
        --renders <pkg>/shots/SHOT_001/renders/video --reference <dir with the blur-reference render> \
        --out <dir>

Since the amendment the layers are rendered sharp and the blur is applied after the head is
composited. That fixes the seam, but it replaces a rendered 3D blur with a 2D one, so the
question "does it still look like motion blur" has to be measured rather than asserted. The
reference is a render of the same frames WITH the shutter open (`render_passes.py
--blur-reference`) — ground truth for the default head, a `MASTER_COST` line per master version,
never a per-order render.

The gate carries its own negative controls (invariant 12): the same comparison is run for **no
blur at all** and for a **doubled shutter**, and the blur must be clearly closer to the truth than
both. A gate that only checks an absolute number would pass a blur that does nothing.

That comparison only means something where the picture actually moves: measured on SHOT_001 v01 at
25 %, frame 1090 travels 14 px and separates the blur from no blur by 1.5×, while frame 1001
travels 0.3 px and the three images are identical to three decimals. So the controls are required
on frames whose longest path clears `discriminating_min_path_px`; a slower frame is reported as
non-discriminating, and a run where NO frame discriminates fails — it proved nothing.

Both images come from separate renders, so per-pixel noise dominates a raw difference; the metric
is measured on a 4×4 box low-pass of both.

Exit 0 with BLUR_FIDELITY_OK, exit 2 with BLUR_FIDELITY_ERROR."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import motion_blur  # noqa: E402
from slice.composite import derive, read_parts  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
BF = CONV["blur_fidelity"]


class FidelityError(RuntimeError):
    pass


def fail(msg):
    print(f"BLUR_FIDELITY_ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def low_pass(a, k=4):
    h, w = a.shape[:2]
    a = a[:h // k * k, :w // k * k]
    return a.reshape(h // k, k, w // k, k, *a.shape[2:]).mean(axis=(1, 3))


def dilate(mask, n):
    m = mask.copy()
    for _ in range(n):
        k = m.copy()
        k[1:] |= m[:-1]
        k[:-1] |= m[1:]
        k[:, 1:] |= m[:, :-1]
        k[:, :-1] |= m[:, 1:]
        m = k
    return m


def error_against(truth, img, regions):
    e = np.abs(low_pass(img[..., :3]) - low_pass(truth[..., :3])).max(axis=-1)
    out = {}
    for name, mask in regions.items():
        m = low_pass(mask.astype(np.float32)) > 0.25
        out[name] = round(float(e[m].mean()), 5) if m.any() else None
    return out


def layers_of(parts, d, head_layer):
    def vd(prefix):
        vec = parts[f"{prefix}_MOTION_VECTORS"][0].astype(np.float32)
        dep = parts[f"{prefix}_DEPTH"][0].astype(np.float32)
        return vec, (dep[..., 0] if dep.ndim == 3 else dep)
    return [(d["front"], *vd("FRONT")), (head_layer, *vd("HEAD")), (d["back"], *vd("BACK"))]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", required=True, help="the profile directory that composite.py wrote into")
    ap.add_argument("--reference", required=True, help="the directory of the --blur-reference render (its <profile>/raw)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--may-be-non-discriminating", action="store_true",
                    help="a smoke run at reduced scale, where the shot's own motion may be too small to tell the blur "
                         "from no blur: report NOT_APPLICABLE instead of failing. Never for a delivery check at 100 %")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd = Path(args.renders)

    try:
        bundles = sorted(pd.glob("bundle_manifest.*.json"))
        if len(bundles) != 1:
            raise FidelityError(f"expected one bundle_manifest in {pd}, found {len(bundles)} — run composite.py first")
        bm = json.loads(bundles[0].read_text())
        rm = json.loads((pd / bm["source_render_manifest"]).read_text())
        shutter_frames = rm["settings"]["shutter_angle_deg"] / 360.0
        if shutter_frames <= 0:
            raise FidelityError("this profile's shutter is 0: nothing is blurred, so there is nothing to compare")
        if rm["settings"].get("render_motion_blur"):
            raise FidelityError("the plates carry rendered motion blur; since the 2026-09-22 amendment they are "
                                "rendered sharp and blurred after compositing, and this gate measures that blur")

        ref_dir = Path(args.reference)
        ref_manifests = sorted(ref_dir.glob("render_manifest.*.json")) or sorted(ref_dir.glob("*/render_manifest.*.json"))
        if len(ref_manifests) != 1:
            raise FidelityError(f"expected one render_manifest under {ref_dir}, found {len(ref_manifests)}")
        ref_man = json.loads(ref_manifests[0].read_text())
        if ref_man.get("kind") != "blur_reference":
            raise FidelityError(f"{ref_manifests[0].name} is a plate render, not a blur reference — "
                                "re-render it with render_passes.py --blur-reference")
        if not ref_man["settings"].get("render_motion_blur"):
            raise FidelityError("the reference render carries no motion blur — it cannot be the ground truth")
        if ref_man["settings"]["shutter_angle_deg"] != rm["settings"]["shutter_angle_deg"]:
            raise FidelityError(f"reference shutter {ref_man['settings']['shutter_angle_deg']}° != plates' "
                                f"{rm['settings']['shutter_angle_deg']}°")
        if ref_man["settings"]["resolution_percentage"] != rm["settings"]["resolution_percentage"]:
            raise FidelityError("reference and plates were rendered at different scales")
        ref_raw = ref_manifests[0].parent / "raw"
        ref_files = {row["frame"]: ref_raw / row["files"]["blur_reference"]["file"] for row in ref_man["frames"]}

        comp_dir = pd / "COMPOSITE_BUNDLE"
        derived = bm["bundles"]["COMPOSITE_BUNDLE"].get("derived")
        if not derived:
            raise FidelityError(f"{bundles[0].name} carries no compositor section — run composite.py first")
        blur_by_frame = {r["frame"]: r.get("post_composite_blur") for r in derived["frames"]}
        if not any(blur_by_frame.values()):
            raise FidelityError("the composite ran without the post-composite blur — re-run composite.py on plates "
                                "rendered since the 2026-09-22 amendment")
        raw_by_frame = {row["frame"]: pd / "raw" / row["files"]["beauty"]["file"] for row in rm["frames"]}
        rule = BF["pass_rule"]
        # Whether this run can prove anything is known from the manifests alone: decide it before
        # spending a single blur on it.
        measurable = [r["frame"] for r in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"] if r["frame"] in ref_files]
        fast = [f for f in measurable if (blur_by_frame.get(f) or {}).get("longest_path_px", 0.0) >= rule["discriminating_min_path_px"]]
        if not measurable:
            raise FidelityError("no frame is present in both the plate render and the blur reference")
        if not fast:
            why = (f"none of the measured frames {measurable} moves more than {rule['discriminating_min_path_px']} px "
                   f"during the shutter at {rm['settings']['resolution_percentage']} %, so this run cannot tell the blur "
                   "from no blur at all")
            if not args.may_be_non_discriminating:
                raise FidelityError(why + ": pick a frame with the fastest relative motion (slice/pick_frames.py does) "
                                          "or render at a larger scale")
            report = {"gate": "blur_fidelity", "status": "NOT_APPLICABLE", "reason": why,
                      "criterion": BF["criterion"], "pass_rule": rule, "frames": measurable,
                      "paths_px": {f: (blur_by_frame.get(f) or {}).get("longest_path_px") for f in measurable},
                      "scale_percent": rm["settings"]["resolution_percentage"]}
            (out / "blur_fidelity_report.json").write_text(json.dumps(report, indent=1) + "\n")
            print(f"BLUR_FIDELITY_NOT_APPLICABLE {why} — the blur was NOT exercised by this run "
                  f"-> {out / 'blur_fidelity_report.json'}")
            return
        rows, failed = [], []
        for row in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]:
            frame = row["frame"]
            if frame not in ref_files:
                continue
            blurred_path = comp_dir / f"blurred_default_head.{frame:04d}.exr"
            if not blurred_path.exists():
                raise FidelityError(f"{blurred_path.name} missing — composite.py must run with a shutter > 0")
            parts, d, _ = derive(comp_dir / row["file"])
            raw = read_parts(raw_by_frame[frame])
            head_layer = raw["L_HEAD.Combined"][0].astype(np.float32)
            truth_parts = read_parts(ref_files[frame])
            if "L_FULL.Combined" not in truth_parts:
                raise FidelityError(f"{ref_files[frame].name}: L_FULL.Combined missing")
            truth = truth_parts["L_FULL.Combined"][0].astype(np.float32)
            blurred = read_parts(blurred_path)["BLURRED_DEFAULT_HEAD"][0].astype(np.float32)
            sharp = motion_blur.over(d["front"], motion_blur.over(head_layer, d["back"]))
            doubled, dbl_report = motion_blur.blur(layers_of(parts, d, head_layer), shutter_frames * 2)

            regions = {"head": dilate(head_layer[..., 3] > 0.05, 10), "frame": np.ones(truth.shape[:2], bool)}
            e_blur = error_against(truth, blurred, regions)
            e_sharp = error_against(truth, sharp, regions)
            e_double = error_against(truth, doubled, regions)
            blur_row = blur_by_frame.get(frame) or {}
            path = blur_row.get("longest_path_px", 0.0)
            discriminating = path >= rule["discriminating_min_path_px"]
            ratio = lambda e: round(e["head"] / e_blur["head"], 3) if e_blur["head"] else None  # noqa: E731
            checks = {
                "head_mean_max": {"value": e_blur["head"], "limit": rule["head_mean_max"],
                                  "ok": e_blur["head"] is not None and e_blur["head"] <= rule["head_mean_max"]},
                "beats_no_blur": {"ratio": ratio(e_sharp), "limit": rule["discrimination_min_ratio"],
                                  "required": discriminating,
                                  "ok": not discriminating or (e_blur["head"] is not None and e_sharp["head"] >= e_blur["head"] * rule["discrimination_min_ratio"])},
                "beats_doubled_shutter": {"ratio": ratio(e_double), "limit": rule["discrimination_min_ratio"],
                                          "required": discriminating,
                                          "ok": not discriminating or (e_blur["head"] is not None and e_double["head"] >= e_blur["head"] * rule["discrimination_min_ratio"])},
            }
            bad = [k for k, v in checks.items() if not v["ok"]]
            rows.append({"frame": frame, "status": "FAIL" if bad else "PASS", "failed": bad,
                         "longest_path_px": path, "discriminating": discriminating,
                         "error_vs_true_blur": {"post_composite_blur": e_blur, "negative_control_no_blur": e_sharp,
                                                "negative_control_doubled_shutter": e_double},
                         "checks": checks, "blur": blur_row, "doubled_shutter_samples": dbl_report["samples"]})
            if bad:
                failed.append(frame)
            print(f"BLUR_FIDELITY_FRAME {frame} {'FAIL' if bad else 'PASS'} "
                  f"{'discriminating' if discriminating else 'too slow to discriminate'} path={path}px "
                  f"head_err={e_blur['head']} (no blur {e_sharp['head']}, doubled {e_double['head']}) frame_err={e_blur['frame']}")
        discriminating = [r["frame"] for r in rows if r["discriminating"]]
        report = {"gate": "blur_fidelity", "status": "FAIL" if failed else "PASS", "criterion": BF["criterion"],
                  "discriminating_frames": discriminating,
                  "metric": BF["metric"], "pass_rule": rule, "thresholds_status": BF["status"],
                  "negative_controls": BF["negative_controls"], "shutter_frames": shutter_frames,
                  "scale_percent": rm["settings"]["resolution_percentage"], "samples": rm["settings"]["samples"],
                  "reference_samples": ref_man["settings"]["samples"], "frames": rows}
        (out / "blur_fidelity_report.json").write_text(json.dumps(report, indent=1) + "\n")
        if failed:
            fail(f"the post-composite blur does not reproduce the rendered blur on frames {failed} "
                 f"({BF['status'].split(' - ')[0]}) -> {out / 'blur_fidelity_report.json'}")
        print(f"BLUR_FIDELITY_OK {len(rows)} frames, {len(discriminating)} of them fast enough to discriminate "
              f"({discriminating}) -> {out / 'blur_fidelity_report.json'}")
    except (FidelityError, KeyError, motion_blur.BlurError) as e:
        fail(str(e))


if __name__ == "__main__":
    main()
