"""SKIN_PROBE_BUNDLE — the master's second render for the order's skin tone (ADR-0002 amendment 2026-10-31). Blender's
Python (OpenImageIO):

    blender -b <shot.blend> --python-exit-code 2 -P slice/skin_probe.py -- set-tone --tone R,G,B --out <copy.blend>
    blender -b --python-exit-code 2 -P slice/skin_probe.py -- derive <master renders/<profile>> <probe renders/<profile>>

set-tone — a copy of the shot file with every hero skin material (conventions → skin_tone.materials_toned) at the tone:
the probe's file, and the skin-tone gate's truths. A material that is missing, has no Principled BSDF or a textured base
colour is refused: a tone cannot be set on it.

derive — per frame of the master's bundles, the probe render (render_passes.py --skin-probe) against the master's
BODY_BEAUTY / FOREGROUND_PLATE and SKIN_BUNDLE: REST and BOUNCE of each layer (slice/skin_retint.probe_parts), and EDGE and
SHARED — the pixels the skin shares with another surface and their own change (slice/skin_retint.edge_parts; owner
2026-11-01, decision 13 (A)) — written to <master>/SKIN_PROBE_BUNDLE/skin_probe.####.exr and recorded in the master's
bundle manifest (bundles.SKIN_PROBE_BUNDLE: the frames with their pixel hashes and shared pixel counts, the probe's albedo
and render, the edge's thresholds). The probe is quantised to half as the master's bundles are before the difference.
Refused: a render that is not a skin probe, misses a frame of the master's, is not at the conventions' probe tone in
every toned material, was rendered with other settings than the master's, or whose direct light inside the skin is not
the master's within direct_light_z_max sampling-noise units (or cannot be measured on any layer of any frame, or of a
chunk with skin: unmeasured_chunks); an existing SKIN_PROBE_BUNDLE without --replace. The bundle is written beside as
SKIN_PROBE_BUNDLE.partial and put in place only whole: a derive that fails leaves the bundle that was there. A bundle
derived by an older rule (derived_by_current_rule) is used by no order and no gate: derive it again with --replace. A
derive moves the bundle's skin-tone gate record to `skin_tone_retired`: it vouched for the probe that was there
(gate_refusal; burst 6 review Q79-1, 2026-11-01)."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
ST = CONV["skin_tone"]
P = ST["probe"]


class SkinProbeError(RuntimeError):
    pass


def parse_tone(text):
    try:
        tone = [float(v) for v in text.split(",")]
    except ValueError:
        raise SkinProbeError(f"--tone {text!r}: expected R,G,B scene-linear albedo") from None
    if len(tone) != 3 or not all(0.0 < v <= 1.0 for v in tone):
        raise SkinProbeError(f"--tone {text!r}: three channels in (0, 1]")
    return tone


def set_tone(tone, out):
    import bpy
    for name in ST["materials_toned"]:
        m = bpy.data.materials.get(name)
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m is not None and m.use_nodes else None
        if b is None:
            raise SkinProbeError(f"{name}: {'missing' if m is None else 'no Principled BSDF'} — a tone cannot be set on it")
        if b.inputs["Base Color"].is_linked:
            raise SkinProbeError(f"{name}: the base colour is textured — a tone cannot be set on it (ADR-0002 amendment 2026-09-29 §Does not solve)")
        b.inputs["Base Color"].default_value = (*tone, 1.0)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True, copy=True)
    print(f"TONE_SET {tone} on {', '.join(ST['materials_toned'])} -> {out}")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _same(a, b):
    return a is not None and b is not None and len(a) == len(b) == 3 and all(abs(float(x) - float(y)) <= 1e-6 for x, y in zip(a, b))


def derived_by_current_rule(bm):
    """Whether the bundle manifest's SKIN_PROBE_BUNDLE was derived by the conventions' rule as it is now: every frame of
    the conventions' parts, the edge found by the conventions' thresholds (a bundle derived before the edge, 2026-11-01,
    is not), the probe at the conventions' tone."""
    b = bm.get("bundles", {}).get(P["bundle"])
    if not b or not b.get("frames"):
        return False
    pr = b.get("probe", {})
    return (pr.get("edge") == P["edge"] and _same(pr.get("albedo"), P["tone"])
            and all([q["name"] for q in r["parts"]] == P["parts"] for r in b["frames"]))


def probe_fingerprint(bm):
    """The bundle's SKIN_PROBE_BUNDLE as one sha256 — its probe and master albedos and every frame's file sha256, the rows
    in frame order — or None without one. The skin-tone gate's record carries the fingerprint of the probe it was written
    beside (check_skin_tone.record_in_bundles); an order re-tints only when it is the bundle's (gate_refusal)."""
    b = bm.get("bundles", {}).get(P["bundle"])
    if not b or not b.get("frames"):
        return None
    t = {"albedo": b.get("probe", {}).get("albedo"), "master_albedo": b.get("probe", {}).get("master_albedo"),
         "frames": [[r["frame"], r.get("sha256")] for r in sorted(b["frames"], key=lambda r: r["frame"])]}
    return hashlib.sha256(json.dumps(t, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def probe_frames(bm):
    """{frame: the probe frame file's sha256} — what composite_order.compose_frame checks the file it reads against."""
    return {r["frame"]: r["sha256"] for r in bm.get("bundles", {}).get(P["bundle"], {}).get("frames", [])}


def gate_refusal(bm):
    """Why the bundle's skin-tone gate does not admit a re-tint by its SKIN_PROBE_BUNDLE — None when it does: a PASS of the
    probe method written beside this very probe (its fingerprint, its probe and master albedos the bundle's). A VACUOUS
    gate admits nothing: derive refuses a render without measurable skin, so beside a probe VACUOUS is skin the gate did
    not measure (burst 6 review, Q79-1 and finding 5, 2026-11-01)."""
    gate = bm.get("skin_tone", {})
    if gate.get("status") != "PASS" or gate.get("method") != "probe":
        return (f"the skin-tone gate is {gate.get('status', 'NOT RUN')!r} by method {gate.get('method') or 'first order'!r} on this "
                "bundle — only a PASS of the probe method admits a re-tint (slice/check_skin_tone.py; VACUOUS: gate more frames)")
    pr = bm.get("bundles", {}).get(P["bundle"], {}).get("probe", {})
    if gate.get("probe_bundle_sha256") != probe_fingerprint(bm):
        return (f"the skin-tone gate's record was written beside another {P['bundle']} (its fingerprint "
                f"{str(gate.get('probe_bundle_sha256'))[:12]}, the bundle's {str(probe_fingerprint(bm))[:12]}) — the probe was derived "
                "again after the gate: run the gate again on this one")
    if not _same(gate.get("probe_albedo"), pr.get("albedo")) or not _same(gate.get("master_albedo"), pr.get("master_albedo")):
        return (f"the skin-tone gate measured the probe albedo {gate.get('probe_albedo')} over the master's {gate.get('master_albedo')}, "
                f"the bundle's probe is {pr.get('albedo')} over {pr.get('master_albedo')}")
    return None


def retire_gate_record(bm, why):
    """The gate's record moved to `skin_tone_retired` (kept, never dropped): the probe it was written beside is replaced."""
    if "skin_tone" in bm:
        bm.setdefault("skin_tone_retired", []).append(dict(bm.pop("skin_tone"), retired=why))


def material_status(sss, textured, base_color, toned, toned_sss):
    """RE-TINTABLE, or why not: the body's skin a plain colour without subsurface scattering (ADR-0002 amendment
    2026-09-29), and every hero skin material the probe tones (materials_toned) of that same colour, untextured, without
    subsurface — the probe sets them all to one tone, so light the head throws on the body is weighted by the body's
    albedo (burst 6 review finding 7, 2026-11-01). slice/render_passes.py records it in every render manifest."""
    if textured or sss != 0.0:
        return "NOT RE-TINTABLE BY A GAIN (textured base colour or subsurface — re-measure, ADR-0002 amendment 2026-09-29 §Does not solve)"
    off = sorted(k for k in ST["materials_toned"] if not _same(toned.get(k) if isinstance(toned.get(k), list) else None, base_color)
                 or toned_sss.get(k) != 0.0)
    if off:
        return (f"NOT RE-TINTABLE BY A GAIN ({', '.join(off)}: not the body skin's plain colour without subsurface — the probe tones "
                "every hero skin material alike; burst 6 review finding 7)")
    return "RE-TINTABLE"


def unmeasured_chunks(rows, chunks):
    """The chunks of the probe render (its manifest's assembled_from_chunks; a render without them is one chunk) whose
    frames show skin and measure none of it — the guard cannot tell such a chunk from another render, a frame off or an
    older light (burst 6 review Q79-3, 2026-11-01). A chunk with no skin re-tints nothing."""
    frames = sorted(r["frame"] for r in rows)
    chunks = chunks or [{"chunk": f"{frames[0]}-{frames[-1]}", "frames": [frames[0], frames[-1]]}] if frames else []
    out = []
    for c in chunks:
        a, b = c["frames"]
        vals = [v for r in rows if a <= r["frame"] <= b for v in r["direct_light_mismatch"].values()]
        if any(v != "NO_SKIN" for v in vals) and not any(isinstance(v, float) for v in vals):
            out.append(c["chunk"])
    return out


def has_skin(m):
    """A layer has skin when its cryptomatte carries the material (m is not None) and a pixel is more skin than not —
    the gate's visible skin; a front plate that carries the material and shows none has no skin."""
    return m is not None and bool((m > 0.5).any())


def derive(master_dir, probe_dir, replace=False):
    import numpy as np
    from slice import skin_retint as sr
    from slice.composite import read_parts, write_parts, layer_skin
    from slice.split_bundles import pixel_sha1, quantize
    mdir, pdir = Path(master_dir), Path(probe_dir)
    profile = mdir.name
    mman = json.loads((mdir / f"render_manifest.{profile}.json").read_text())
    pman_path = pdir / f"render_manifest.{profile}.json"
    pman = json.loads(pman_path.read_text())
    bm_path = mdir / f"bundle_manifest.{profile}.json"
    bm = json.loads(bm_path.read_text())
    if pman.get("kind") != "skin_probe":
        raise SkinProbeError(f"{pman_path}: kind {pman.get('kind')!r} — not a skin probe render (render_passes.py --skin-probe)")
    if mman.get("kind", "plates") != "plates":
        raise SkinProbeError(f"{mdir}: kind {mman.get('kind')!r} — the master's plates are what the probe is set against")
    sm, sp = mman.get("skin_material", {}), pman.get("skin_material", {})
    if sm.get("status") != "RE-TINTABLE":
        raise SkinProbeError(f"the master's skin is {sm.get('status', 'NOT RECORDED')!r} — a gain cannot re-tint it")
    tone = [round(float(v), 6) for v in P["tone"]]
    toned = sp.get("materials_toned", {})
    off = {k: v for k, v in toned.items() if v != tone}
    if sorted(toned) != sorted(ST["materials_toned"]) or off:
        raise SkinProbeError(f"the probe's hero skin is {toned or 'NOT RECORDED'}, the conventions' probe tone {tone} on {ST['materials_toned']}")
    diff = sorted(k for k in set(mman["settings"]) | set(pman["settings"]) if mman["settings"].get(k) != pman["settings"].get(k))
    if diff:
        raise SkinProbeError(f"the probe was rendered with other settings than the master's: {diff}")
    sr.gain_and_weight(tone, sm["base_color"], tone)          # refuses a probe at the master's albedo in any channel
    prows = {r["frame"]: r for r in pman["frames"]}
    comp = {r["frame"]: r["file"] for r in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]}
    skin = {r["frame"]: r["file"] for r in bm["bundles"]["SKIN_BUNDLE"]["frames"]}
    missing = sorted(set(comp) - set(prows))
    if missing:
        raise SkinProbeError(f"the probe render lacks the master's frames {missing[:10]}{' …' if len(missing) > 10 else ''}")
    out = mdir / P["bundle"]
    if out.exists() and not replace:
        raise SkinProbeError(f"{out} exists — derived once; --replace to derive it again")
    work = mdir / f"{P['bundle']}.partial"                  # written here, put in place only whole
    if work.exists():
        shutil.rmtree(work)                                  # a derive that died half way
    work.mkdir()
    try:
        scale = mman["settings"]["resolution_percentage"] / 100.0
        rows, worst, measured, with_skin = _derive_frames(np, sr, read_parts, write_parts, layer_skin, pixel_sha1, quantize,
                                                          mdir, pdir, comp, skin, prows, work, scale, sm["base_color"], tone)
        if not measured:
            raise SkinProbeError(f"no layer of any frame has skin interior enough to measure the probe's direct light on "
                                 f"(conventions → skin_tone.probe.direct_light_interior) — the probe cannot be told from another render")
        blind = unmeasured_chunks(rows, pman.get("assembled_from_chunks"))
        if blind:
            raise SkinProbeError(f"the probe render's chunks {blind} show skin and measure none of it (conventions → "
                                 f"skin_tone.probe.direct_light_interior) — such a chunk cannot be told from another render")
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    if out.exists():
        shutil.rmtree(out)
    work.rename(out)
    before = probe_fingerprint(bm)
    retire_gate_record(bm, f"{P['bundle']} derived again (the record's was {str(before)[:12]}) — the gate runs again on the new one")
    sizes = [r["bytes"] for r in rows]
    bm["bundles"][P["bundle"]] = {
        "read_granularity": "per-frame", "consumer": "the per-order skin re-tint (slice/composite_order.py) and the skin-tone gate",
        "rule": "ADR-0002 amendment 2026-10-31, amended 2026-11-01 (the edge) — slice/skin_retint.py", "frames": rows,
        "bytes_per_frame": {"min": min(sizes), "max": max(sizes), "mean": sum(sizes) / len(sizes),
                            "measured_on": bm["bundles"]["COMPOSITE_BUNDLE"]["bytes_per_frame"]["measured_on"]},
        "probe": {"albedo": tone, "master_albedo": sm["base_color"], "materials_toned": ST["materials_toned"],
                  "render_manifest": {"file": pman_path.name, "sha256": sha256(pman_path)}, "source_scene": pman["source_scene"],
                  "direct_light_z_worst": worst, "direct_light_z_max": P["direct_light_z_max"],
                  "direct_light_interior": P["direct_light_interior"], "direct_light_grain_px": list(sr.grain(scale)),
                  "direct_light_measured_layers": measured,
                  "direct_light_layers_with_skin": with_skin, "edge": P["edge"]}}
    bm_path.write_text(json.dumps(bm, indent=1) + "\n")
    print(f"SKIN_PROBE_OK {profile} {len(rows)} frames, probe {tone}, direct light within {worst:.2f} noise units of the master's inside the skin "
          f"({measured} of {with_skin} layers with skin measured), {sum(sum(r['edge_px'].values()) for r in rows)} shared edge px -> {out}")


def _derive_frames(np, sr, read_parts, write_parts, layer_skin, pixel_sha1, quantize, mdir, pdir, comp, skin, prows, out, scale,
                   master_albedo, probe_albedo):
    """Every frame's REST, BOUNCE, EDGE and SHARED written into `out`: (rows, the worst direct-light mismatch, layers
    measured, layers with skin — a pixel more skin than not)."""
    q = lambda a: quantize(np.asarray(a, np.float32), "half").astype(np.float32)  # noqa: E731
    mat = ST["material_body"]
    rows, worst, measured, with_skin = [], 0.0, 0, 0
    for frame in sorted(comp):
        mp, ms = read_parts(mdir / "COMPOSITE_BUNDLE" / comp[frame]), read_parts(mdir / "SKIN_BUNDLE" / skin[frame])
        pr = read_parts(pdir / "raw" / prows[frame]["files"]["skin_probe"]["file"])
        parts, mismatch, edge_px = [], {}, {}
        for layer, plate, raw, side in (("BODY", "BODY_BEAUTY", "L_BODY", "BACK"), ("FRONT", "FOREGROUND_PLATE", "L_FG", "FRONT")):
            m = layer_skin(ms, layer, mat)
            shape = mp[plate][0].shape[:2]
            if m is None:
                rest = bounce = edge = np.zeros((*shape, 3), np.float32)
                shared = np.zeros((*shape, 1), np.float32)
                mismatch[side] = "NO_SKIN"
            else:
                S = lambda n: ms[f"{layer}_{n}"][0][..., :3].astype(np.float32)  # noqa: E731
                R = lambda n: q(pr[f"{raw}.{n}"][0][..., :3])  # noqa: E731
                d_m, d_p = S("DIFFUSE_DIRECT"), R("Diffuse Direct")
                comb_m, comb_p = mp[plate][0].astype(np.float32), q(pr[f"{raw}.Combined"][0])
                mismatch[side] = sr.direct_mismatch(m, d_m, d_p, scale) if has_skin(m) else "NO_SKIN"
                rest, bounce = sr.probe_parts(m, S("DIFFUSE_COLOR"), d_m, S("DIFFUSE_INDIRECT"), comb_m,
                                              R("Diffuse Color"), d_p, R("Diffuse Indirect"), comb_p, scale)
                edge, shared = sr.edge_parts(m, S("DIFFUSE_COLOR"), comb_m, R("Diffuse Color"), comb_p, master_albedo, probe_albedo)
            edge_px[side] = int((shared > 0.5).sum())
            parts += [(f"REST_{side}", rest, ["R", "G", "B"], "half", "NOT_APPLICABLE"),
                      (f"BOUNCE_{side}", bounce, ["R", "G", "B"], "half", "NOT_APPLICABLE"),
                      (f"EDGE_{side}", edge, ["R", "G", "B"], "half", "NOT_APPLICABLE"),
                      (f"SHARED_{side}", shared, ["Y"], "half", "NOT_APPLICABLE")]
        names = [p[0] for p in parts]
        if names != P["parts"]:
            raise SkinProbeError(f"parts {names} != the conventions' {P['parts']}")
        dst = out / f"{P['file_stem']}.{frame:04d}.exr"
        write_parts(dst, parts, {})
        back = read_parts(dst)
        if list(back) != names:
            raise SkinProbeError(f"{dst.name}: parts {list(back)} written as {names}")
        prow = []
        for name, arr, chans, ptype, alpha in parts:
            w = back[name][0]
            if not np.array_equal(w, quantize(arr, ptype)):
                raise SkinProbeError(f"{dst.name}: {name} differs from what was written after {ptype} quantisation")
            prow.append({"name": name, "pixel_type": ptype, "channels": chans, "alpha": alpha, "pixel_sha1": pixel_sha1(w)})
        got = [v for v in mismatch.values() if isinstance(v, float)]   # None: skin without an interior block to measure
        worst = max([worst] + got)
        measured += len(got)
        with_skin += sum(1 for v in mismatch.values() if v != "NO_SKIN")
        rows.append({"frame": frame, "file": dst.name, "bytes": dst.stat().st_size, "sha256": sha256(dst), "parts": prow,
                     "direct_light_mismatch": mismatch, "edge_px": edge_px})
    return rows, worst, measured, with_skin


def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("set-tone")
    t.add_argument("--tone", required=True)
    t.add_argument("--out", required=True)
    d = sub.add_parser("derive")
    d.add_argument("master")
    d.add_argument("probe")
    d.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "set-tone":
        set_tone(parse_tone(a.tone), Path(a.out))
    else:
        derive(a.master, a.probe, a.replace)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(args)
    except (SkinProbeError, RuntimeError) as e:          # SkinRetintError, CompositeError, SplitError are RuntimeErrors
        print(f"SKIN_PROBE_ERROR {e}", file=sys.stderr)
        sys.exit(2)
