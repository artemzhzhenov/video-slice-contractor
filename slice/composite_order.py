"""Per-order composite entry point (conventions.json → compositor.per_order; ADR-0002 D5, D3
amendment). Runs under Blender's Python for numpy + OpenImageIO:

    blender -b --python-exit-code 2 -P slice/composite_order.py -- compose \
        --bundle <pkg>/shots/SHOT_001/renders/<profile> --head-layer <dir> --shadow-multiply <dir> \
        [--head-vectors <dir>] --skin-tone R,G,B|master --order-id <id> --out <dir> [--frames 1001-1010]

    blender -b --python-exit-code 2 -P slice/composite_order.py -- default-head-inputs \
        --bundle <renders/profile> --out <dir>      # QC baseline: the default head's own layer and multiply

FINAL = PRECOMP_FRONT over (HEAD_LAYER over SEAM_EXTEND(BODY_BEAUTY × SHADOW_MULTIPLY_ORDER)), and in the video profile
the post-composite motion blur on those three layers (ADR-0002 D5 amendment 2026-09-22: "in production the head layer is
the order's own, delivered sharp with its own vectors in the same convention; nothing else changes") — the same
slice/motion_blur.py the QC path's blur-fidelity gate measured; the head's vectors and depth are an input of the head
technology (--head-vectors, head_mv.####.exr), required whenever the shutter is open and refused for a still. Until
2026-09-29 this entry point applied no blur (Phase 0.5 exit review, step 5). The body's skin tone (ADR-0002 amendment
2026-09-29, C3, amended 2026-10-31 and 2026-11-01): between the master and its skin probe (slice/skin_retint.py) —
BODY_BEAUTY + (g − 1)·SKIN_DIFFUSE_BACK + w·REST_BACK + g·w·BOUNCE_BACK before the order's shadow multiply, and
BODY_BEAUTY + w·EDGE_BACK at the pixels the skin shares with another surface (SHARED_BACK), the same on PRECOMP_FRONT
with the FRONT parts, g = the order's tone / the master's albedo, w = (tone − master) / (probe − master), before
compositing and the blur; a bundle without SKIN_PROBE_BUNDLE, with one derived by an older rule, or without the probe
method's passing gate re-tints nothing and refuses every tone but 'master'; a tone outside the master's measured range
(slice/check_skin_tone.py) is refused; 'master' re-tints nothing (QC baseline).
The head layer and the order's shadow multiply come from the head technology; nothing is
substituted when either is missing (the default head's multiply would be the wrong head's shadow —
a silent fallback). SEAM_EXTEND (ADR-0002 amendment 2026-09-24, slice/seam_extend.py) extends the
back under the head's lower edge at the seam, exactly as the precomp test does, from the socket
boundary rings in the bundle's exports. Prerequisite gates: the bundle's precomp reproduction and
round-trip must have PASSed (CLAUDE.md §6: money does not flow below an unverified artifact). Per
frame the layer must fill HEAD_HOLDOUT (unfilled fraction gate); overfill and out-of-range
multiply values are reported. Every written frame is re-read and compared with what was computed.
Per frame the manifest records `t_comp` (platform.md: wall-clock and process CPU seconds from reading the inputs to the
re-read check) and `master_bytes_read` (the bundle files this frame reads whole — the composite and the derived EXR, and
the skin probe's when the tone is re-tinted —
i.e. platform.md's S_frame for this consumer), so the bake-off record's measurements come from real runs."""
import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice.composite import over, read_parts, write_parts, seam_context, seam_zone_for, SE, vector_reach, layer_vd, require_blur_parts  # noqa: E402
from slice import motion_blur, seam_extend, skin_retint, skin_probe  # noqa: E402
from slice.order_inputs import head_fill  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
PO = CONV["compositor"]["per_order"]


class OrderCompositeError(RuntimeError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_frames(spec, available):
    if spec is None:
        return available
    a, b = (int(x) for x in spec.split("-")) if "-" in spec else (int(spec), int(spec))
    wanted = [f for f in available if a <= f <= b]
    if len(wanted) != b - a + 1:
        raise OrderCompositeError(f"frames {spec} are not all in the bundle ({available[0]}-{available[-1]})")
    return wanted


def load_bundle(bundle_dir):
    rd = Path(bundle_dir)
    manifests = sorted(rd.glob("bundle_manifest.*.json"))
    if len(manifests) != 1:
        raise OrderCompositeError(f"expected one bundle_manifest in {rd}, found {len(manifests)}")
    bm = json.loads(manifests[0].read_text())
    cb = bm["bundles"]["COMPOSITE_BUNDLE"]
    if not cb.get("derived"):
        raise OrderCompositeError("prerequisite gate: composite.py has not run on this bundle (no derived parts, no precomp reproduction)")
    if bm.get("roundtrip", {}).get("status") != "PASS":
        raise OrderCompositeError(f"prerequisite gate: round-trip status is {bm.get('roundtrip', {}).get('status', 'NOT RUN')!r}, not PASS — the export is not proven to place the head")
    plus = bm["bundles"]["HEAD_RENDER_BUNDLE"].get("plus_files")
    rt_sha = bm["roundtrip"].get("exports", {}).get("export_manifest_sha256")
    if not rt_sha:
        raise OrderCompositeError("prerequisite gate: the round-trip record is not bound to an export manifest (older roundtrip.py) — re-run the round-trip")
    if not plus:
        raise OrderCompositeError("prerequisite gate: HEAD_RENDER_BUNDLE carries no plus files (split with --no-plus-files) — not an order input")
    if plus.get("export_manifest.json") != rt_sha:
        raise OrderCompositeError(f"prerequisite gate: the exports delivered in HEAD_RENDER_BUNDLE ({str(plus.get('export_manifest.json'))[:12]}) are not the exports the round-trip validated ({rt_sha[:12]})")
    derived_by_frame = {r["frame"]: r for r in cb["derived"]["frames"]}
    for r in cb["derived"]["frames"]:
        if r["precomp_reproduction"]["status"] != "PASS":
            raise OrderCompositeError(f"prerequisite gate: precomp reproduction {r['precomp_reproduction']['status']} on frame {r['frame']}")
    return rd, manifests[0], bm, {r["frame"]: r for r in cb["frames"]}, derived_by_frame


def single_part(path, want_channels, what):
    parts = read_parts(path)
    if len(parts) != 1:
        raise OrderCompositeError(f"{what} {path.name}: expected one part, found {list(parts)}")
    (name, (pix, attrs, chans)), = parts.items()
    if chans != want_channels:
        raise OrderCompositeError(f"{what} {path.name}: channels {chans} are not {want_channels}")
    if not np.isfinite(pix).all():
        raise OrderCompositeError(f"{what} {path.name}: non-finite values")
    return pix.astype(np.float32), attrs


def head_motion(path, shape):
    """The head technology's own vectors and depth for this frame (conventions → compositor.per_order.inputs.head_vectors):
    HEAD_MOTION_VECTORS (4 channels, the shutter-open pair then the shutter-close pair) and HEAD_DEPTH, both 'data'."""
    parts = read_parts(path)
    if set(parts) != {"HEAD_MOTION_VECTORS", "HEAD_DEPTH"}:
        raise OrderCompositeError(f"head vectors {path.name}: parts {sorted(parts)} are not HEAD_MOTION_VECTORS + HEAD_DEPTH")
    for name, (pix, attrs, chans) in parts.items():
        if attrs.get("colorInteropID") != CONV["bundle_attributes"]["data_declaration"]["colorInteropID"]:
            raise OrderCompositeError(f"head vectors {path.name}: {name} is not declared 'data' — a reader must never colour-transform vectors or depth")
        if pix.shape[:2] != shape or not np.isfinite(pix).all():
            raise OrderCompositeError(f"head vectors {path.name}: {name} is {pix.shape[:2]} (bundle {shape}) or carries NaN/Inf")
    return parts


PROBE = CONV["skin_tone"]["probe"]


def skin_gain(bm, tone):
    """The order's body-skin re-tint — {gain, weight, probe_albedo} per channel (ADR-0002 amendment 2026-10-31) and the
    probe's frames {frame: sha256}, which compose_frame checks the probe file against — or None for 'master' (no re-tint).
    Refuses a tone the master cannot take: no recorded albedo, a skin a gain cannot describe, no skin probe, no PASS of the
    probe method written beside this very probe (skin_probe.gate_refusal; burst 6 review, 2026-11-01), outside the range."""
    if tone == "master":
        return None
    try:
        target = np.array([float(v) for v in tone.split(",")], np.float32)
    except ValueError:
        raise OrderCompositeError(f"--skin-tone {tone!r}: expected R,G,B scene-linear albedo or 'master'")
    st = bm["bundles"]["COMPOSITE_BUNDLE"]["derived"].get("skin_tone", {})
    if target.shape != (3,) or not st.get("master_albedo"):
        raise OrderCompositeError(f"--skin-tone {tone!r}: three channels needed, and the bundle must record the master's albedo (derived.skin_tone; contract v5)")
    if st.get("material_status") != "RE-TINTABLE":
        raise OrderCompositeError(f"the master's skin is {st.get('material_status')!r} — a gain cannot re-tint it (ADR-0002 amendment 2026-09-29)")
    probe = bm["bundles"].get(PROBE["bundle"], {}).get("probe")
    if not probe:
        raise OrderCompositeError(f"the bundle carries no {PROBE['bundle']} — the master's skin probe (slice/skin_probe.py derive); without it no tone "
                                  "but 'master' is re-tinted (ADR-0002 amendment 2026-10-31)")
    if not skin_probe.derived_by_current_rule(bm):
        raise OrderCompositeError(f"the bundle's {PROBE['bundle']} was derived by an older rule (its parts, edge or probe tone are not the conventions' "
                                  f"{PROBE['parts']}, {PROBE['edge']}, {PROBE['tone']}) — derive it again: slice/skin_probe.py derive --replace, then the gate")
    why = skin_probe.gate_refusal(bm)
    if why:
        raise OrderCompositeError(f"prerequisite gate: {why}")
    gate = bm["skin_tone"]
    lo, hi = np.array(gate["supported_range"]["min"], np.float32), np.array(gate["supported_range"]["max"], np.float32)
    if (target < lo - 1e-6).any() or (target > hi + 1e-6).any():
        raise OrderCompositeError(f"--skin-tone {target.tolist()} is outside the master's supported range {lo.tolist()}–{hi.tolist()} — a qualification reject (ADR-0002 D4), never clamped")
    try:
        gain, weight = skin_retint.gain_and_weight(target, st["master_albedo"], probe["albedo"])
    except skin_retint.SkinRetintError as e:
        raise OrderCompositeError(str(e)) from None
    return {"gain": gain, "weight": weight, "probe_albedo": probe["albedo"], "probe_frames": skin_probe.probe_frames(bm)}


def probe_file(rd, bm, frame):
    """The skin probe's frame of the bundle — required whenever the tone is re-tinted."""
    rows = {r["frame"]: r["file"] for r in bm["bundles"].get(PROBE["bundle"], {}).get("frames", [])}
    if frame not in rows:
        raise OrderCompositeError(f"frame {frame}: no {PROBE['bundle']} frame — the skin cannot be re-tinted without it")
    return Path(rd) / PROBE["bundle"] / rows[frame]


def compose_frame(frame, comp_path, derived_path, head_path, shadow_path, seam_ctx, head_mv_path=None, shutter_frames=0.0, reach_frames=None, tone=None,
                  silhouette_path=None, probe_path=None):
    comp = read_parts(comp_path)
    der = read_parts(derived_path)
    body, front, holdout = comp["BODY_BEAUTY"][0], der["PRECOMP_FRONT"][0], comp["HEAD_HOLDOUT"][0][..., 0]
    colour = comp["BODY_BEAUTY"][1].get("colorInteropID")
    if not colour:
        raise OrderCompositeError(f"{comp_path.name}: BODY_BEAUTY carries no colorInteropID")
    colour_attrs = {k: comp["BODY_BEAUTY"][1][k] for k in CONV["bundle_attributes"]["carried"] if k in comp["BODY_BEAUTY"][1]}
    head, hattrs = single_part(head_path, ["R", "G", "B", "A"], "head layer")
    if hattrs.get("colorInteropID") != colour:
        raise OrderCompositeError(f"head layer {head_path.name}: colorInteropID {hattrs.get('colorInteropID')!r} is not the bundle's {colour!r} — the head technology must declare its colour")
    shadow, sattrs = single_part(shadow_path, ["R", "G", "B"], "shadow multiply")
    if sattrs.get("colorInteropID") != CONV["bundle_attributes"]["data_declaration"]["colorInteropID"]:
        raise OrderCompositeError(f"shadow multiply {shadow_path.name}: colorInteropID {sattrs.get('colorInteropID')!r} is not 'data' — a factor must be declared as data so no reader transforms it")
    if head.shape[:2] != body.shape[:2] or shadow.shape[:2] != body.shape[:2]:
        raise OrderCompositeError(f"frame {frame}: sizes differ — bundle {body.shape[:2]}, head {head.shape[:2]}, shadow {shadow.shape[:2]}")
    slack = PO["gate"]["multiply_range_slack"]
    out_of_range = float(np.mean((shadow < -slack) | (shadow > 1 + slack)))
    m = np.clip(shadow, 0.0, 1.0)  # after the gate below: only half-ULP excess is ever clipped
    back = body.copy()
    if tone is not None:   # the order's skin tone between the master and its probe, before the shadow (ADR-0002 amendment 2026-10-31)
        if probe_path is None:
            raise OrderCompositeError(f"frame {frame}: the tone is re-tinted only with the master's skin probe — no probe frame given")
        want = tone.get("probe_frames", {}).get(frame)
        if want is None or skin_probe.sha256(probe_path) != want:   # the tone and the probe of one bundle (burst 6 review, finding 8)
            raise OrderCompositeError(f"frame {frame}: the probe file {Path(probe_path).name} is not the frame of the probe the tone was "
                                      f"computed from ({'no such frame' if want is None else want[:12]}) — the tone comes from skin_gain of the same bundle")
        pr = read_parts(probe_path)
        g, w = tone["gain"], tone["weight"]
        back = skin_retint.retint(back, der["SKIN_DIFFUSE_BACK"][0], g, w, *(pr[f"{n}_BACK"][0] for n in ("REST", "BOUNCE", "EDGE", "SHARED")))
        front = skin_retint.retint(front, der["SKIN_DIFFUSE_FRONT"][0], g, w, *(pr[f"{n}_FRONT"][0] for n in ("REST", "BOUNCE", "EDGE", "SHARED")))
    back[..., :3] *= m
    zone, rings = seam_zone_for(seam_ctx, frame, holdout.shape)
    blur = shutter_frames > 0
    carry = [back]
    if blur:
        require_blur_parts(comp, frame)
        back_vec, back_dep = layer_vd(comp, "BACK")
        carry += [back_vec, back_dep[..., None]]
    ext, seam_stats = seam_extend.extend(carry, holdout, zone, SE["extend_px"], SE["holdout_known_max"])
    back = ext[0]
    seam_stats["rings"] = rings
    blur_report = None
    if blur:
        hm = head_motion(head_mv_path, holdout.shape)
        hdep = hm["HEAD_DEPTH"][0]
        layers = [(front.astype(np.float32), *layer_vd(comp, "FRONT")),
                  (head.astype(np.float32), hm["HEAD_MOTION_VECTORS"][0].astype(np.float32), (hdep[..., 0] if hdep.ndim == 3 else hdep).astype(np.float32)),
                  (back.astype(np.float32), ext[1], ext[2][..., 0])]
        final, blur_report = motion_blur.blur(layers, shutter_frames, reach_frames)
        final = final.astype(np.float32)
    else:
        final = over(front, over(head, back)).astype(np.float32)
    ha = head[..., 3]
    if silhouette_path is None:          # the caller declared the order's head the default head: its silhouette IS HEAD_HOLDOUT
        silhouette = holdout
    else:
        sil, sattrs = single_part(silhouette_path, ["Y"], "head silhouette")
        if sattrs.get("colorInteropID") != CONV["bundle_attributes"]["data_declaration"]["colorInteropID"]:
            raise OrderCompositeError(f"head silhouette {Path(silhouette_path).name}: not declared 'data' — a matte is never colour-transformed")
        if sil.shape[:2] != holdout.shape:
            raise OrderCompositeError(f"head silhouette {Path(silhouette_path).name}: {sil.shape[:2]}, the bundle {holdout.shape}")
        silhouette = sil[..., 0]
    fill = head_fill(ha, silhouette, holdout, zone, edge_px=0 if silhouette_path is None else PO["gate"]["own_silhouette_edge_px"],
                     seam_edge_px=PO["gate"]["seam_edge_px"])
    metrics = {**fill, "multiply_out_of_range_fraction": out_of_range, "silhouette": "HEAD_HOLDOUT (the default head)" if silhouette_path is None else Path(silhouette_path).name,
               "holdout_px": int((holdout >= 0.5).sum()), "head_alpha_px": int((ha >= 0.5).sum()), "seam_extend": seam_stats}
    if blur_report is not None:
        metrics["post_composite_blur"] = blur_report
    failed = [k for k, v in (("unfilled_fraction", fill["unfilled_fraction"]), ("seam_unfilled_fraction", fill["seam_unfilled_fraction"]),
                             ("multiply_out_of_range_fraction", out_of_range)) if v is not None and v > PO["gate"][f"{k}_max"]]
    return final, colour, colour_attrs, metrics, failed


def same_picture(final, reference_exr):
    """FINAL, as written (half), against a picture the QC path made from the same inputs (the blur gate's blurred default
    head, half): the two differ only by the half quantization of the inputs the per-order path reads (the precomp pair,
    the multiply, the head layer), so the rule is in half steps, not an absolute 1e-3 — at scene-linear 2-16 one half
    step is already 2e-3-8e-3 (measured 2026-09-29, SHOT_001 v02: every pixel within 2 steps)."""
    ref = next(iter(read_parts(reference_exr).values()))[0].astype(np.float32)
    fin = final.astype(np.float16).astype(np.float32)
    err = np.abs(fin - ref).max(-1)
    step = np.spacing(np.maximum(np.abs(ref).max(-1), 6.1e-5).astype(np.float16)).astype(np.float32)
    return {"reference": reference_exr.name, "within_2_half_steps": float((err <= 2 * step).mean()), "max_abs_error": float(err.max()),
            "max_relative_error": float((err / np.maximum(np.abs(ref).max(-1), 1e-3)).max())}


def reproduction_vs_default(final, comp_path):
    """FINAL against DEFAULT_HEAD_BEAUTY with the precomp-reproduction band rule — meaningful
    only when the inputs are the default head's own layer and multiply (QC baseline)."""
    from slice.matte_metrics import edge_band
    comp = read_parts(comp_path)
    full = comp["DEFAULT_HEAD_BEAUTY"][0]
    hold = comp["HEAD_HOLDOUT"][0][..., 0]
    fg = comp["FOREGROUND_PLATE"][0][..., 3]
    band_px = CONV["compositor"]["precomp_reproduction_test"]["boundary_band_px"]
    err = np.abs(final[..., :3] - full[..., :3]).max(-1)
    band = edge_band(hold > 0.5, band_px) | edge_band(fg > 0.5, band_px)
    return {"outside_band_within_1e-3": float((err[~band] <= 1e-3).mean()), "inside_band_within_5e-2": float((err[band] <= 5e-2).mean()) if band.any() else None,
            "max_abs_error": float(err.max()), "band_fraction": float(band.mean())}


def compose(args):
    rd, bm_path, bm, comp_rows, derived_rows = load_bundle(args.bundle)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = parse_frames(args.frames, sorted(comp_rows))
    head_dir, shadow_dir = Path(args.head_layer), Path(args.shadow_multiply)
    rm = json.loads((rd / bm["source_render_manifest"]).read_text())
    st = rm["settings"]
    shutter_frames = st["shutter_angle_deg"] / 360.0
    reach_frames = vector_reach(st, shutter_frames, bm["source_render_manifest"]) if shutter_frames else None
    if shutter_frames and not args.head_vectors:
        raise OrderCompositeError(f"{bm['profile']}: the shutter is open ({st['shutter_angle_deg']}°) — the head's own vectors and depth are required (--head-vectors); the blur is never skipped")
    if not shutter_frames and args.head_vectors:
        raise OrderCompositeError(f"{bm['profile']}: the shutter is closed — a still is not blurred, --head-vectors is not an input here")
    gain = skin_gain(bm, args.skin_tone)
    inputs = {}
    for frame in frames:
        wanted = [("head_layer", head_dir / f"head.{frame:04d}.exr"), ("shadow_multiply", shadow_dir / f"shadow.{frame:04d}.exr")]
        if args.head_vectors:
            wanted.append(("head_vectors", Path(args.head_vectors) / f"head_mv.{frame:04d}.exr"))
        if args.head_silhouette != "default-head":
            wanted.append(("head_silhouette", Path(args.head_silhouette) / f"head_silhouette.{frame:04d}.exr"))
        for what, p in wanted:
            if not p.exists():
                raise OrderCompositeError(f"frame {frame}: {what} {p} missing — no substitute exists for it")
            inputs[(frame, what)] = {"file": str(p), "sha256": sha256(p)}
    bundle_sha = sha256(bm_path)
    gate_sha = hashlib.sha256(json.dumps(PO["gate"], sort_keys=True).encode()).hexdigest()
    seam_sha = hashlib.sha256(json.dumps(SE, sort_keys=True).encode()).hexdigest()  # the operation's parameters change the frames
    blur_sha = hashlib.sha256(json.dumps(CONV["post_composite_blur"], sort_keys=True).encode()).hexdigest() if shutter_frames else "no blur"
    key_src = "|".join([args.order_id, bundle_sha, f"{frames[0]}-{frames[-1]}", gate_sha, seam_sha, blur_sha, f"record_default_head_reproduction={args.record_default_head_reproduction}", f"skin_tone={args.skin_tone}", f"head_silhouette={'default-head' if args.head_silhouette == 'default-head' else 'own'}"] + [inputs[k]["sha256"] for k in sorted(inputs)])
    seam_ctx = seam_context(rd, bm["profile"], rm["settings"]["resolution_percentage"])
    key = hashlib.sha256(key_src.encode()).hexdigest()
    prev_path = out / "order_composite_manifest.json"
    if prev_path.exists():
        prev = json.loads(prev_path.read_text())
        if prev.get("idempotency_key") == key and prev.get("status") == "PASS" and prev.get("gate") == PO["gate"] and all((out / f["file"]).exists() and sha256(out / f["file"]) == f["sha256"] for f in prev["frames"]):
            print(f"ORDER_COMPOSITE_OK {args.order_id} already composed with the same idempotency key ({key[:12]}), frames verified on disk — no-op")
            return
        if prev.get("idempotency_key") != key:
            raise OrderCompositeError(f"{out} holds order {prev.get('order_id')} with idempotency key {str(prev.get('idempotency_key'))[:12]} ≠ this run's {key[:12]} — one output directory per (order, bundle, frame range, gate, inputs); use another directory")
        # same key, previous FAIL / ERROR or frames missing: re-run from nothing — the old manifest
        # is kept under its status name (numbered, never overwritten) and every old frame removed
        n = 1
        while (out / f"order_composite_manifest.{prev.get('status', 'UNKNOWN').lower()}.previous{n}.json").exists():
            n += 1
        prev_path.rename(out / f"order_composite_manifest.{prev.get('status', 'UNKNOWN').lower()}.previous{n}.json")
        for old_frame in out.glob("final.*.exr"):
            old_frame.unlink()
    manifest = {"schema_note": "per-order composite manifest; conventions.json → compositor.per_order", "order_id": args.order_id,
                "idempotency_key": key, "idempotency_key_rule": "sha256(order_id | bundle_manifest sha256 | frame range | gate sha256 | seam_extend sha256 | post_composite_blur sha256 (video) | record flag | skin tone | every input sha256 in order); a re-run with the same key over a PASS is a verified no-op, a different key in the same directory is refused",
                "shot_id": bm["shot_id"], "profile": bm["profile"], "smoke_test_only": bm["smoke_test_only"],
                "bundle_manifest": {"file": str(bm_path), "sha256": bundle_sha}, "formula": PO["formula"], "seam_extend": SE,
                "gate": PO["gate"], "post_composite_blur": {"shutter_frames": shutter_frames, "vector_reach_frames": reach_frames, "applied": bool(shutter_frames)},
                "skin_tone": {"requested": args.skin_tone, "gain": None if gain is None else [round(float(g), 6) for g in gain["gain"]],
                              "weight": None if gain is None else [round(float(v), 6) for v in gain["weight"]],
                              "probe_albedo": None if gain is None else gain["probe_albedo"], "method": None if gain is None else "probe",
                              "probe_bundle_sha256": None if gain is None else bm["skin_tone"]["probe_bundle_sha256"],
                              "master_albedo": bm["bundles"]["COMPOSITE_BUNDLE"]["derived"].get("skin_tone", {}).get("master_albedo"),
                              "supported_range": bm.get("skin_tone", {}).get("supported_range"), "applied": gain is not None},
                "fallbacks": [], "frames": [], "status": "RUNNING"}
    staging = out / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        for frame in frames:
            t0, c0 = time.perf_counter(), time.process_time()
            comp_path = rd / "COMPOSITE_BUNDLE" / comp_rows[frame]["file"]
            derived_path = rd / "COMPOSITE_BUNDLE" / derived_rows[frame]["file"]
            head_path, shadow_path = Path(inputs[(frame, "head_layer")]["file"]), Path(inputs[(frame, "shadow_multiply")]["file"])
            mv_path = Path(inputs[(frame, "head_vectors")]["file"]) if (frame, "head_vectors") in inputs else None
            sil_path = Path(inputs[(frame, "head_silhouette")]["file"]) if (frame, "head_silhouette") in inputs else None
            pr_path = probe_file(rd, bm, frame) if gain is not None else None
            final, colour, colour_attrs, metrics, failed = compose_frame(frame, comp_path, derived_path, head_path, shadow_path, seam_ctx, mv_path, shutter_frames, reach_frames, gain,
                                                                         silhouette_path=sil_path, probe_path=pr_path)
            if args.record_default_head_reproduction:
                note = "the QC baseline with the default head's own layer, multiply and vectors — for any other head this compares two different heads"
                if shutter_frames:
                    qc = derived_rows[frame].get("post_composite_blur", {}).get("file")
                    if not qc:
                        raise OrderCompositeError(f"frame {frame}: the bundle has no QC-path blurred frame to compare the blurred FINAL with")
                    metrics["vs_qc_blurred_default_head"] = {**same_picture(final, rd / "COMPOSITE_BUNDLE" / qc), "meaningful_only_for": note}
                else:
                    metrics["vs_default_head_beauty"] = {**reproduction_vs_default(final, comp_path), "meaningful_only_for": note}
            if failed:
                manifest["status"] = "FAIL"
                manifest["failed"] = {"frame": frame, "metrics": failed, "values": metrics, "thresholds": {k: PO["gate"][f"{k}_max"] for k in failed}}
                raise OrderCompositeError(f"order {args.order_id} frame {frame}: gate FAIL on {failed}: {metrics} (thresholds {manifest['failed']['thresholds']})")
            dst = staging / f"final.{frame:04d}.exr"
            write_parts(dst, [("FINAL", final, ["R", "G", "B", "A"], "half", "PREMULTIPLIED")], colour_attrs)
            w = read_parts(dst)["FINAL"]
            if not np.array_equal(w[0], final.astype(np.float16).astype(np.float32)) or w[1].get("colorInteropID") != colour:
                raise OrderCompositeError(f"{dst.name}: re-read differs from the computed frame")
            t_comp = {"wall_s": round(time.perf_counter() - t0, 3), "cpu_s": round(time.process_time() - c0, 3)}
            manifest["frames"].append({"frame": frame, "file": dst.name, "sha256": sha256(dst), "bytes": dst.stat().st_size,
                                       "t_comp": t_comp, "master_bytes_read": comp_path.stat().st_size + derived_path.stat().st_size + (pr_path.stat().st_size if pr_path else 0),
                                       "inputs": {"composite": {"file": comp_path.name, "sha256": comp_rows[frame]["sha256"]}, "derived": {"file": derived_path.name, "sha256": derived_rows[frame]["sha256"]},
                                                  "head_layer": inputs[(frame, "head_layer")], "shadow_multiply": inputs[(frame, "shadow_multiply")]},
                                       "metrics": metrics, "status": "PASS"})
            blur_txt = f" blur K={metrics['post_composite_blur']['samples']} {metrics['post_composite_blur']['seconds']}s" if "post_composite_blur" in metrics else ""
            print(f"ORDER_FRAME {frame} PASS unfilled={metrics['unfilled_fraction']:.5f} seam_unfilled={metrics['seam_unfilled_fraction']} beyond_default={metrics['beyond_default_silhouette_fraction']:.5f} multiply_oor={metrics['multiply_out_of_range_fraction']:.5f} t_comp={t_comp['wall_s']:.2f}s{blur_txt}")
        for f in sorted(staging.glob("final.*.exr")):
            f.rename(out / f.name)
        staging.rmdir()
        manifest["status"] = "PASS"
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if manifest["status"] == "RUNNING":
            manifest["status"] = "ERROR"
        for f in manifest["frames"]:
            f["status"] = "STAGED_THEN_DISCARDED"  # computed, never delivered: staging is removed on failure
        manifest["frames_written"] = []
        (out / "order_composite_manifest.json").write_text(json.dumps(manifest, indent=1, allow_nan=False) + "\n")
        raise
    (out / "order_composite_manifest.json").write_text(json.dumps(manifest, indent=1, allow_nan=False) + "\n")
    print(f"ORDER_COMPOSITE_OK {args.order_id} {len(frames)} frames idempotency_key={manifest['idempotency_key'][:12]} -> {out}")


def default_head_inputs(args):
    """Write the default head's own layer (raw L_HEAD.Combined), its HEAD_SHADOW_MULTIPLY and, when the bundle carries
    them (video), its own vectors and depth (HEAD_MOTION_VECTORS, HEAD_DEPTH) in the per-order input layout, so the
    entry point can be run against the master's own head."""
    rd, bm_path, bm, comp_rows, derived_rows = load_bundle(args.bundle)
    rm = json.loads((rd / bm["source_render_manifest"]).read_text())
    raw_by_frame = {row["frame"]: rd / "raw" / row["files"]["beauty"]["file"] for row in rm["frames"]}
    out = Path(args.out)
    (out / "head").mkdir(parents=True, exist_ok=True)
    (out / "shadow").mkdir(parents=True, exist_ok=True)
    for frame in sorted(comp_rows):
        raw = read_parts(raw_by_frame[frame])
        comp = read_parts(rd / "COMPOSITE_BUNDLE" / comp_rows[frame]["file"])
        der = read_parts(rd / "COMPOSITE_BUNDLE" / derived_rows[frame]["file"])
        colour = {k: comp["BODY_BEAUTY"][1][k] for k in CONV["bundle_attributes"]["carried"] if k in comp["BODY_BEAUTY"][1]}
        write_parts(out / "head" / f"head.{frame:04d}.exr", [("HEAD_LAYER", raw["L_HEAD.Combined"][0].astype(np.float32), ["R", "G", "B", "A"], "half", "PREMULTIPLIED")], colour)
        write_parts(out / "shadow" / f"shadow.{frame:04d}.exr", [("SHADOW_MULTIPLY", der["HEAD_SHADOW_MULTIPLY"][0].astype(np.float32), ["R", "G", "B"], "half", "NOT_APPLICABLE")], colour)
        if "HEAD_MOTION_VECTORS" in comp:
            (out / "head_mv").mkdir(exist_ok=True)
            vec, vattrs, vch = comp["HEAD_MOTION_VECTORS"]
            dep, dattrs, dch = comp["HEAD_DEPTH"]
            write_parts(out / "head_mv" / f"head_mv.{frame:04d}.exr", [("HEAD_MOTION_VECTORS", vec.astype(np.float32), vch, "float", "NOT_APPLICABLE"),
                                                                       ("HEAD_DEPTH", dep.astype(np.float32), dch, "float", "NOT_APPLICABLE")], colour)
    print(f"DEFAULT_HEAD_INPUTS_OK {len(comp_rows)} frames -> {out}")


def main(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compose")
    c.add_argument("--bundle", required=True)
    c.add_argument("--head-layer", required=True)
    c.add_argument("--shadow-multiply", required=True)
    c.add_argument("--skin-tone", required=True, help="the order's body-skin albedo R,G,B (scene-linear), or 'master' for the QC baseline (no re-tint)")
    c.add_argument("--head-vectors", default=None, help="<dir>/head_mv.####.exr — the head's own vectors and depth; required when the shutter is open (video)")
    c.add_argument("--head-silhouette", required=True, help="'default-head' (the order's head IS the default head: its silhouette is HEAD_HOLDOUT) or <dir>/head_silhouette.####.exr — "
                   "the order head's own coverage as L_HEAD sees it (bakeoff/metrics/extract_geometry.py mattes); the gate holds the head layer to it (ADR-0002 amendment 2026-10-30)")
    c.add_argument("--order-id", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--frames", default=None)
    c.add_argument("--record-default-head-reproduction", action="store_true", help="QC baseline runs only: record FINAL vs DEFAULT_HEAD_BEAUTY (fraction within 1e-3 outside the 2-px band, max abs error) per frame")
    d = sub.add_parser("default-head-inputs")
    d.add_argument("--bundle", required=True)
    d.add_argument("--out", required=True)
    args = p.parse_args(argv)
    (compose if args.cmd == "compose" else default_head_inputs)(args)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(argv)
    except (OrderCompositeError, OSError, ValueError, KeyError) as e:
        print(f"ORDER_COMPOSITE_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
