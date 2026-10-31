"""SKIN_PROBE_BUNDLE — the master's second render for the order's skin tone (ADR-0002 amendment 2026-10-31). Blender's
Python (OpenImageIO):

    blender -b <shot.blend> --python-exit-code 2 -P slice/skin_probe.py -- set-tone --tone R,G,B --out <copy.blend>
    blender -b --python-exit-code 2 -P slice/skin_probe.py -- derive <master renders/<profile>> <probe renders/<profile>>

set-tone — a copy of the shot file with every hero skin material (conventions → skin_tone.materials_toned) at the tone:
the probe's file, and the skin-tone gate's truths. A material that is missing, has no Principled BSDF or a textured base
colour is refused: a tone cannot be set on it.

derive — per frame of the master's bundles, the probe render (render_passes.py --skin-probe) against the master's
BODY_BEAUTY / FOREGROUND_PLATE and SKIN_BUNDLE: REST and BOUNCE of each layer (slice/skin_retint.probe_parts), written to
<master>/SKIN_PROBE_BUNDLE/skin_probe.####.exr and recorded in the master's bundle manifest (bundles.SKIN_PROBE_BUNDLE:
the frames with their pixel hashes, the probe's albedo and render). The probe is quantised to half as the master's
bundles are before the difference. Refused: a render that is not a skin probe, misses a frame of the master's, is not at
the conventions' probe tone in every toned material, was rendered with other settings than the master's, or whose
direct light on the skin is not the master's; an existing SKIN_PROBE_BUNDLE without --replace."""
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
    if out.exists():
        if not replace:
            raise SkinProbeError(f"{out} exists — derived once; --replace to derive it again")
        shutil.rmtree(out)
    out.mkdir()
    q = lambda a: quantize(np.asarray(a, np.float32), "half").astype(np.float32)  # noqa: E731
    mat = ST["material_body"]
    rows, worst = [], 0.0
    for frame in sorted(comp):
        mp, ms = read_parts(mdir / "COMPOSITE_BUNDLE" / comp[frame]), read_parts(mdir / "SKIN_BUNDLE" / skin[frame])
        pr = read_parts(pdir / "raw" / prows[frame]["files"]["skin_probe"]["file"])
        parts, mismatch = [], {}
        for layer, plate, raw, side in (("BODY", "BODY_BEAUTY", "L_BODY", "BACK"), ("FRONT", "FOREGROUND_PLATE", "L_FG", "FRONT")):
            m = layer_skin(ms, layer, mat)
            shape = mp[plate][0].shape[:2]
            if m is None:
                rest = bounce = np.zeros((*shape, 3), np.float32)
                mismatch[side] = None
            else:
                S = lambda n: ms[f"{layer}_{n}"][0][..., :3].astype(np.float32)  # noqa: E731
                R = lambda n: q(pr[f"{raw}.{n}"][0][..., :3])  # noqa: E731
                d_m, d_p = S("DIFFUSE_DIRECT"), R("Diffuse Direct")
                mismatch[side] = sr.direct_mismatch(m, d_m, d_p)
                rest, bounce = sr.probe_parts(m, S("DIFFUSE_COLOR"), d_m, S("DIFFUSE_INDIRECT"), mp[plate][0].astype(np.float32),
                                              R("Diffuse Color"), d_p, R("Diffuse Indirect"), q(pr[f"{raw}.Combined"][0]))
            parts += [(f"REST_{side}", rest, ["R", "G", "B"], "half", "NOT_APPLICABLE"),
                      (f"BOUNCE_{side}", bounce, ["R", "G", "B"], "half", "NOT_APPLICABLE")]
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
        worst = max([worst] + [v for v in mismatch.values() if v is not None])
        rows.append({"frame": frame, "file": dst.name, "bytes": dst.stat().st_size, "sha256": sha256(dst), "parts": prow,
                     "direct_light_mismatch": mismatch})
    sizes = [r["bytes"] for r in rows]
    bm["bundles"][P["bundle"]] = {
        "read_granularity": "per-frame", "consumer": "the per-order skin re-tint (slice/composite_order.py) and the skin-tone gate",
        "rule": "ADR-0002 amendment 2026-10-31 — slice/skin_retint.py", "frames": rows,
        "bytes_per_frame": {"min": min(sizes), "max": max(sizes), "mean": sum(sizes) / len(sizes),
                            "measured_on": bm["bundles"]["COMPOSITE_BUNDLE"]["bytes_per_frame"]["measured_on"]},
        "probe": {"albedo": tone, "master_albedo": sm["base_color"], "materials_toned": ST["materials_toned"],
                  "render_manifest": {"file": pman_path.name, "sha256": sha256(pman_path)}, "source_scene": pman["source_scene"],
                  "direct_light_mismatch_max": worst, "direct_light_match_max": P["direct_light_match_max"]}}
    bm_path.write_text(json.dumps(bm, indent=1) + "\n")
    print(f"SKIN_PROBE_OK {profile} {len(rows)} frames, probe {tone}, direct light within {worst:.2e} of the master's -> {out}")


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
