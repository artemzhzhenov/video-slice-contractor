"""Is the eye behind the hand — the owner's criterion for hand_over_face (2026-09-26: the hand covers the near
eye entirely, fingers across the bridge towards the far eye), checked on a render independent of the
contractor's ray test. Per frame, two flat Workbench renders from the shot camera, the shot file never saved:

  eye alone     the eyeball object white, nothing else rendered — its full silhouette (the region the eye
                occupies, lids and socket included: stricter than the visible opening);
  eye + arm     the same eyeball white with the hand (C_HAND_FG) and the body (C_BODY) rendered black in front.

covered = 1 − white(eye + arm) / white(eye alone), for both eyes; the near eye is the one closer to the camera.

    blender -b SHOT_003_vNN.blend --python-exit-code 2 -P slice/measurements/eye_under_hand.py -- \\
        --frames 1305-1332 --out <dir> [--res 960]

Prints EYE_UNDER_HAND <frame> near=<name> <covered> far=<name> <covered> per frame and writes <dir>/eye_under_hand.json."""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--frames", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--res", type=int, default=960)
a = ap.parse_args(argv)
f0, f1 = (int(x) for x in a.frames.split("-"))
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)

sc = bpy.data.scenes["SLICE"]
bpy.context.window.scene = sc
cam = sc.camera
eyes = [bpy.data.objects[n] for n in ("HERO_EYE_L", "HERO_EYE_R")]
arm = {o.name for c in ("C_HAND_FG", "C_BODY") for o in bpy.data.collections[c].all_objects if o.type == "MESH"}
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light, sh.color_type = "FLAT", "OBJECT"
sh.show_shadows = sh.show_cavity = sh.show_object_outline = sh.show_specular_highlight = False
sc.display.render_aa = "OFF"
sc.render.film_transparent = True
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = a.res, a.res * 9 // 16, 100
sc.render.use_motion_blur = False
sc.view_settings.view_transform = "Raw"   # the ACES config has no "Standard"; white stays 1.0
sc.render.image_settings.media_type = "IMAGE"   # the shot writes multilayer EXR
sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGBA"
saved = {o.name: (o.hide_render, tuple(o.color)) for o in bpy.data.objects}


def white(path):
    img = bpy.data.images.load(str(path))
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(-1, 4)
    return int(((px[:, 0] > 0.5) & (px[:, 3] > 0.5)).sum())


def render(eye, with_arm, path):
    for o in bpy.data.objects:
        o.hide_render = not (o is eye or (with_arm and o.name in arm))
        o.color = (1, 1, 1, 1) if o is eye else (0, 0, 0, 1)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return white(path)


rows = []
for f in range(f0, f1 + 1):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    cpos = cam.matrix_world.translation

    def centre(o):
        ev = o.evaluated_get(dg)
        return ev.matrix_world @ (sum((v.co for v in ev.data.vertices), ev.data.vertices[0].co * 0) / len(ev.data.vertices))
    near, far = sorted(eyes, key=lambda o: (centre(o) - cpos).length)
    row = {"frame": f}
    for role, eye in (("near", near), ("far", far)):
        alone = render(eye, False, out / f"{role}_alone_{f}.png")
        behind = render(eye, True, out / f"{role}_arm_{f}.png")
        row[role] = {"eye": eye.name, "eye_px": alone, "covered": round(1 - behind / alone, 4) if alone else None}
    rows.append(row)
    print(f"EYE_UNDER_HAND {f} near={near.name} {row['near']['covered']:.4f} far={far.name} {row['far']['covered']:.4f} "
          f"(eye px {row['near']['eye_px']} / {row['far']['eye_px']})")
for o in bpy.data.objects:
    o.hide_render, o.color = saved[o.name][0], saved[o.name][1]
(out / "eye_under_hand.json").write_text(json.dumps({"frames": rows, "resolution": [sc.render.resolution_x, sc.render.resolution_y],
                                                     "method": __doc__.split("\n\n")[1]}, indent=1) + "\n")
nears = [r["near"]["covered"] for r in rows]
print(f"EYE_UNDER_HAND_SUMMARY near min {min(nears):.4f} over {len(rows)} frames; far {min(r['far']['covered'] for r in rows):.3f}-"
      f"{max(r['far']['covered'] for r in rows):.3f}")
