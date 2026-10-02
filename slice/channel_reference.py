"""Channel reference renders — ADR-0002 D8 ("a reference render of every channel at its extremes on the default head,
shipped with the master") and the slice brief's deliverable D, so "0.7 on this channel" has one visual answer. Runs
under Blender on an accepted shot file (its default head, its rig and its lights; the file is never saved):

    blender -b SHOT_001_v02.blend --python-exit-code 2 -P slice/channel_reference.py -- --out <dir> [--frame 1001] \
        [--samples 64] [--res 1024]

FACE_CTRL's animation is cleared, every channel of slice/channel_map.json set to 0 (the neutral), and each channel in
turn set to each end of its output range that is not 0 — the others at 0 — at one frame of the shot (its front neutral
by default, the head's own pose kept). Two cameras of our own frame the face: front, along the eyes' line of sight at
neutral, and three-quarter, the same turned 35° toward the character's left; 85 mm, the shot's lights; the shot's set, props and foreground hand excluded from the
view layer, the background transparent. Per state and view
a PNG and its change against the neutral render (the fraction of pixels whose largest channel moves by more than 2 % of
the display range): a channel whose extreme changes nothing visible is listed as NO_VISIBLE_EFFECT — the default head's
rig does not implement it, which the vocabulary then says. Writes <out>/channel_reference.json and two sheets.
The combination rule (lid + blink) is shown on its own: a widened lid with a full blink is a closed eye."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slice.eyes import eye_objects  # noqa: E402
from slice.render_passes import configure_device  # noqa: E402

CONV = json.loads((ROOT / "slice" / "conventions.json").read_text())
CMAP = json.loads((ROOT / "slice" / "channel_map.json").read_text())
CHANGE_LEVEL = 0.02           # of the display range, per pixel
NO_EFFECT_FRACTION = 1e-4     # of the frame
THREE_QUARTER_DEG = 35.0
DISTANCE_M = 0.8
HIDDEN_COLLECTIONS = ("C_ENV", "C_HAND_FG", "C_PROXIES")   # the shot's set and props are not the head's reference
COMBINATIONS = [("lid_widened_blink_full", {"lid_aperture_l": 1.0, "lid_aperture_r": 1.0, "blink_l": 1.0, "blink_r": 1.0}),
                ("lid_widened_blink_half", {"lid_aperture_l": 1.0, "lid_aperture_r": 1.0, "blink_l": 0.5, "blink_r": 0.5})]


def look_at(cam, target):
    d = (target - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def read_png(path):
    img = bpy.data.images.load(str(path), check_existing=False)
    a = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)
    bpy.data.images.remove(img)
    return a[..., :3] * a[..., 3:4] + 0.5 * (1 - a[..., 3:4])     # over mid grey, as the sheets show it


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frame", type=int, default=None)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--res", type=int, default=1024)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc = bpy.data.scenes["SLICE"]
    frame = a.frame or sc.frame_start
    ctrl = bpy.data.objects[CONV["scene_naming"]["face_ctrl"]]
    ctrl.animation_data_clear()
    channels = CMAP["channels"]
    for ch in channels:
        ctrl[ch["channel"]] = 0.0
    sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    eyes, eye_kind = eye_objects(bpy.data.objects)
    ax = Vector(CONV["scene_naming"]["eyes"]["pupil_axis_local"])
    centres = [e.evaluated_get(dg).matrix_world.translation.copy() for e in eyes]
    fwd = sum(((e.evaluated_get(dg).matrix_world.to_3x3() @ ax).normalized() for e in eyes), Vector()).normalized()
    up = Vector((0.0, 0.0, 1.0))
    target = (centres[0] + centres[1]) / 2 + up * 0.005
    left = (centres[0] - centres[1]).normalized()              # the character's left: eye L minus eye R
    views = {}
    for name, yaw in (("front", 0.0), ("three_quarter", THREE_QUARTER_DEG)):
        toward_left = 1.0 if up.cross(fwd).dot(left) > 0 else -1.0   # a positive turn about up moves fwd along up × fwd
        d = (Matrix.Rotation(math.radians(yaw) * toward_left, 3, up) @ fwd).normalized()
        cd = bpy.data.cameras.new(f"REF_{name}")
        cd.lens, cd.sensor_width, cd.clip_start = 85.0, 36.0, 0.05
        cam = bpy.data.objects.new(f"REF_CAM_{name}", cd)
        sc.collection.objects.link(cam)
        cam.location = target + d * DISTANCE_M
        look_at(cam, target)
        views[name] = cam
    sc.render.engine = "CYCLES"
    device = configure_device(sc)          # the slice's own choice: Metal where there is one, else the CPU (recorded)
    sc.cycles.samples, sc.cycles.use_denoising = a.samples, True
    sc.render.resolution_x = sc.render.resolution_y = a.res
    sc.render.resolution_percentage = 100
    sc.render.use_motion_blur = False
    sc.render.use_border = False
    if hasattr(sc.render.image_settings, "media_type"):          # Blender 5: the slice scene writes multilayer EXR
        sc.render.image_settings.media_type = "IMAGE"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.color_mode = "RGBA"
    for vl in sc.view_layers:
        vl.use = vl.name == "L_FULL"
    def layer_coll(lc, name):
        if lc.name == name:
            return lc
        for ch in lc.children:
            hit = layer_coll(ch, name)
            if hit:
                return hit
        return None
    for c in HIDDEN_COLLECTIONS:          # excluded on the view layer: an object's own (animated) visibility cannot bring it back
        lc = layer_coll(sc.view_layers["L_FULL"].layer_collection, c)
        if lc is not None:
            lc.exclude = True
    sc.render.film_transparent = True     # the set is gone and the slice has no world: transparent, shown over grey on the sheets

    states = [("neutral", {})]
    for ch in channels:
        for v in ch["output_range"]:
            if v != 0:
                states.append((f"{ch['channel']}_{'min' if v < 0 else 'max'}", {ch["channel"]: float(v)}))
    states += [(n, vals) for n, vals in COMBINATIONS]
    rows, base = [], {}
    for name, vals in states:
        for ch in channels:
            ctrl[ch["channel"]] = float(vals.get(ch["channel"], 0.0))
        sc.frame_set(frame)
        row = {"state": name, "values": vals, "views": {}}
        for vname, cam in views.items():
            sc.camera = cam
            path = out / f"{name}.{vname}.png"
            sc.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            img = read_png(path)
            if name == "neutral":
                base[vname] = img
                row["views"][vname] = {"file": path.name}
            else:
                diff = np.abs(img - base[vname]).max(-1)
                frac = float((diff > CHANGE_LEVEL).mean())
                row["views"][vname] = {"file": path.name, "changed_fraction": round(frac, 6), "max_change": round(float(diff.max()), 4)}
        if name != "neutral":
            row["visible"] = any(v["changed_fraction"] > NO_EFFECT_FRACTION for v in row["views"].values())
        rows.append(row)
        print(f"CHANNEL_REF {name} " + " ".join(f"{k}={v.get('changed_fraction', '-')}" for k, v in row["views"].items()), flush=True)
    no_effect = [r["state"] for r in rows if r.get("visible") is False]
    rec = {"rule": __doc__.split("\n\n")[2].replace("\n", " "), "source": bpy.data.filepath, "shot": sc.get("shot_id"), "frame": frame,
           "eyes": eye_kind, "channel_vocabulary_version": CMAP["channel_vocabulary_version"],
           "gaze_note": "gaze_yaw / gaze_pitch are readouts since vocabulary v2: their renders show the vocabulary's degrees (1 = 30° / 20°) on the default head; heads are driven by the gaze point",
           "hidden": list(HIDDEN_COLLECTIONS), "views": {k: {"lens_mm": 85, "distance_m": DISTANCE_M, "yaw_deg": 0.0 if k == "front" else THREE_QUARTER_DEG} for k in views},
           "render": {"device": device, "samples": a.samples, "resolution": a.res, "denoise": True, "view_layer": "L_FULL", "view_transform": sc.view_settings.view_transform},
           "change_level": CHANGE_LEVEL, "no_effect_fraction": NO_EFFECT_FRACTION, "states": rows, "no_visible_effect": no_effect}
    (out / "channel_reference.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    print(f"CHANNEL_REFERENCE_OK {len(rows)} states x {len(views)} views -> {out}; no visible effect: {no_effect or 'none'}")


main(sys.argv[sys.argv.index("--") + 1:])
