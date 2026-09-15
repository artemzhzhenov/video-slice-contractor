"""Render the raw multilayer EXRs of one shot for one profile, in two groups, plus the lighting
probe (ADR-0002 D5, D6, D9; proposal §1):

    blender -b <scene.blend> --python-exit-code 2 -P slice/render_passes.py -- \
        --shot SHOT_001 --profile video --frames 1001-1120 --out <pkg>/shots/SHOT_001/renders [--probe] \
        [--samples N --scale PCT]   # smoke-test overrides; the manifest marks the output non-conformant

Group "beauty": L_FULL, L_BODY, L_BODYSHADOW, L_HEAD, L_FG with the profile's shutter.
Group "data":   L_DATA with motion blur off (Depth unfiltered, Vector available).
Output: <out>/<profile>/raw/beauty.####.exr, data.####.exr, lighting_probe.####.exr and
render_manifest.<profile>.json (settings, device, per-frame seconds and bytes, sha256).
The scene file is never saved from here. Bundle split: slice/split_bundles.py."""
import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
SMAP = json.loads((ROOT / "slice" / "state_map.json").read_text())
N = CONV["scene_naming"]
HERO = ("C_HEAD", "C_HAIR", "C_BODY", "C_HAND_FG")


class RenderError(RuntimeError):
    pass


def parse_frames(spec, shot, profile):
    if spec == "still":
        return [SMAP["still_frames"][shot]]
    if spec == "all":
        fr = CONV["shots"][shot]["frame_range"]
        return list(range(fr["start"], fr["end"] + 1))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    fr = CONV["shots"][shot]["frame_range"]
    bad = [f for f in out if not fr["start"] <= f <= fr["end"]]
    if bad:
        raise RenderError(f"frames {bad} outside {shot}'s range {fr}")
    return out


def configure_device(scene):
    cprefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        cprefs.compute_device_type = "METAL"
        cprefs.get_devices()
        for d in cprefs.devices:
            d.use = d.type in ("METAL", "CPU")
        if any(d.type == "METAL" and d.use for d in cprefs.devices):
            scene.cycles.device = "GPU"
            return "METAL"
    except Exception as e:  # noqa: BLE001
        print(f"RENDER_NOTE: Metal unavailable ({e})")
    scene.cycles.device = "CPU"
    return "CPU"


def apply_profile(scene, profile, samples, scale):
    p = CONV["render_profiles"][profile]
    rx, ry = p["resolution"]
    scene.render.resolution_x, scene.render.resolution_y = rx, ry
    scene.render.resolution_percentage = scale
    scene.cycles.samples = samples
    angle = p["shutter_angle_deg"]
    if angle > 0:
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = angle / 360.0
        scene.render.motion_blur_position = {"CENTRED": "CENTER", "START": "START", "END": "END"}[p["shutter_position"]]
    elif angle == 0:
        scene.render.use_motion_blur = False  # shutter 0 (ADR-0002 D9)
    else:
        raise RenderError(f"profile {profile}: shutter_angle_deg {angle} is not a shutter")
    # Determinism settings are the template's; assert and record them, never assume.
    det = CONV["determinism"]
    c = scene.cycles
    actual = {"seed": c.seed, "use_adaptive_sampling": c.use_adaptive_sampling, "use_denoising": c.use_denoising, "use_animated_seed": c.use_animated_seed}
    want = {k: det[k] for k in actual}
    if actual != want:
        raise RenderError(f"determinism settings {actual} differ from conventions {want}")
    if scene.render.image_settings.exr_codec.lower() != CONV["exr"]["compression"]:
        raise RenderError(f"exr codec {scene.render.image_settings.exr_codec} is not {CONV['exr']['compression']}")
    return {"resolution": [rx, ry], "resolution_percentage": scale, "samples": samples,
            "shutter_angle_deg": angle, "shutter_position": p["shutter_position"],
            "dof_camera_setting": bool(scene.camera.data.dof.use_dof), "determinism": actual,
            "exr_codec": scene.render.image_settings.exr_codec, "color_depth": scene.render.image_settings.color_depth,
            "conformant": samples == p["samples"] and scale == 100}


def set_group(scene, group, dof_setting):
    """Enable the group's view layers. The data group renders with motion blur AND depth of
    field off (proposal §1 row 5: Depth is unfiltered, unusable under either); the beauty group
    keeps the camera's own DoF setting."""
    layers = CONV["render_groups"][group]["view_layers"]
    for vl in scene.view_layers:
        vl.use = vl.name in layers
    if group == "data":
        scene.render.use_motion_blur = False
        scene.camera.data.dof.use_dof = False
    else:
        scene.camera.data.dof.use_dof = dof_setting
    return {"motion_blur": scene.render.use_motion_blur, "dof": scene.camera.data.dof.use_dof}


def render_one(scene, filepath_stem, frame):
    scene.frame_set(frame)
    # write_still does not substitute '#' padding (verified on 5.2.1): name the file explicitly.
    scene.render.filepath = f"{filepath_stem}.{frame:04d}"
    t = time.time()
    bpy.ops.render.render(write_still=True, animation=False)
    seconds = round(time.time() - t, 2)
    written = Path(f"{filepath_stem}.{frame:04d}.exr")
    if not written.exists() or written.stat().st_size == 0:
        raise RenderError(f"expected {written} after rendering frame {frame}")
    return written, seconds


def render_probe(scene, out_dir, frame, device_note):
    """Chrome + grey balls at the socket position, hero collections excluded, on a temporary
    view layer; nothing is saved to the scene file."""
    pc = CONV["lighting_probe"]
    coll = bpy.data.collections.new("C_PROBE_TMP")
    scene.collection.children.link(coll)
    sock = bpy.data.objects["SOCKET_HEAD"]
    scene.frame_set(frame)
    base = sock.matrix_world.translation.copy()
    created = []
    for i, (name, spec) in enumerate(pc["balls"].items()):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(base.x + (-0.16 if i == 0 else 0.16), base.y, base.z), segments=64, ring_count=32)
        ball = bpy.context.active_object
        ball.name = f"PROBE_{name.upper()}"
        for c in ball.users_collection:
            c.objects.unlink(ball)
        coll.objects.link(ball)
        bpy.ops.object.shade_smooth()
        m = bpy.data.materials.new(f"PROBE_{name.upper()}")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (spec["base"], spec["base"], spec["base"], 1.0)
        b.inputs["Metallic"].default_value = spec["metallic"]
        b.inputs["Roughness"].default_value = spec["roughness"]
        ball.data.materials.append(m)
        created.append((ball, m))
    vl = scene.view_layers.new("L_PROBE_TMP")
    for c in N["collections"]:
        lc = vl.layer_collection.children[c]
        lc.exclude = c in HERO
    vl.use_pass_combined = True
    for other in scene.view_layers:
        other.use = other.name == "L_PROBE_TMP"
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    pct, blur = scene.render.resolution_percentage, scene.render.use_motion_blur
    scene.render.resolution_x, scene.render.resolution_y = pc["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = False
    written, seconds = render_one(scene, str(out_dir / "lighting_probe"), frame)
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage, scene.render.use_motion_blur = rx, ry, pct, blur
    scene.view_layers.remove(vl)
    for ball, m in created:
        mesh = ball.data
        bpy.data.objects.remove(ball, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        bpy.data.materials.remove(m)
    bpy.data.collections.remove(coll)
    return written, seconds


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--shot", required=True)
    p.add_argument("--profile", choices=["video", "still"], required=True)
    p.add_argument("--frames", default=None, help="'all', 'still', '1001-1010', '1001,1050'")
    p.add_argument("--out", required=True)
    p.add_argument("--samples", type=int, default=None)
    p.add_argument("--scale", type=int, default=100)
    p.add_argument("--probe", action="store_true")
    args = p.parse_args(argv)
    scene = bpy.data.scenes["SLICE"]
    if args.shot not in CONV["shots"] or scene.get("shot_id") != args.shot:
        raise RenderError(f"scene is {scene.get('shot_id')}, requested {args.shot}")
    spec = args.frames if args.frames is not None else ("still" if args.profile == "still" else "all")
    frames = parse_frames(spec, args.shot, args.profile)
    samples = CONV["render_profiles"][args.profile]["samples"] if args.samples is None else args.samples
    if samples < 1:
        raise RenderError(f"samples {samples}")
    out = Path(args.out).resolve() / args.profile
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    device = configure_device(scene)
    dof_setting = bool(scene.camera.data.dof.use_dof)
    settings = apply_profile(scene, args.profile, samples, args.scale)
    scene_path = Path(bpy.data.filepath)
    placeholders = sorted(o.name for o in bpy.data.objects if o.name.startswith("PLACEHOLDER_"))
    manifest = {"shot_id": args.shot, "profile": args.profile, "blender": bpy.app.version_string, "device": device,
                "machine": platform.platform(), "ocio_env": os.environ.get("OCIO") or "NOT_VERIFIED",
                "source_scene": {"file": scene_path.name, "sha256": sha256(scene_path) if scene_path.exists() else "UNKNOWN",
                                 "slice_template_version": scene.get("slice_template_version"), "placeholder_objects": placeholders,
                                 "scene_kind": "placeholder template" if placeholders else "asset"},
                "settings": settings, "smoke_test_only": not settings["conformant"],
                "groups": {g: {"view_layers": CONV["render_groups"][g]["view_layers"]} for g in ("beauty", "data")},
                "frames": [], "probe": None,
                "file_hash_note": "sha256 is an integrity token for the file, not a reproducibility token: EXR headers carry render time and date; pixel hashes are in bundle_manifest"}
    for frame in frames:
        row = {"frame": frame, "files": {}, "seconds": {}}
        for group in ("beauty", "data"):
            apply_profile(scene, args.profile, samples, args.scale)
            state = set_group(scene, group, dof_setting)
            manifest["groups"][group].update(state)
            written, seconds = render_one(scene, str(raw / group), frame)
            row["files"][group] = {"file": written.name, "bytes": written.stat().st_size, "sha256": sha256(written)}
            row["seconds"][group] = seconds
        manifest["frames"].append(row)
        print(f"RENDER_FRAME {args.profile} {frame} beauty={row['seconds']['beauty']}s data={row['seconds']['data']}s")
    scene.camera.data.dof.use_dof = dof_setting
    if args.probe:
        probe_frame = CONV["shots"][args.shot]["frame_range"]["start"]  # lighting is per shot and asserted static
        written, seconds = render_probe(scene, raw, probe_frame, device)
        manifest["probe"] = {"frame": probe_frame, "file": written.name, "bytes": written.stat().st_size, "sha256": sha256(written), "seconds": seconds, "resolution": CONV["lighting_probe"]["resolution"], "samples": samples}
    for vl in scene.view_layers:
        vl.use = True
    (out / f"render_manifest.{args.profile}.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"RENDER_OK {args.profile} {len(frames)} frames -> {out}")


if __name__ == "__main__":
    try:
        main()
    except RenderError as e:
        print(f"RENDER_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
