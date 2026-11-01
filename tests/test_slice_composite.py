"""composite.py: derived passes and the precomp-reproduction report. CI checks the declared
formulas exist and are consistent; on the slice machine a 64-sample smoke frame is rendered,
split, composited and every derived part checked against an independent computation."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice import skin_probe  # noqa: E402
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
OCIO_CONFIG = ROOT / "benchmarks" / "bakeoff" / "01J7B000000000000000BAKEXP" / "slice" / "ocio" / "studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv").exists() else "python3"


def test_every_derived_pass_has_a_formula_type_and_alpha_declaration():
    derived = CONV["bundles"]["COMPOSITE_BUNDLE"]["derived_by_compositor"]
    spec = CONV["compositor"]["derived"]
    for name in derived:
        assert name in spec and spec[name]["formula"] and spec[name]["pixel_type"] in ("half", "float") and spec[name]["alpha"] in ("PREMULTIPLIED", "NOT_APPLICABLE"), name
    assert "STATIC_PRECOMP" in spec and "PRECOMP_BACK" in spec["STATIC_PRECOMP"] and "PRECOMP_FRONT" in spec["STATIC_PRECOMP"]
    assert 0 < spec["HEAD_SHADOW_MULTIPLY"]["epsilon_scene_linear"] < 1e-2


@pytest.mark.skipif(shutil.which("blender") is None, reason="Blender not installed")
def test_plates_whose_vectors_do_not_reach_the_shutter_ends_are_refused_not_blurred_on_a_guess():
    """ADR-0002 amendment 2026-09-25: the blur's path runs through the positions the vectors point
    at, which must be the shutter's open and close. Plates rendered before it carry vectors to
    frame ±1 and no settings.vector_reach_frames; blurring them as if they reached the shutter's
    ends would be a silent wrong blur (on SHOT_002 1209 the frame-vector path missed the ends by
    6.2 px median at 4K)."""
    code = f"""import sys; sys.path.insert(0, {str(ROOT)!r})
from slice.composite import vector_reach, CompositeError
print('REACH', vector_reach({{'vector_reach_frames': 0.25}}, 0.5, 'm'), vector_reach({{}}, 0.0, 'm'))
for st in ({{}}, {{'vector_reach_frames': 1.0}}):
    try:
        vector_reach(st, 0.5, 'm'); print('NOT_REFUSED', st)
    except CompositeError as e:
        print('REFUSED', 'vector_reach_frames' in str(e) or 'shutter' in str(e))"""
    r = subprocess.run(["blender", "-b", "--python-exit-code", "2", "--python-expr", code], capture_output=True, text=True, timeout=300,
                       env=dict(os.environ, OCIO=str(OCIO_CONFIG)))
    lines = [l for l in r.stdout.splitlines() if l.startswith(("REACH", "REFUSED", "NOT_REFUSED"))]
    assert lines == ["REACH 0.25 None", "REFUSED True", "REFUSED True"], r.stdout[-1500:] + r.stderr[-1500:]


@pytest.mark.skipif(shutil.which("blender") is None or shutil.which("oiiotool") is None, reason="Blender/oiiotool not installed")
def test_smoke_frame_composites_and_derived_parts_agree_with_independent_checks(tmp_path):
    env = dict(os.environ, OCIO=str(OCIO_CONFIG))
    blend = tmp_path / "template.blend"
    subprocess.run(["blender", "-b", "--python-exit-code", "2", "-P", str(ROOT / "slice" / "scene_template.py"), "--", "--out", str(blend)], capture_output=True, text=True, timeout=300, env=env, check=True)
    out = tmp_path / "renders"
    r = subprocess.run(["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice" / "render_passes.py"), "--", "--shot", "SHOT_001", "--profile", "video", "--frames", "1001", "--samples", "64", "--scale", "10", "--probe", "--out", str(out)], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    exports = tmp_path / "exports"
    r = subprocess.run(["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice" / "export_shot.py"), "--", "--shot", "SHOT_001", "--out", str(exports)], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(["blender", "-b", "--python-exit-code", "2", "-P", str(ROOT / "slice" / "split_bundles.py"), "--", str(out / "video"), "--exports", str(exports)], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    r = subprocess.run(["blender", "-b", "--python-exit-code", "2", "-P", str(ROOT / "slice" / "composite.py"), "--", str(out / "video")], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0 and "COMPOSITE_OK" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
    derived = out / "video" / "COMPOSITE_BUNDLE" / "derived.1001.exr"
    info = subprocess.run(["oiiotool", "--info", "-v", "-a", str(derived)], capture_output=True, text=True, timeout=120).stdout
    for name in CONV["bundles"]["COMPOSITE_BUNDLE"]["derived_by_compositor"]:
        assert f'oiio:subimagename: "{name}"' in info, name
    assert 'compression: "zip"' in info
    # Independent checks with oiiotool on the written files:
    composite = out / "video" / "COMPOSITE_BUNDLE" / "composite.1001.exr"
    def stats(path, part, ch=None):
        args = ["oiiotool", str(path), "--subimage", part] + (["--ch", ch] if ch else []) + ["--printstats"]
        o = subprocess.run(args, capture_output=True, text=True, timeout=120).stdout
        import re
        return {k: [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", re.search(rf"Stats {k}: ([^\n(]+)", o).group(1))] for k in ("Min", "Max", "Avg")}
    mult = stats(derived, "HEAD_SHADOW_MULTIPLY")
    assert min(mult["Min"]) < 0.9, "the default head must actually shadow the body somewhere (measured 0.62 on the placeholder)"
    # ASSUMPTION of this test: the placeholder head is 100 % HERO_SKIN_HEAD with no visible hair,
    # so the material-cryptomatte skin coverage of the head must equal the head's holdout
    # silhouette wherever the occluder does not cover it — per pixel, exactly.
    r = subprocess.run(["blender", "-b", "--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
import numpy as np
from slice.composite import read_parts
c = read_parts({str(composite)!r}); d = read_parts({str(derived)!r})
hold = c['HEAD_HOLDOUT'][0][..., 0]; skin = d['SKIN_ID_HEAD'][0][..., 0]; fg = d['PRECOMP_FRONT'][0][..., 3]
clear = fg < 1e-6
print('MAXDIFF', float(np.abs(hold[clear] - skin[clear]).max()), 'PIX', int(clear.sum()))"""], capture_output=True, text=True, timeout=300, env=env)
    m = [l for l in r.stdout.splitlines() if l.startswith("MAXDIFF")]
    assert m and float(m[0].split()[1]) == 0.0 and int(m[0].split()[3]) > 1000, r.stdout[-800:] + r.stderr[-800:]
    assert stats(derived, "SKIN_ID_BODY")["Max"][0] > 0.99, "body skin (neck top, hand) must be present"
    report = json.loads((out / "video" / "COMPOSITE_BUNDLE" / "precomp_report.1001.json").read_text())
    rep = report["precomp_reproduction"]
    assert report["multiply_clipped_fraction"] < 1e-3          # measured 4e-5: half-ULP excess only
    assert rep["status"] == "PASS" and rep["pass_rule"]["failed"] == [] and rep["within"]["0.05"]["inside_band"] >= 0.9
    assert rep["within"]["0.001"]["outside_band"] > 0.995 and rep["band_fraction"] < 0.05
    assert rep["same_seed_layer_agreement_away_from_head"]["fraction_bit_exact"] > 0.99
    fp = report["occluder_footprint"]
    assert fp["pixels"] > 100 and fp["back_vs_body_max_abs"] < 0.05 and fp["back_vs_front_mean_abs"] > 0.5, fp  # BACK holds the body, not the hand
    bm = json.loads((out / "video" / "bundle_manifest.video.json").read_text())
    assert bm["bundles"]["COMPOSITE_BUNDLE"]["derived"]["frames"][0]["file"] == "derived.1001.exr"
    assert bm["working_space"] == "ACEScg"
    r = subprocess.run(["blender", "-b", "--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
from slice.composite import read_parts
for path in ({str(derived)!r}, {str(composite)!r}):
    for name, (pix, attrs, ch) in read_parts(path).items():
        print('COLOUR', name, attrs.get('slice:alpha'), attrs.get('colorInteropID'))"""], capture_output=True, text=True, timeout=300, env=env)
    rows = [l.split() for l in r.stdout.splitlines() if l.startswith("COLOUR")]
    assert len(rows) >= 19, r.stdout[-800:] + r.stderr[-800:]
    for _, name, alpha, colour in rows:
        assert (colour == "data") == (alpha == "NOT_APPLICABLE"), (name, alpha, colour)
        if alpha == "PREMULTIPLIED":
            assert colour == "lin_ap1_scene", (name, colour)
    # ---- per-order composite entry point (conventions → compositor.per_order)
    B = ["blender", "-b", "--python-exit-code", "2"]
    inputs = tmp_path / "default_head_inputs"
    # 1. prerequisite gate: no round-trip yet → refused
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "default-head-inputs", "--bundle", str(out / "video"), "--out", str(inputs)], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "prerequisite gate" in r.stderr and "round-trip" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "roundtrip.py"), "--", "--exports", str(exports), "--renders", str(out / "video")], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0 and "ROUNDTRIP_OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]  # 10 % run: floor thresholds, a weaker test (report says smoke_test_only)
    # 1b. the round-trip PASS is bound to the exports delivered in the bundle: a PASS obtained
    #     against other exports (re-exported after the split) does not unlock the order composite
    other = tmp_path / "exports_other"
    shutil.copytree(exports, other)
    (other / "export_manifest.json").write_text((other / "export_manifest.json").read_text().replace("\n}", ",\n \"note\": \"re-exported\"\n}"))
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "roundtrip.py"), "--", "--exports", str(other), "--renders", str(out / "video")], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "default-head-inputs", "--bundle", str(out / "video"), "--out", str(inputs)], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "not the exports the round-trip validated" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "roundtrip.py"), "--", "--exports", str(exports), "--renders", str(out / "video")], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    # 2. identity run: the default head's own layer and multiply must reproduce DEFAULT_HEAD_BEAUTY
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "default-head-inputs", "--bundle", str(out / "video"), "--out", str(inputs)], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0 and "DEFAULT_HEAD_INPUTS_OK" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    order = tmp_path / "order"
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(inputs / "shadow"), "--head-vectors", str(inputs / "head_mv"), "--skin-tone", "master", "--order-id", "01J7B00000000000000TESTORD", "--out", str(order), "--record-default-head-reproduction"], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0 and "ORDER_COMPOSITE_OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    om = json.loads((order / "order_composite_manifest.json").read_text())
    assert om["fallbacks"] == [] and om["status"] == "PASS" and om["frames"][0]["metrics"]["unfilled_fraction"] == 0.0
    assert len(om["idempotency_key"]) == 64 and not (order / ".staging").exists()
    f0 = om["frames"][0]   # t_comp and S_frame for the bake-off record (Phase 0.5 exit review, criterion 6)
    cb = out / "video" / "COMPOSITE_BUNDLE"
    assert f0["t_comp"]["wall_s"] > 0 and f0["t_comp"]["cpu_s"] > 0
    assert f0["master_bytes_read"] == (cb / f0["inputs"]["composite"]["file"]).stat().st_size + (cb / f0["inputs"]["derived"]["file"]).stat().st_size
    # video: the per-order FINAL is blurred after compositing (ADR-0002 D5 amendment 2026-09-22) — with the default head's own
    # layer, multiply and vectors it is the QC path's blurred frame, which the blur-fidelity gate measures, up to the half
    # quantization of the precomp pair and multiply the per-order path reads
    assert om["post_composite_blur"]["applied"] and "post_composite_blur" in f0["metrics"] and f0["metrics"]["post_composite_blur"]["samples"] >= 16
    vq = f0["metrics"]["vs_qc_blurred_default_head"]
    assert vq["within_2_half_steps"] >= 0.999, vq
    # a re-run with the same key (same inputs, gate and flags) over a PASS is a verified no-op; a different order in the same directory is refused
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(inputs / "shadow"), "--head-vectors", str(inputs / "head_mv"), "--skin-tone", "master", "--order-id", "01J7B00000000000000TESTORD", "--out", str(order), "--record-default-head-reproduction"], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0 and "no-op" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(inputs / "shadow"), "--head-vectors", str(inputs / "head_mv"), "--skin-tone", "master", "--order-id", "01J7B00000000000000OTHERORD", "--out", str(order)], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "refused" not in r.stdout and "use another directory" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    assert om["frames"][0]["inputs"]["head_layer"]["sha256"] and om["frames"][0]["metrics"]["multiply_out_of_range_fraction"] == 0.0
    r = subprocess.run(["blender", "-b", "--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
import numpy as np
from slice.composite import read_parts
from slice.matte_metrics import edge_band
final = read_parts({str(order / 'final.1001.exr')!r})['FINAL']
qc = next(iter(read_parts({str(out / 'video' / 'COMPOSITE_BUNDLE' / 'blurred_default_head.1001.exr')!r}).values()))
err = np.abs(final[0] - qc[0]).max(-1)
step = np.spacing(np.maximum(np.abs(qc[0]).max(-1), 6.1e-5).astype(np.float16)).astype(np.float32)
print('ORDERCHECK', float((err <= 2 * step).mean()), float(err.max()), final[1].get('colorInteropID'), final[1].get('slice:alpha'))"""], capture_output=True, text=True, timeout=300, env=env)
    row = [l.split() for l in r.stdout.splitlines() if l.startswith("ORDERCHECK")]
    assert row and float(row[0][1]) >= 0.999 and row[0][3] == "lin_ap1_scene" and row[0][4] == "PREMULTIPLIED", r.stdout[-800:] + r.stderr[-800:]
    # 3. negative control: a head layer shifted 8 px does not fill the holdout → gate FAIL, no frame written
    shifted = tmp_path / "shifted_head"
    shifted.mkdir()
    r = subprocess.run(["blender", "-b", "--python-exit-code", "2", "--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
import numpy as np
from slice.composite import read_parts, write_parts
name, (pix, attrs, ch) = next(iter(read_parts({str(inputs / 'head' / 'head.1001.exr')!r}).items()))
write_parts({str(shifted / 'head.1001.exr')!r}, [('HEAD_LAYER', np.roll(pix, 8, axis=1), ch, 'half', 'PREMULTIPLIED')], {{k: attrs[k] for k in ('colorInteropID', 'oiio:ColorSpace') if k in attrs}})"""], capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(shifted), "--shadow-multiply", str(inputs / "shadow"), "--head-vectors", str(inputs / "head_mv"), "--skin-tone", "master", "--order-id", "01J7B00000000000000TESTBAD", "--out", str(tmp_path / "order_bad")], capture_output=True, text=True, timeout=600, env=env)
    # the head moved off its own silhouette: unfilled fails (and, where the shift uncovers the seam, seam_unfilled with it)
    assert r.returncode == 2 and "gate FAIL on ['unfilled_fraction'" in r.stderr and not (tmp_path / "order_bad" / "final.1001.exr").exists(), r.stdout[-800:] + r.stderr[-800:]
    assert json.loads((tmp_path / "order_bad" / "order_composite_manifest.json").read_text())["status"] == "FAIL"
    # 3b. a display-referred / 8-bit shadow map (values above 1) is a gate failure, never clamped to "no shadow"
    bad_shadow = tmp_path / "bad_shadow"
    bad_shadow.mkdir()
    r = subprocess.run(["blender", "-b", "--python-exit-code", "2", "--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
import numpy as np
from slice.composite import read_parts, write_parts
name, (pix, attrs, ch) = next(iter(read_parts({str(inputs / 'shadow' / 'shadow.1001.exr')!r}).items()))
write_parts({str(bad_shadow / 'shadow.1001.exr')!r}, [('SHADOW_MULTIPLY', pix * 255.0, ch, 'half', 'NOT_APPLICABLE')], {{}})"""], capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(bad_shadow), "--head-vectors", str(inputs / "head_mv"), "--skin-tone", "master", "--order-id", "01J7B00000000000000TESTOOR", "--out", str(tmp_path / "order_oor")], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "multiply_out_of_range_fraction" in r.stderr and not list((tmp_path / "order_oor").glob("final.*.exr")), r.stdout[-800:] + r.stderr[-800:]
    # 3c. with the shutter open the head's own vectors are required: the blur is never skipped
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(inputs / "shadow"), "--skin-tone", "master", "--order-id", "01J7B00000000000000TESTNMV", "--out", str(tmp_path / "order_nomv")], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "never skipped" in r.stderr and not list((tmp_path / "order_nomv").glob("final.*.exr")), r.stdout[-800:] + r.stderr[-800:]
    # 3d. the order's skin tone (ADR-0002 amendment 2026-09-29, amended 2026-10-31): refused until the bundle carries the
    #     master's skin probe and a passing gate of the probe method; with both, the skin changes and nothing else does; a
    #     tone outside the range is a reject, never clamped
    base = ["compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(inputs / "shadow"), "--head-vectors", str(inputs / "head_mv")]
    def tone_run(tone, oid, dst):
        return subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", *base, "--skin-tone", tone, "--order-id", oid, "--out", str(dst)], capture_output=True, text=True, timeout=600, env=env)
    r = tone_run("0.4,0.24,0.16", "01J7B00000000000000TESTTN1", tmp_path / "order_tone0")
    assert r.returncode == 2 and "SKIN_PROBE_BUNDLE" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    bmp = out / "video" / "bundle_manifest.video.json"
    bmj = json.loads(bmp.read_text())
    assert bmj["bundles"]["COMPOSITE_BUNDLE"]["derived"]["skin_tone"]["master_albedo"], "composite.py records the master's skin albedo"
    bmj["skin_tone"] = {"status": "PASS", "supported_range": {"min": [0.2, 0.11, 0.07], "max": [0.9, 0.72, 0.62]}}   # the first-order gate's record
    bmp.write_text(json.dumps(bmj, indent=1) + "\n")
    first_order = dict(bmj["skin_tone"])
    probe_blend, probe_out = tmp_path / "probe.blend", tmp_path / "probe_renders"
    r = subprocess.run(["blender", "-b", str(blend), "--python-exit-code", "2", "-P", str(ROOT / "slice" / "skin_probe.py"), "--", "set-tone", "--tone", ",".join(map(str, CONV["skin_tone"]["probe"]["tone"])), "--out", str(probe_blend)], capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0 and "TONE_SET" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(["blender", "-b", str(probe_blend), "--python-exit-code", "2", "-P", str(ROOT / "slice" / "render_passes.py"), "--", "--shot", "SHOT_001", "--profile", "video", "--frames", "1001", "--samples", "64", "--scale", "10", "--skin-probe", "--out", str(probe_out)], capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    derive = lambda probe_dir, *extra: subprocess.run(B + ["-P", str(ROOT / "slice" / "skin_probe.py"), "--", "derive", str(out / "video"), str(probe_dir), *extra], capture_output=True, text=True, timeout=600, env=env)  # noqa: E731
    r = derive(out / "video")
    assert r.returncode == 2 and "not a skin probe" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    r = derive(probe_out / "video")
    assert r.returncode == 0 and "SKIN_PROBE_OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    r = derive(probe_out / "video")
    assert r.returncode == 2 and "--replace" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    bmj = json.loads(bmp.read_text())
    sp = bmj["bundles"]["SKIN_PROBE_BUNDLE"]
    assert [p["name"] for p in sp["frames"][0]["parts"]] == CONV["skin_tone"]["probe"]["parts"] and sp["probe"]["albedo"] == [round(v, 6) for v in CONV["skin_tone"]["probe"]["tone"]]
    assert sp["probe"]["direct_light_z_worst"] <= CONV["skin_tone"]["probe"]["direct_light_z_max"]
    # the gate's record beside the bundle before the probe was derived vouches for no probe: moved aside, kept (Q79-1)
    assert "skin_tone" not in bmj and bmj["skin_tone_retired"][0]["status"] == first_order["status"]
    assert sp["probe"]["direct_light_measured_layers"] >= 1 and sp["probe"]["direct_light_interior"] == CONV["skin_tone"]["probe"]["direct_light_interior"]
    # the layers with skin are the frames' layers not NO_SKIN (a layer with the material and no skin is NO_SKIN:
    # tests/test_skin_probe.py; on the smoke frame the body shows none, the front plate's hand does)
    assert sp["probe"]["direct_light_layers_with_skin"] == sum(v != "NO_SKIN" for r in sp["frames"] for v in r["direct_light_mismatch"].values())
    # the edge (owner 2026-11-01, decision 13 (A)): the pixels the skin shares with cloth, found and counted
    assert sp["probe"]["edge"] == CONV["skin_tone"]["probe"]["edge"] and sum(sp["frames"][0]["edge_px"].values()) > 0
    # a derive that fails half way (here: the guard refuses a layer) leaves what was there, and nothing half written
    before = {f.name: f.read_bytes() for f in (out / "video" / "SKIN_PROBE_BUNDLE").iterdir()}
    r = subprocess.run(B + ["--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
from slice import skin_retint, skin_probe
def refuse(*a, **k):
    raise skin_retint.SkinRetintError("the probe's direct diffuse light is off (planted)")
skin_retint.probe_parts = refuse
try:
    skin_probe.derive({str(out / 'video')!r}, {str(probe_out / 'video')!r}, replace=True)
except skin_retint.SkinRetintError as e:
    print("REFUSED", e)
"""], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0 and "REFUSED" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    assert {f.name: f.read_bytes() for f in (out / "video" / "SKIN_PROBE_BUNDLE").iterdir()} == before
    assert json.loads(bmp.read_text())["bundles"]["SKIN_PROBE_BUNDLE"] == sp
    assert not [p for p in (out / "video").iterdir() if p.name.startswith("SKIN_PROBE_BUNDLE") and p.name != "SKIN_PROBE_BUNDLE"]
    bmj["skin_tone"] = first_order
    bmp.write_text(json.dumps(bmj, indent=1) + "\n")
    r = tone_run("0.4,0.24,0.16", "01J7B00000000000000TESTTN5", tmp_path / "order_tone5")
    assert r.returncode == 2 and "probe method" in r.stderr, "a gate measured on the first-order re-tint does not admit the probe's: " + r.stdout[-800:] + r.stderr[-800:]
    # the gate's record as check_skin_tone.record_in_bundles writes it: beside this probe (burst 6 review Q79-1, 2026-11-01)
    pb = bmj["bundles"]["SKIN_PROBE_BUNDLE"]["probe"]
    bound = {"status": "PASS", "method": "probe", "supported_range": {"min": [0.2, 0.11, 0.07], "max": [0.9, 0.72, 0.62]},
             "probe_albedo": pb["albedo"], "master_albedo": pb["master_albedo"], "probe_bundle_sha256": skin_probe.probe_fingerprint(bmj)}
    for over, oid, why in (({"probe_bundle_sha256": "0" * 64}, "01J7B00000000000000TESTTN7", "another"),
                           ({"status": "VACUOUS"}, "01J7B00000000000000TESTTN8", "VACUOUS")):
        bmj["skin_tone"] = bound | over
        bmp.write_text(json.dumps(bmj, indent=1) + "\n")
        r = tone_run("0.4,0.24,0.16", oid, tmp_path / f"order_{oid[-3:]}")
        assert r.returncode == 2 and why in r.stderr and not list((tmp_path / f"order_{oid[-3:]}").glob("final.*.exr")), r.stdout[-800:] + r.stderr[-800:]
    bmj["skin_tone"] = bound
    older = json.loads(json.dumps(bmj))
    for row in older["bundles"]["SKIN_PROBE_BUNDLE"]["frames"]:
        row["parts"] = [q for q in row["parts"] if not q["name"].startswith(("EDGE_", "SHARED_"))]   # derived before the edge
    bmp.write_text(json.dumps(older, indent=1) + "\n")
    r = tone_run("0.4,0.24,0.16", "01J7B00000000000000TESTTN6", tmp_path / "order_tone6")
    assert r.returncode == 2 and "older rule" in r.stderr and not list((tmp_path / "order_tone6").glob("final.*.exr")), r.stdout[-800:] + r.stderr[-800:]
    bmp.write_text(json.dumps(bmj, indent=1) + "\n")
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", *base, "--skin-tone", "0.05,0.05,0.05", "--order-id", "01J7B00000000000000TESTTN2", "--out", str(tmp_path / "order_tone_out")], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "outside the master's supported range" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", *base, "--skin-tone", "dark", "--order-id", "01J7B00000000000000TESTTN3", "--out", str(tmp_path / "order_tone_bad")], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "R,G,B" in r.stderr, r.stdout[-800:] + r.stderr[-800:]
    # a probe frame that is not the bundle's (another bundle's file in its place): refused before it is read (finding 8)
    pf = out / "video" / "SKIN_PROBE_BUNDLE" / bmj["bundles"]["SKIN_PROBE_BUNDLE"]["frames"][0]["file"]
    kept = pf.read_bytes()
    pf.write_bytes(kept + b"\0")
    r = tone_run("0.4,0.24,0.16", "01J7B00000000000000TESTTN9", tmp_path / "order_tone9")
    pf.write_bytes(kept)
    assert r.returncode == 2 and "not the frame of the probe" in r.stderr and not list((tmp_path / "order_tone9").glob("final.*.exr")), r.stdout[-800:] + r.stderr[-800:]
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", *base, "--skin-tone", "0.4,0.24,0.16", "--order-id", "01J7B00000000000000TESTTN4", "--out", str(tmp_path / "order_tone")], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0 and "ORDER_COMPOSITE_OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]
    omt = json.loads((tmp_path / "order_tone" / "order_composite_manifest.json").read_text())
    assert omt["skin_tone"]["applied"] and omt["skin_tone"]["gain"][0] < 1.0 and omt["skin_tone"]["method"] == "probe" and 0 < omt["skin_tone"]["weight"][0] < 1
    assert omt["skin_tone"]["probe_bundle_sha256"] == bound["probe_bundle_sha256"]
    r = subprocess.run(["blender", "-b", "--python-expr", f"""import sys; sys.path.insert(0, {str(ROOT)!r})
import numpy as np
from slice.composite import read_parts
a = read_parts({str(order / 'final.1001.exr')!r})['FINAL'][0]; b = read_parts({str(tmp_path / 'order_tone' / 'final.1001.exr')!r})['FINAL'][0]
d = read_parts({str(out / 'video' / 'COMPOSITE_BUNDLE' / 'derived.1001.exr')!r})
sd = d['SKIN_DIFFUSE_BACK'][0][..., :3].max(-1) + d['SKIN_DIFFUSE_FRONT'][0][..., :3].max(-1)
diff = np.abs(a[..., :3] - b[..., :3]).max(-1)
print('TONECHECK', float((sd > 1e-3).mean()), float(diff[sd > 1e-3].mean()) if (sd > 1e-3).any() else 0.0, float(diff[sd == 0].max()))"""], capture_output=True, text=True, timeout=300, env=env)
    row = [l.split() for l in r.stdout.splitlines() if l.startswith("TONECHECK")]
    assert row, r.stdout[-800:] + r.stderr[-800:]
    skin_frac, skin_change, off_skin_max = map(float, row[0][1:])
    assert skin_frac == 0.0 or skin_change > 1e-3, "where the skin's diffuse light is, the tone changes the picture"
    assert off_skin_max < 0.02, "away from the skin (and its blur footprint) the picture does not change"
    # 4. a missing shadow multiply is an error, never the default head's shadow
    r = subprocess.run(B + ["-P", str(ROOT / "slice" / "composite_order.py"), "--", "compose", "--head-silhouette", "default-head", "--bundle", str(out / "video"), "--head-layer", str(inputs / "head"), "--shadow-multiply", str(tmp_path / "nowhere"), "--head-vectors", str(inputs / "head_mv"), "--skin-tone", "master", "--order-id", "01J7B00000000000000TESTMIS", "--out", str(tmp_path / "order_missing")], capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 2 and "missing" in r.stderr and "no substitute" in r.stderr, r.stdout[-800:] + r.stderr[-800:]



@pytest.mark.skipif(shutil.which("blender") is None, reason="Blender not installed")
def test_a_seam_only_failure_below_production_scale_is_pending_not_passed_and_fails_at_100_percent():
    """Owner, 2026-09-27: SEAM_EXTEND cannot judge a sub-pixel sliver of neck skin at 25 % (SHOT_003 1286: -0.083 at 25 %,
    +0.006 at 100 %). A frame whose ONLY failed metric is the seam is SEAM_PENDING_4K below 100 % — never PASS — and a
    plain FAIL at 100 %; any other failed metric fails at every scale. Synthetic plates, in Blender's Python (OIIO)."""
    code = f"""import sys, json; sys.path.insert(0, {str(ROOT)!r})
import numpy as np
import slice.composite as c
h, w = 48, 200
hold = np.zeros((h, w), np.float32); hold[:, :100] = 1.0; hold[:, 100] = 0.5
full = np.full((h, w, 4), 0.5, np.float32)
head = np.dstack([hold * 0.5] * 3 + [hold]).astype(np.float32)
back = np.full((h, w, 4), 0.5, np.float32)
zone = np.zeros((h, w), bool); zone[:, 96:106] = True
front = np.zeros((h, w, 4), np.float32)
d = {{"full": full, "back": back, "front": front, "holdout": hold, "seam_zone": zone, "seam_rings": {{"visible_open_points": 0}}, "seam_extend_stats": {{"replaced_px": 0}}}}
def run(darken, scale):
    ext = back.copy(); ext[zone & (hold > 0), :3] -= darken
    dd = dict(d, back_extended=ext); c.SCALE_PERCENT = scale; report = {{"frame": 1286}}
    try:
        c.reproduction(dd, head, report); err = None
    except c.CompositeError as e:
        err = str(e)
    r = report["precomp_reproduction"]; return {{"status": r["status"], "failed": r["pass_rule"]["failed"], "seam": r["seam"]["signed_mean"], "err": err}}
print("RESULT", json.dumps([run(0.0, 25), run(0.09, 25), run(0.09, 100)]))
"""
    r = subprocess.run(["blender", "-b", "--python-exit-code", "2", "--python-expr", code], capture_output=True, text=True, timeout=300, env=dict(os.environ, OCIO=str(OCIO_CONFIG)))
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    clean, pend, fail = json.loads(r.stdout.split("RESULT ", 1)[1].splitlines()[0])
    assert clean["status"] == "PASS" and clean["err"] is None, clean
    assert pend["failed"] == ["seam_signed_mean_abs_max"] and pend["status"] == "SEAM_PENDING_4K" and pend["err"] is None and pend["seam"] < -0.04, pend
    assert fail["status"] == "FAIL" and fail["err"] and "seam_signed_mean_abs_max" in fail["err"], fail
