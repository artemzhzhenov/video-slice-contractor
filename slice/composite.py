"""Compositor script for one profile's COMPOSITE bundle — derives the passes the render cannot
produce directly and runs the precomp-reproduction test (ADR-0002 D5 rows 9, 10, 13;
§Validation criterion 3; conventions.json → compositor):

    blender -b --python-exit-code 2 -P slice/composite.py -- <pkg>/shots/SHOT_001/renders/<profile>

Runs under Blender's Python for its OpenImageIO + numpy; touches no scene. Per frame it reads
COMPOSITE_BUNDLE/composite.####.exr and writes COMPOSITE_BUNDLE/derived.####.exr (parts:
HEAD_SHADOW_MULTIPLY, SKIN_ID, SKIN_ID_HEAD, SKIN_ID_BODY, PRECOMP_BACK, PRECOMP_FRONT) and
precomp_report.####.json; then appends a "derived" section to bundle_manifest.<profile>.json.
Every derived value has a declared formula; nothing is clamped silently — the one clamp
(the multiply factor to [0, 1]) is part of its declared formula and the clipped fraction is
reported."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import OpenImageIO as oiio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice.cryptomatte import manifest_ids  # noqa: E402
from slice.matte_metrics import edge_band  # noqa: E402
from slice import motion_blur  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
CC = CONV["compositor"]
DERIVED = CC["derived"]


class CompositeError(RuntimeError):
    pass


def read_parts(path):
    """{part_name: (numpy HxWxC float32, {attr: value})} for every part of a multi-part EXR."""
    inp = oiio.ImageInput.open(str(path))
    if inp is None:
        raise CompositeError(f"cannot open {path}: {oiio.geterror()}")
    parts = {}
    i = 0
    while inp.seek_subimage(i, 0):
        spec = inp.spec()
        name = spec.getattribute("oiio:subimagename")
        if not name:
            raise CompositeError(f"{Path(path).name}: part {i} has no oiio:subimagename")
        pix = inp.read_image(i, 0, 0, spec.nchannels, oiio.FLOAT)
        attrs = {a.name: a.value for a in spec.extra_attribs}
        parts[name] = (np.asarray(pix, dtype=np.float32).reshape(spec.height, spec.width, spec.nchannels), attrs, list(spec.channelnames))
        i += 1
    inp.close()
    return parts


def write_parts(path, parts, colour_attrs):
    """parts: list of (name, array HxWxC, channel names, pixel_type 'half'|'float', alpha decl).
    colour_attrs: the working-space declaration carried from the source (conventions →
    bundles.carried_attributes) onto every written part."""
    specs = []
    for name, arr, chans, ptype, alpha in parts:
        h, w, c = arr.shape
        spec = oiio.ImageSpec(w, h, c, oiio.HALF if ptype == "half" else oiio.FLOAT)
        spec.channelnames = chans
        spec.attribute("oiio:subimagename", name)
        spec.attribute("slice:pass", name)
        spec.attribute("slice:alpha", alpha)
        spec.attribute("compression", CONV["exr"]["compression"])
        # Colour rule (conventions → bundle_attributes.colour_rule): scene-linear only for
        # premultiplied colour; mattes, ids and factors are 'data' like Blender's own data passes.
        decl = CONV["bundle_attributes"]["data_declaration"] if alpha == "NOT_APPLICABLE" else colour_attrs
        for k, v in decl.items():
            spec.attribute(k, v)
        specs.append(spec)
    out = oiio.ImageOutput.create(str(path))
    if out is None:
        raise CompositeError(f"cannot create {path}: {oiio.geterror()}")
    if not out.open(str(path), specs):
        raise CompositeError(f"open failed: {out.geterror()}")
    for i, (name, arr, chans, ptype, alpha) in enumerate(parts):
        if i > 0 and not out.open(str(path), specs[i], "AppendSubimage"):
            raise CompositeError(f"append failed at {name}: {out.geterror()}")
        if not out.write_image(np.ascontiguousarray(arr, dtype=np.float32)):
            raise CompositeError(f"write failed at {name}: {out.geterror()}")
    out.close()


def coverage(parts, prefix, float_id):
    """Cryptomatte coverage of one id across all rank pairs of the CRYPTO_<prefix>NN parts."""
    cov = None
    for n in range(3):
        arr = parts[f"CRYPTO_{prefix}{n:02d}"][0]
        for k in (0, 2):  # (id, coverage) pairs: (r,g) and (b,a)
            ids, cvg = arr[..., k], arr[..., k + 1]
            hit = np.where(ids == np.float32(float_id), cvg, 0.0).astype(np.float32)
            cov = hit if cov is None else cov + hit
    return cov


def crypto_manifest(attrs, wanted_name):
    for k, v in attrs.items():
        if k.startswith("cryptomatte/") and k.endswith("/name") and v == wanted_name:
            key = k[: -len("/name")]
            return json.loads(attrs[key + "/manifest"])
    raise CompositeError(f"no cryptomatte manifest named {wanted_name}")


def over(front, back):
    """Premultiplied over, RGBA float arrays."""
    a = front[..., 3:4]
    return front + (1.0 - a) * back


def derive(frame_path):
    parts = read_parts(frame_path)
    need = ["DEFAULT_HEAD_BEAUTY", "BODY_BEAUTY", "BODY_SHADOW_RAW", "FOREGROUND_PLATE", "HEAD_HOLDOUT"] + [f"CRYPTO_MATERIAL{n:02d}" for n in range(3)]
    missing = [n for n in need if n not in parts]
    if missing:
        raise CompositeError(f"{frame_path.name}: missing parts {missing}")
    full = parts["DEFAULT_HEAD_BEAUTY"][0]
    body = parts["BODY_BEAUTY"][0]
    shadowed = parts["BODY_SHADOW_RAW"][0]
    front = parts["FOREGROUND_PLATE"][0]
    holdout = parts["HEAD_HOLDOUT"][0][..., 0]

    # HEAD_SHADOW_MULTIPLY: declared formula, epsilon floor, clipped fraction reported.
    eps = np.float32(DERIVED["HEAD_SHADOW_MULTIPLY"]["epsilon_scene_linear"])
    rgb_b, rgb_s = body[..., :3], shadowed[..., :3]
    safe = rgb_b >= eps
    ratio = np.where(safe, rgb_s / np.where(safe, rgb_b, 1.0), 1.0)
    clipped = float(np.mean((ratio < 0) | (ratio > 1)))
    if not np.isfinite(ratio).all():
        raise CompositeError("HEAD_SHADOW_MULTIPLY: non-finite ratio — the body plates carry NaN or Inf")
    multiply = np.clip(ratio, 0.0, 1.0).astype(np.float32)

    # SKIN_ID from the material cryptomatte manifest carried on the CRYPTO_MATERIAL parts.
    m_attrs = parts["CRYPTO_MATERIAL00"][1]
    material_names = [v for k, v in m_attrs.items() if k.startswith("cryptomatte/") and k.endswith("/name") and "Material" in v]
    if len(material_names) != 1:
        raise CompositeError(f"expected one material cryptomatte manifest on CRYPTO_MATERIAL00, found {material_names}")
    manifest = crypto_manifest(m_attrs, material_names[0])
    ids = manifest_ids(json.dumps(manifest))
    for mat in ("HERO_SKIN_HEAD", "HERO_SKIN_BODY"):
        if mat not in ids:
            raise CompositeError(f"material {mat} not in the cryptomatte manifest {sorted(ids)}")
    skin_head = coverage(parts, "MATERIAL", ids["HERO_SKIN_HEAD"])
    skin_body = coverage(parts, "MATERIAL", ids["HERO_SKIN_BODY"])
    skin = np.clip(skin_head + skin_body, 0.0, 1.0).astype(np.float32)

    # The precomp pair.
    back = shadowed.astype(np.float32)          # = BODY_BEAUTY × multiply by construction
    # Occluder-footprint check: where the occluder is fully opaque, BACK must hold the body /
    # environment (the occluder is shadow-only in the body plates), not the occluder itself.
    fp = front[..., 3] >= 0.999
    footprint = {"pixels": int(fp.sum())}
    if fp.any():
        footprint.update({"back_vs_body_max_abs": float(np.abs(back[fp, :3] - body[fp, :3]).max()),
                          "back_vs_front_mean_abs": float(np.abs(back[fp, :3] - front[fp, :3]).mean()),
                          "full_vs_front_mean_abs": float(np.abs(full[fp, :3] - front[fp, :3]).mean())})
    report = {"frame": int(frame_path.stem.split(".")[-1]), "multiply_clipped_fraction": clipped,
              "epsilon_branch_pixel_fraction": float((~safe).any(axis=-1).mean()),
              "skin_coverage_mean": {"head": float(skin_head.mean()), "body": float(skin_body.mean()), "union": float(skin.mean())},
              "occluder_footprint": footprint}
    colour = {k: v for k, v in parts["DEFAULT_HEAD_BEAUTY"][1].items() if k in CONV["bundle_attributes"]["carried"]}
    return parts, {"multiply": multiply, "skin": skin, "skin_head": skin_head, "skin_body": skin_body, "back": back, "front": front.astype(np.float32), "full": full, "holdout": holdout, "body": body, "colour": colour}, report


def reproduction(d, head_layer, report):
    """FRONT over (HEAD over BACK) vs DEFAULT_HEAD_BEAUTY (conventions → precomp_reproduction_test).
    HEAD is the unoccluded head layer (head_layer_contract); the band is the union of the head
    and occluder edges; the pass rule is a gate — a failing frame raises."""
    rt = CC["precomp_reproduction_test"]
    comp = over(d["front"], over(head_layer, d["back"]))
    err = np.abs(comp[..., :3] - d["full"][..., :3]).max(axis=-1)
    band = rt["boundary_band_px"]
    edge = edge_band(d["holdout"] > 0.5, band) | edge_band(d["front"][..., 3] > 0.5, band)
    outside = ~edge
    if not outside.any():
        raise CompositeError("boundary band covers the whole frame — nothing to measure")
    res = {"max_abs_error": float(err.max()), "mean_abs_error_outside_band": float(err[outside].mean()),
           "boundary_band_px": band, "band_fraction": float(edge.mean()), "within": {}}
    for tol in rt["tolerances"]["within_abs"]:
        res["within"][str(tol)] = {"outside_band": float((err[outside] <= tol).mean()),
                                   "inside_band": float((err[edge] <= tol).mean()) if edge.any() else None}
    # Same-seed layer agreement away from head and occluder: the shadowed body plate and the full
    # render see identical geometry there, so identical paths — measured, not assumed.
    away = outside & (d["holdout"] < 1e-6) & (d["front"][..., 3] < 1e-6)
    if away.any():
        diff = np.abs(d["back"][away, :3] - d["full"][away, :3]).max(axis=-1)
        res["same_seed_layer_agreement_away_from_head"] = {"pixels": int(away.sum()), "fraction_bit_exact": float((diff == 0).mean()), "max_abs": float(diff.max())}
    rule = rt["pass_rule"]["metrics"]
    values = {"outside_band_within_1e-3_min": res["within"]["0.001"]["outside_band"],
              "inside_band_within_5e-2_min": res["within"]["0.05"]["inside_band"] if res["within"]["0.05"]["inside_band"] is not None else 1.0,
              "band_fraction_max": res["band_fraction"]}
    failed = [k for k, v in values.items() if (v < rule[k] if k.endswith("_min") else v > rule[k])]
    res["pass_rule"] = {"thresholds": rule, "values": values, "failed": failed, "status_of_thresholds": rt["pass_rule"]["status"]}
    res["status"] = "PASS" if not failed else "FAIL"
    res["measured_cause_of_error"] = rt["measured_cause_of_error"]
    report["precomp_reproduction"] = res
    if failed:
        raise CompositeError(f"frame {report['frame']}: precomp reproduction FAIL on {failed}: {values}")
    return comp


def blur_default_head(parts, d, head_layer, out_dir, frame, shutter_frames):
    """The post-composite blur of ADR-0002 D5 (amendment 2026-09-22), run on the DEFAULT head so
    the blur-fidelity gate has something to measure. In production the head layer is the order's
    own, delivered sharp with its own vectors in the same convention; nothing else changes.

    FRONT and BACK carry their own vectors and depth from the render; the head layer uses the head
    layer's. Writes blurred_default_head.####.exr — a picture, not a delivery plate."""
    need = ["FRONT_MOTION_VECTORS", "FRONT_DEPTH", "HEAD_MOTION_VECTORS", "HEAD_DEPTH",
            "BACK_MOTION_VECTORS", "BACK_DEPTH"]
    missing = [n for n in need if n not in parts]
    if missing:
        raise CompositeError(f"frame {frame}: per-layer vectors/depth missing {missing} — the plates were "
                             "rendered before the 2026-09-22 amendment; re-render with render_passes.py")
    def vd(prefix):
        vec = parts[f"{prefix}_MOTION_VECTORS"][0].astype(np.float32)
        dep = parts[f"{prefix}_DEPTH"][0].astype(np.float32)
        return vec, (dep[..., 0] if dep.ndim == 3 else dep)
    layers = [(d["front"], *vd("FRONT")), (head_layer, *vd("HEAD")), (d["back"], *vd("BACK"))]
    img, report = motion_blur.blur(layers, shutter_frames)
    dst = out_dir / f"blurred_default_head.{frame:04d}.exr"
    write_parts(dst, [("BLURRED_DEFAULT_HEAD", img, ["R", "G", "B", "A"], "half", "PREMULTIPLIED")], d["colour"])
    report["file"] = dst.name
    return dst, report


def process_frame(frame_path, out_dir, raw_beauty, shutter_frames=None):
    parts, d, report = derive(frame_path)
    # The default head layer for the reproduction test is L_HEAD.Combined from the raw render.
    raw = read_parts(raw_beauty)
    if "L_HEAD.Combined" not in raw:
        raise CompositeError(f"{raw_beauty.name}: L_HEAD.Combined missing")
    head_layer = raw["L_HEAD.Combined"][0].astype(np.float32)
    reproduction(d, head_layer, report)
    frame = report["frame"]
    if shutter_frames:
        _, report["post_composite_blur"] = blur_default_head(parts, d, head_layer, out_dir, frame, shutter_frames)
    dst = out_dir / f"derived.{frame:04d}.exr"
    planned = [
        ("HEAD_SHADOW_MULTIPLY", d["multiply"], ["R", "G", "B"], "half", "NOT_APPLICABLE"),
        ("SKIN_ID", d["skin"][..., None], ["coverage"], "float", "NOT_APPLICABLE"),
        ("SKIN_ID_HEAD", d["skin_head"][..., None], ["coverage"], "float", "NOT_APPLICABLE"),
        ("SKIN_ID_BODY", d["skin_body"][..., None], ["coverage"], "float", "NOT_APPLICABLE"),
        ("PRECOMP_BACK", d["back"], ["R", "G", "B", "A"], "half", "PREMULTIPLIED"),
        ("PRECOMP_FRONT", d["front"], ["R", "G", "B", "A"], "half", "PREMULTIPLIED"),
    ]
    write_parts(dst, planned, d["colour"])
    written = read_parts(dst)
    if list(written) != [p[0] for p in planned]:
        raise CompositeError(f"{dst.name}: parts {list(written)}")
    for name, arr, chans, ptype, alpha in planned:
        w = written[name]
        expected = arr.astype(np.float16).astype(np.float32) if ptype == "half" else arr.astype(np.float32)
        if w[2] != chans or not np.array_equal(w[0], expected):
            raise CompositeError(f"{dst.name}: {name} does not match what was computed after {ptype} quantization")
        want_colour = "data" if alpha == "NOT_APPLICABLE" else d["colour"].get("colorInteropID")
        if w[1].get("slice:alpha") != alpha or (want_colour and w[1].get("colorInteropID") != want_colour):
            raise CompositeError(f"{dst.name}: {name} alpha/colour declaration wrong: {w[1].get('slice:alpha')!r}, {w[1].get('colorInteropID')!r}")
    (out_dir / f"precomp_report.{frame:04d}.json").write_text(json.dumps(report, indent=1, allow_nan=False) + "\n")
    return dst, report


def main(profile_dir):
    pd = Path(profile_dir)
    manifests = sorted(pd.glob("bundle_manifest.*.json"))
    if len(manifests) != 1:
        raise CompositeError(f"expected one bundle_manifest in {pd}, found {len(manifests)} — run split_bundles.py first")
    bm_path = manifests[0]
    bm = json.loads(bm_path.read_text())
    rm = json.loads((pd / bm["source_render_manifest"]).read_text())
    raw_by_frame = {row["frame"]: pd / "raw" / row["files"]["beauty"]["file"] for row in rm["frames"]}
    # The shutter now describes the blur applied HERE, after the head is composited (ADR-0002 D5
    # amendment 2026-09-22). Shutter 0 (still profile) means no blur, not a silent skip.
    st = rm["settings"]
    if st.get("render_motion_blur"):
        raise CompositeError(f"{bm['source_render_manifest']}: the plates carry rendered motion blur; since the "
                             "2026-09-22 amendment the layers are rendered sharp and blurred after compositing")
    shutter_frames = st["shutter_angle_deg"] / 360.0
    if st["shutter_position"] not in ("CENTRED", "NOT_APPLICABLE"):
        raise CompositeError(f"shutter_position {st['shutter_position']} is not implemented by the post-composite "
                             "blur, which is centred; conventions → post_composite_blur")
    out_dir = pd / "COMPOSITE_BUNDLE"
    derived_rows = []
    for row in bm["bundles"]["COMPOSITE_BUNDLE"]["frames"]:
        dst, report = process_frame(out_dir / row["file"], out_dir, raw_by_frame[row["frame"]], shutter_frames)
        derived_rows.append({"frame": row["frame"], "file": dst.name, "bytes": dst.stat().st_size,
                             "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(), "report": f"precomp_report.{row['frame']:04d}.json",
                             "parts": [{"name": n, "pixel_type": DERIVED[n]["pixel_type"], "alpha": DERIVED[n]["alpha"]} for n in CONV["bundles"]["COMPOSITE_BUNDLE"]["derived_by_compositor"]],
                             "precomp_reproduction": report["precomp_reproduction"], "multiply_clipped_fraction": report["multiply_clipped_fraction"],
                             **({"post_composite_blur": report["post_composite_blur"]} if "post_composite_blur" in report else {})})
        r = report["precomp_reproduction"]
        print(f"COMPOSITE_FRAME {row['frame']} {r['status']} outside_band_within_1e-3={r['within']['0.001']['outside_band']:.4f} inside_band_within_5e-2={r['within']['0.05']['inside_band']:.3f} band={r['band_fraction']:.4f} max_err={r['max_abs_error']:.4g}")
        if "post_composite_blur" in report:
            b = report["post_composite_blur"]
            print(f"BLUR_FRAME {row['frame']} samples={b['samples']} path={b['longest_path_px']}px holes_filled={b['holes_filled']} {b['seconds']}s -> {b['file']}")
    bm["bundles"]["COMPOSITE_BUNDLE"]["derived"] = {"script": CC["script"], "frames": derived_rows, "static_precomp": CC["derived"]["STATIC_PRECOMP"]}
    bm_path.write_text(json.dumps(bm, indent=1) + "\n")
    print(f"COMPOSITE_OK {len(derived_rows)} frames -> {out_dir}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(argv[0])
    except (CompositeError, IndexError, OSError, ValueError, StopIteration, KeyError) as e:
        print(f"COMPOSITE_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
