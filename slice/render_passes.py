"""Render the raw multilayer EXRs of one shot for one profile, in two groups, plus the lighting
probe (ADR-0002 D5, D6, D9; proposal §1):

    blender -b <scene.blend> --python-exit-code 2 -P slice/render_passes.py -- \
        --shot SHOT_001 --profile video --frames 1001-1120 --out <pkg>/shots/SHOT_001/renders [--probe] \
        [--samples N --scale PCT]   # smoke-test overrides; the manifest marks the output non-conformant

Group "beauty": L_FULL, L_BODY, L_BODYSHADOW, L_HEAD, L_FG rendered SHARP, each carrying its own
                Vector and Depth (ADR-0002 D5 amendment 2026-09-22: motion blur is applied after
                compositing, from per-layer vectors — blurring the layers and compositing after
                draws a line across the head/body seam under relative motion).
Group "data":   L_DATA with motion blur and DoF off (Depth unfiltered, front-most Vector).
--blur-reference renders L_FULL only, WITH the profile's shutter, as the reference the
blur-fidelity gate compares the post-composite blur against (§Validation criterion 8). It is not a
deliverable plate: split_bundles refuses that manifest.
Output: <out>/<profile>/raw/beauty.####.exr, data.####.exr, lighting_probe.####.exr and
render_manifest.<profile>.json (settings, device, per-frame seconds and bytes, sha256).
The scene file is never saved from here. Bundle split: slice/split_bundles.py."""
import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from fractions import Fraction
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


def time_stretch(angle):
    """(frame_map_old, frame_map_new) that stretch the animation by 720 / shutter angle, so that
    frame ±1 of the stretched timeline is the shutter's open / close instant of the original — where
    every Vector pass must point since the ADR-0002 amendment of 2026-09-25 (×4 at 180°). The picture
    of the stretched frame is the original frame's (measured: p99 difference 0 on SHOT_002 1209)."""
    f = Fraction(720, angle).limit_denominator(900)
    if f.numerator > 900 or f.denominator > 900 or abs(float(f) - 720 / angle) > 1e-9:
        raise RenderError(f"shutter angle {angle}° needs a time stretch of {720 / angle} that Blender's time remapping (1..900) cannot express exactly")
    return f.denominator, f.numerator


def set_stretch(scene, old_new):
    scene.render.frame_map_old, scene.render.frame_map_new = old_new


def blur_reference_steps(n_samples):
    """Cycles motion steps whose time points are the exports' sub-frame samples: Blender samples
    2^(steps-1)+1 instants across the shutter, open to close."""
    steps = 1 + math.log2(n_samples - 1) if n_samples > 1 else None
    if steps is None or steps != int(steps):
        raise RenderError(f"{n_samples} sub-frame samples cannot be matched by Cycles motion steps (2^(steps-1)+1 instants)")
    return int(steps)


def apply_profile(scene, profile, samples, scale, blur_reference=False):
    p = CONV["render_profiles"][profile]
    rx, ry = p["resolution"]
    # A smoke scale must give whole pixels on both axes. Blender truncates rx·pct/100 while every
    # consumer that re-derives the size rounds it, so a scale like 16 % on 3840×2160 renders
    # 614×345 where the round-trip expects 614×346 and stops with a size mismatch that says
    # nothing about its cause (contractor, 2026-09-17). Refused here, where the cause is visible.
    if (rx * scale) % 100 or (ry * scale) % 100:
        ok = [s for s in range(1, 101) if not (rx * s) % 100 and not (ry * s) % 100]
        raise RenderError(f"--scale {scale} % on {profile}'s {rx}x{ry} gives {rx * scale / 100:.1f}x{ry * scale / 100:.1f} px, "
                          f"not whole pixels; scales that do: {', '.join(str(s) + ' %' for s in ok)}")
    scene.render.resolution_x, scene.render.resolution_y = rx, ry
    scene.render.resolution_percentage = scale
    scene.cycles.samples = samples
    angle = p["shutter_angle_deg"]
    if angle < 0:
        raise RenderError(f"profile {profile}: shutter_angle_deg {angle} is not a shutter")
    # Deliverable plates are rendered sharp whatever the shutter says: since the 2026-09-22
    # amendment the shutter describes the blur the compositor applies (conventions →
    # post_composite_blur). Only the blur-fidelity reference is rendered with the shutter open.
    vectors = {"vector_reach_frames": None, "vectors_point_at": "NOT_APPLICABLE — no shutter, no blur", "time_stretch": None}
    motion_steps = None
    if blur_reference:
        if angle == 0:
            raise RenderError(f"profile {profile}: shutter is 0, so a blur reference would equal the plate")
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = angle / 360.0
        scene.render.motion_blur_position = {"CENTRED": "CENTER", "START": "START", "END": "END"}[p["shutter_position"]]
        set_stretch(scene, (100, 100))
        # the reference samples the shutter at the exports' own instants, so the round-trip compares
        # like with like (ADR-0002 amendment 2026-09-25: three samples could not describe a laugh pulse)
        motion_steps = blur_reference_steps(len(CONV["exports"]["sub_frame_offsets_frames"]))
        for o in bpy.data.objects:
            o.cycles.motion_steps = motion_steps          # every object, or the render stops: never a silent default
        vectors["vectors_point_at"] = "NOT_APPLICABLE — the reference carries no Vector pass"
        # an object with its own motion blur off is sharp in the ground truth: recorded, never hidden
        vectors["objects_without_motion_blur"] = sorted(o.name for o in bpy.data.objects if o.type in ("MESH", "CURVES", "CURVE") and
                                                        not (o.cycles.use_motion_blur and o.cycles.use_deform_motion))
    else:
        scene.render.use_motion_blur = False
        if angle > 0 and p["shutter_position"] == "CENTRED":
            stretch = time_stretch(angle)
            set_stretch(scene, stretch)
            vectors = {"vector_reach_frames": angle / 720.0, "vectors_point_at": "the shutter's open and close instants (ADR-0002 amendment 2026-09-25)",
                       "time_stretch": list(stretch)}
        elif angle > 0:
            raise RenderError(f"profile {profile}: shutter position {p['shutter_position']} — shutter-end vectors are defined for a centred shutter only")
        else:
            set_stretch(scene, (100, 100))
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
            "render_motion_blur": bool(scene.render.use_motion_blur),
            "blur": "rendered_reference" if blur_reference else p.get("motion_blur", "none — shutter 0"),
            "dof_camera_setting": bool(scene.camera.data.dof.use_dof), "determinism": actual,
            "exr_codec": scene.render.image_settings.exr_codec, "color_depth": scene.render.image_settings.color_depth,
            "conformant": samples == p["samples"] and scale == 100, **vectors,
            "motion_steps": motion_steps, "shutter_time_points": (2 ** (motion_steps - 1) + 1) if motion_steps else None}


SKIN_LAYERS = sorted({p["from"].split(":")[1].split(".")[0] for p in CONV["bundles"]["SKIN_BUNDLE"]["parts"]})
SKIN_CRYPTO_DEPTH = 2 * sum(1 for p in CONV["bundles"]["SKIN_BUNDLE"]["parts"] if p["name"].startswith("CRYPTO_BODY_MATERIAL"))  # 2 ranks per part


def skin_material(scene):
    """The master's body-skin albedo for the re-tint (ADR-0002 amendment 2026-09-29, C2): the Principled base colour of
    conventions → skin_tone.material_body, and whether a plain gain can describe that skin (no texture on the base colour,
    no subsurface) — recorded, and enforced where the re-tint is made."""
    name = CONV["skin_tone"]["material_body"]
    m = bpy.data.materials.get(name)
    if m is None or not m.use_nodes:
        return {"name": name, "status": "MISSING" if m is None else "NO NODES"}
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        return {"name": name, "status": "NO PRINCIPLED BSDF"}
    sss = float(b.inputs["Subsurface Weight"].default_value)
    textured = bool(b.inputs["Base Color"].is_linked)
    return {"name": name, "base_color": [round(float(v), 6) for v in b.inputs["Base Color"].default_value[:3]],
            "subsurface_weight": sss, "base_color_textured": textured,
            "status": "RE-TINTABLE" if not textured and sss == 0.0 else "NOT RE-TINTABLE BY A GAIN (textured base colour or subsurface — re-measure, ADR-0002 amendment 2026-09-29 §Does not solve)"}


def set_group(scene, group, dof_setting):
    """Enable the group's view layers. The data group renders with motion blur AND depth of
    field off (proposal §1 row 5: Depth is unfiltered, unusable under either); the beauty group
    keeps the camera's own DoF setting and, since the 2026-09-22 amendment, carries Vector and
    Depth on every layer — Cycles only produces Vector with motion blur off, which is now the
    case for every deliverable plate."""
    layers = CONV["render_groups"][group]["view_layers"]
    for vl in scene.view_layers:
        vl.use = vl.name in layers
    if group == "data":
        scene.render.use_motion_blur = False
        scene.camera.data.dof.use_dof = False
    else:
        scene.camera.data.dof.use_dof = dof_setting
    if group == "beauty":
        if scene.render.use_motion_blur:
            raise RenderError("the beauty group must render sharp: Cycles produces no Vector pass with motion blur on")
        for vl in scene.view_layers:
            if vl.name in layers:
                vl.use_pass_vector = True
                vl.use_pass_z = True
            if vl.name in SKIN_LAYERS:   # ADR-0002 amendment 2026-09-29, C1: the skin's diffuse light and a matte per layer
                vl.use_pass_diffuse_color = vl.use_pass_diffuse_direct = vl.use_pass_diffuse_indirect = True
                vl.use_pass_cryptomatte_material = True
                vl.pass_cryptomatte_depth = SKIN_CRYPTO_DEPTH
    elif group == "blur_reference":
        for vl in scene.view_layers:
            if vl.name in layers:
                vl.use_pass_vector = False       # Cycles cannot produce it with the shutter open
    return {"motion_blur": scene.render.use_motion_blur, "dof": scene.camera.data.dof.use_dof}


def aim_eyes(scene, exports_dir):
    """The gaze target point of vocabulary v2 (ADR-0002 amendment 2026-09-30): each eye of the default head is
    aimed at the exported point — the rendered master follows the rule every head follows. The point comes from
    the exports' performance_track.json (socket-local, metres) and is placed per frame in world space on an aim
    empty (keys linear; the shutter's sub-frames interpolate it), and every eye object (conventions →
    scene_naming.eyes) gets a Damped Track to it along its pupil axis. The scene is not saved. A rig that carries
    its own look-at object already aims its eyes: nothing is added and that is recorded. Returns the manifest
    record; without --exports the rig's own eye rotation renders, recorded as NONE (plates before vocabulary v2
    are rebuilt that way)."""
    E = N["eyes"]
    track_path = Path(exports_dir) / "performance_track.json"
    track = json.loads(track_path.read_text())
    if track.get("channel_vocabulary_version", 0) < 2 or any("gaze" not in f for f in track["frames"]):
        raise RenderError(f"{track_path}: no gaze target point per frame (vocabulary {track.get('channel_vocabulary_version')}) — re-export with the current export_shot.py")
    if bpy.data.objects.get(E["look_at"]) is not None:
        return {"mode": "RIG_LOOK_AT", "object": E["look_at"], "note": "the rig aims its own eyes"}
    sys.path.insert(0, str(ROOT))
    from slice.eyes import EyesError, eye_objects
    try:
        eyes, _kind = eye_objects(bpy.data.objects)
    except EyesError as e:
        raise RenderError(str(e)) from None
    socket = bpy.data.objects["SOCKET_HEAD"]
    sys.path.insert(0, str(ROOT))
    from slice import socketspace as ss
    from mathutils import Matrix, Vector
    from_local = Matrix(ss.C).inverted()
    aim = bpy.data.objects.new("GAZE_AIM_TMP", None)
    scene.collection.objects.link(aim)
    aim.rotation_mode = "XYZ"
    for f in track["frames"]:
        scene.frame_set(f["frame"])
        aim.location = socket.matrix_world @ from_local @ Vector(f["gaze"]["target_m"])
        aim.keyframe_insert("location", frame=f["frame"])
    action = aim.animation_data.action
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:   # Blender 4.4+ layered actions: the slot's channel bag holds the curves
        fcurves = action.layers[0].strips[0].channelbag(action.slots[0]).fcurves
    for fc in fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    ax = Vector(E["pupil_axis_local"])
    axis = {(0, -1, 0): "TRACK_NEGATIVE_Y", (0, 1, 0): "TRACK_Y", (0, 0, -1): "TRACK_NEGATIVE_Z", (0, 0, 1): "TRACK_Z", (1, 0, 0): "TRACK_X", (-1, 0, 0): "TRACK_NEGATIVE_X"}[tuple(int(round(v)) for v in ax)]
    for e in eyes:
        c = e.constraints.new("DAMPED_TRACK")
        c.name = "GAZE_AIM_TMP"
        c.target = aim
        c.track_axis = axis
    scene.frame_set(scene.frame_start)
    return {"mode": "TARGET_POINT", "eyes": [e.name for e in eyes], "track_sha256": hashlib.sha256(track_path.read_bytes()).hexdigest(),
            "sources": {k: sum(1 for f in track["frames"] if f["gaze"]["source"] == k) for k in sorted({f["gaze"]["source"] for f in track["frames"]})},
            "rule": "channel_map.json → gaze: each eye's line of sight through the point; keys linear between frames"}


def render_one(scene, filepath_stem, frame):
    """Render the shot's `frame` (the file carries that number); with a time stretch in force the
    stretched timeline's frame is set, so the Vector passes point at the shutter's ends."""
    at = frame * scene.render.frame_map_new / scene.render.frame_map_old
    scene.frame_set(int(math.floor(at)), subframe=at - math.floor(at))
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
    stretch = (scene.render.frame_map_old, scene.render.frame_map_new)
    set_stretch(scene, (100, 100))                     # the probe sits where the socket is at the shot's own frame
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
    set_stretch(scene, stretch)
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
    p.add_argument("--blur-reference", action="store_true",
                   help="render L_FULL WITH the profile's shutter — the blur-fidelity reference, not a plate; use a separate --out")
    p.add_argument("--exports", default=None,
                   help="the shot's exports: the default head's eyes are aimed at the exported gaze target point (vocabulary v2); "
                        "without it the rig's own eye rotation renders and the manifest says NONE")
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
    if scene.render.frame_map_old != scene.render.frame_map_new:
        # apply_profile sets the stretch with absolute values (and again before every group): a
        # scene's own remap would be overwritten silently — checked once, on the scene as loaded
        raise RenderError(f"the scene remaps time itself ({scene.render.frame_map_old} → {scene.render.frame_map_new}); the exports "
                          "refuse it too — remove it from the scene")
    gaze_aim = aim_eyes(scene, args.exports) if args.exports else {"mode": "NONE", "note": "no --exports: the rig's own eye rotation (the yaw/pitch pair) renders"}
    settings = apply_profile(scene, args.profile, samples, args.scale, args.blur_reference)
    settings["gaze_aim"] = gaze_aim
    groups = ("blur_reference",) if args.blur_reference else ("beauty", "data")
    scene_path = Path(bpy.data.filepath)
    placeholders = sorted(o.name for o in bpy.data.objects if o.name.startswith("PLACEHOLDER_"))
    manifest = {"shot_id": args.shot, "profile": args.profile, "blender": bpy.app.version_string, "device": device,
                "machine": platform.platform(), "ocio_env": os.environ.get("OCIO") or "NOT_VERIFIED",
                "source_scene": {"file": scene_path.name, "sha256": sha256(scene_path) if scene_path.exists() else "UNKNOWN",
                                 "slice_template_version": scene.get("slice_template_version"), "placeholder_objects": placeholders,
                                 "scene_kind": "placeholder template" if placeholders else "asset"},
                "settings": settings, "smoke_test_only": not settings["conformant"],
                "skin_material": skin_material(scene),
                "kind": "blur_reference" if args.blur_reference else "plates",
                "groups": {g: {"view_layers": CONV["render_groups"][g]["view_layers"]} for g in groups},
                "frames": [], "probe": None,
                "file_hash_note": "sha256 is an integrity token for the file, not a reproducibility token: EXR headers carry render time and date; pixel hashes are in bundle_manifest"}
    for frame in frames:
        row = {"frame": frame, "files": {}, "seconds": {}}
        for group in groups:
            apply_profile(scene, args.profile, samples, args.scale, args.blur_reference)
            state = set_group(scene, group, dof_setting)
            manifest["groups"][group].update(state)
            written, seconds = render_one(scene, str(raw / group), frame)
            row["files"][group] = {"file": written.name, "bytes": written.stat().st_size, "sha256": sha256(written)}
            row["seconds"][group] = seconds
        manifest["frames"].append(row)
        print(f"RENDER_FRAME {args.profile} {frame} " + " ".join(f"{g}={row['seconds'][g]}s" for g in groups))
    scene.camera.data.dof.use_dof = dof_setting
    if args.probe:
        probe_frame = CONV["shots"][args.shot]["frame_range"]["start"]  # lighting is per shot and asserted static
        written, seconds = render_probe(scene, raw, probe_frame, device)
        manifest["probe"] = {"frame": probe_frame, "file": written.name, "bytes": written.stat().st_size, "sha256": sha256(written), "seconds": seconds, "resolution": CONV["lighting_probe"]["resolution"], "samples": samples}
    for vl in scene.view_layers:
        vl.use = True
    (out / f"render_manifest.{args.profile}.json").write_text(json.dumps(manifest, indent=1) + "\n")
    kind = "blur reference (shutter open, L_FULL only)" if args.blur_reference else "plates (sharp, per-layer vectors)"
    print(f"RENDER_OK {args.profile} {len(frames)} frames, {kind} -> {out}")


if __name__ == "__main__":
    try:
        main()
    except RenderError as e:
        print(f"RENDER_ERROR: {e}", file=sys.stderr)
        sys.exit(2)
