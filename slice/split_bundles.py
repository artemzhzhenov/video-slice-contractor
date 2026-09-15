"""Split the raw per-frame multilayer EXRs into the two delivery bundles (ADR-0002 D5;
master-spec bundles; conventions.json → bundles). Runs under Blender's Python for its
OpenImageIO + numpy — every EXR is read and written through the OIIO API, never through
`oiiotool --attrib`, which parses its value and truncates a JSON cryptomatte manifest to its
first token (found 2026-09-15, verified with exrinfo):

    blender -b --python-exit-code 2 -P slice/split_bundles.py -- <pkg>/shots/SHOT_001/renders/<profile> \
        [--exports <shot exports dir>] [--no-plus-files]

Reads render_manifest.<profile>.json; writes HEAD_RENDER_BUNDLE/holdout.####.exr and
COMPOSITE_BUNDLE/composite.####.exr (multi-part, parts named and typed per conventions,
cryptomatte/* attributes carried onto the CRYPTO_* parts, slice:alpha and slice:pass on every
part, zip compression); re-reads every written part and requires it to equal the source part
after the declared quantization; records bytes_per_frame and a pixel SHA-1 per part in
bundle_manifest.<profile>.json; copies the HEAD_RENDER plus files (exports + probe)."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import OpenImageIO as oiio

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
BUNDLES = CONV["bundles"]
TYPE = {"half": oiio.HALF, "float": oiio.FLOAT}


class SplitError(RuntimeError):
    pass


def read_parts(path):
    """{part_name: {"pixels": HxWxC float32, "channels": [...], "attrs": {name: value}, "format": 'half'|'float'}}."""
    inp = oiio.ImageInput.open(str(path))
    if inp is None:
        raise SplitError(f"cannot open {path}: {oiio.geterror()}")
    parts, i = {}, 0
    while inp.seek_subimage(i, 0):
        spec = inp.spec()
        name = spec.getattribute("oiio:subimagename")
        if not name:
            raise SplitError(f"{Path(path).name}: part {i} has no oiio:subimagename")
        pix = np.asarray(inp.read_image(i, 0, 0, spec.nchannels, oiio.FLOAT), dtype=np.float32).reshape(spec.height, spec.width, spec.nchannels)
        fmt = "half" if spec.format == oiio.HALF else ("float" if spec.format == oiio.FLOAT else str(spec.format))
        parts[name] = {"pixels": pix, "channels": list(spec.channelnames), "attrs": {a.name: a.value for a in spec.extra_attribs},
                       "format": fmt, "size": (spec.width, spec.height)}
        i += 1
    inp.close()
    return parts


def write_parts(path, parts):
    """parts: list of dicts {name, pixels, channels, format, attrs}. Multi-part EXR, zip."""
    specs = []
    for p in parts:
        h, w, c = p["pixels"].shape
        spec = oiio.ImageSpec(w, h, c, TYPE[p["format"]])
        spec.channelnames = p["channels"]
        spec.attribute("compression", CONV["exr"]["compression"])
        for k, v in p["attrs"].items():
            spec.attribute(k, v)
        spec.attribute("oiio:subimagename", p["name"])
        specs.append(spec)
    out = oiio.ImageOutput.create(str(path))
    if out is None or not out.open(str(path), specs):
        raise SplitError(f"cannot open {path} for writing: {oiio.geterror() if out is None else out.geterror()}")
    for i, p in enumerate(parts):
        if i > 0 and not out.open(str(path), specs[i], "AppendSubimage"):
            raise SplitError(f"{path.name}: append failed at {p['name']}: {out.geterror()}")
        if not out.write_image(np.ascontiguousarray(p["pixels"], dtype=np.float32)):
            raise SplitError(f"{path.name}: write failed at {p['name']}: {out.geterror()}")
    out.close()


def quantize(pixels, fmt):
    return pixels.astype(np.float16).astype(np.float32) if fmt == "half" else pixels.astype(np.float32)


def pixel_sha1(pixels):
    return hashlib.sha1(np.ascontiguousarray(pixels, dtype=np.float32).tobytes()).hexdigest()


def build_bundle(bundle, sources, frame, out_dir, profile_settings):
    spec = BUNDLES[bundle]
    crypto = {}
    for src in sources.values():
        for part in src.values():
            crypto.update({k: v for k, v in part["attrs"].items() if k.startswith("cryptomatte/")})
    planned = []
    for part in spec["parts"]:
        group, src_part = part["from"].split(":")
        src = sources[group].get(src_part)
        if src is None:
            raise SplitError(f"frame {frame}: source part {src_part} missing from the {group} render")
        if part.get("channels"):
            idx = [src["channels"].index(c) for c in part["channels"].keys()]
            pixels, chans = src["pixels"][..., idx], list(part["channels"].values())
        elif part.get("keep_channel_names"):
            pixels, chans = src["pixels"], src["channels"]
        else:
            pixels, chans = src["pixels"], [c.split(".")[-1] for c in src["channels"]]
        attrs = {"slice:pass": part["name"], "slice:alpha": part["alpha"], "slice:source": part["from"]}
        if part["alpha"] == "NOT_APPLICABLE":
            attrs.update(CONV["bundle_attributes"]["data_declaration"])
        else:
            for k in CONV["bundle_attributes"]["carried"]:
                if k in src["attrs"]:
                    attrs[k] = src["attrs"][k]
        if part["name"].startswith("CRYPTO_") and part["pixel_type"] != "float":
            raise SplitError(f"{part['name']}: cryptomatte ids are only exact in float; conventions declare {part['pixel_type']}")
        if part["name"].startswith("CRYPTO_"):
            if not crypto:
                raise SplitError(f"frame {frame}: no cryptomatte/* attributes in the source — the matte would be unreadable")
            attrs.update(crypto)
        planned.append({"name": part["name"], "pixels": pixels, "channels": chans, "format": part["pixel_type"], "attrs": attrs, "source": src, "spec": part})
    stem = "holdout" if bundle == "HEAD_RENDER_BUNDLE" else "composite"
    dst = out_dir / f"{stem}.{frame:04d}.exr"
    write_parts(dst, planned)
    written = read_parts(dst)
    if list(written) != [p["name"] for p in planned]:
        raise SplitError(f"{dst.name}: parts {list(written)} != {[p['name'] for p in planned]}")
    rows = []
    for p in planned:
        w = written[p["name"]]
        if w["format"] != p["format"]:
            raise SplitError(f"{dst.name}: {p['name']} must be {p['format']}, is {w['format']}")
        if w["channels"] != p["channels"]:
            raise SplitError(f"{dst.name}: {p['name']} channels {w['channels']} != {p['channels']}")
        expected = quantize(p["pixels"], p["format"])
        if not np.array_equal(w["pixels"], expected):
            raise SplitError(f"{dst.name}: {p['name']} differs from its source after {p['format']} quantization")
        if p["name"].startswith("CRYPTO_"):
            names = {v for k, v in w["attrs"].items() if k.startswith("cryptomatte/") and k.endswith("/name")}
            if not any(p["spec"]["from"].split(":")[1].startswith(n) for n in names):
                raise SplitError(f"{dst.name}: {p['name']} lacks the cryptomatte manifest matching its channels ({names})")
            for k, v in w["attrs"].items():
                if k.startswith("cryptomatte/") and k.endswith("/manifest"):
                    json.loads(v)  # a truncated manifest is not JSON — fail here, not in the compositor
        if w["attrs"].get("slice:alpha") != p["spec"]["alpha"]:
            raise SplitError(f"{dst.name}: {p['name']} slice:alpha is {w['attrs'].get('slice:alpha')!r}")
        want_colour = "data" if p["spec"]["alpha"] == "NOT_APPLICABLE" else p["source"]["attrs"].get("colorInteropID")
        if want_colour and w["attrs"].get("colorInteropID") != want_colour:
            raise SplitError(f"{dst.name}: {p['name']} colour declaration is {w['attrs'].get('colorInteropID')!r}, expected {want_colour!r}")
        row = {"name": p["name"], "pixel_type": p["format"], "channels": w["channels"], "alpha": p["spec"]["alpha"],
               "pixel_sha1": pixel_sha1(w["pixels"]), "source": p["spec"]["from"]}
        if p["name"] == "MOTION_VECTORS":
            row["shutter_angle_deg"] = profile_settings["shutter_angle_deg"]
            row["shutter_position"] = profile_settings["shutter_position"]
            row["consumer"] = "NONE" if profile_settings["shutter_angle_deg"] == 0 else "head technology (motion-blur matching), compositor"
        rows.append(row)
    return dst, rows


def copy_plus_files(pd, raw, man, exports_dir):
    """The HEAD_RENDER bundle also carries the exports and the lighting probe (conventions →
    bundles.HEAD_RENDER_BUNDLE.plus_files). Every listed file must exist; none is optional."""
    bdir = pd / "HEAD_RENDER_BUNDLE"
    bdir.mkdir(exist_ok=True)
    copied = {}
    for name in BUNDLES["HEAD_RENDER_BUNDLE"]["plus_files"]:
        if name == "lighting_probe":
            if not man.get("probe"):
                raise SplitError("lighting probe listed in plus_files but this render has none — run render_passes with --probe")
            src = raw / man["probe"]["file"]
        else:
            if exports_dir is None:
                raise SplitError(f"{name} listed in plus_files but no --exports directory given")
            src = Path(exports_dir) / name
        if not src.exists():
            raise SplitError(f"plus file missing: {src}")
        dst = bdir / src.name
        shutil.copy2(src, dst)
        copied[src.name] = hashlib.sha256(dst.read_bytes()).hexdigest()
    return copied


def main(argv):
    if not argv:
        raise SplitError("usage: split_bundles.py <renders/<profile>> [--exports <shot exports dir>] [--no-plus-files]")
    pd = Path(argv[0])
    exports_dir = argv[argv.index("--exports") + 1] if "--exports" in argv else None
    with_plus = "--no-plus-files" not in argv
    manifests = sorted(pd.glob("render_manifest.*.json"))
    if len(manifests) != 1:
        raise SplitError(f"expected one render_manifest in {pd}, found {len(manifests)}")
    man = json.loads(manifests[0].read_text())
    for key in ("source_scene", "settings", "frames", "smoke_test_only"):
        if key not in man:
            raise SplitError(f"{manifests[0].name}: missing {key}")
    if "scene_kind" not in man["source_scene"]:
        raise SplitError(f"{manifests[0].name}: source_scene.scene_kind missing — provenance is not invented")
    raw = pd / "raw"
    out_manifest = {"shot_id": man["shot_id"], "profile": man["profile"], "smoke_test_only": man["smoke_test_only"],
                    "source_scene": man["source_scene"], "source_render_manifest": manifests[0].name,
                    "working_space": CONV["colour"]["working_space"], "carried_attributes": CONV["bundle_attributes"]["carried"],
                    "attributes_not_carried": CONV["bundle_attributes"]["not_carried"],
                    "exr_compression": CONV["exr"]["compression"], "writer": f"OpenImageIO {oiio.VERSION_STRING} (Blender's Python)",
                    "bundles": {b: {"read_granularity": BUNDLES[b]["read_granularity"], "consumer": BUNDLES[b]["consumer"], "frames": []} for b in BUNDLES}}
    for row in man["frames"]:
        frame = row["frame"]
        sources = {g: read_parts(raw / row["files"][g]["file"]) for g in ("beauty", "data")}
        for b in BUNDLES:
            bdir = pd / b
            bdir.mkdir(exist_ok=True)
            dst, parts = build_bundle(b, sources, frame, bdir, man["settings"])
            out_manifest["bundles"][b]["frames"].append({"frame": frame, "file": dst.name, "bytes": dst.stat().st_size,
                                                         "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(), "parts": parts})
    if with_plus:
        out_manifest["bundles"]["HEAD_RENDER_BUNDLE"]["plus_files"] = copy_plus_files(pd, raw, man, exports_dir)
    scene_kind = man["source_scene"]["scene_kind"]
    for b, info in out_manifest["bundles"].items():
        sizes = [f["bytes"] for f in info["frames"]]
        info["bytes_per_frame"] = {"min": min(sizes), "max": max(sizes), "mean": sum(sizes) / len(sizes),
                                   "measured_on": f"{scene_kind}, {'smoke settings' if man['smoke_test_only'] else 'conformant settings'}"}
    (pd / f"bundle_manifest.{man['profile']}.json").write_text(json.dumps(out_manifest, indent=1) + "\n")
    print("SPLIT_OK " + json.dumps({b: {"frames": len(i["frames"]), "bytes_per_frame_mean": i["bytes_per_frame"]["mean"]} for b, i in out_manifest["bundles"].items()}))


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        main(args)
    except (SplitError, OSError, ValueError) as e:
        print(f"SPLIT_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
