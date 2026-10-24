"""render_still.py — one still of the character/shot at a given size (no viewport/GPU here, Cycles CPU).

    blender -b file.blend -P render_still.py -- --out DIR --view front|three_quarter|side --res 1920 --samples 12
"""
import argparse, math, sys
import bpy
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True); ap.add_argument("--view", required=True)
ap.add_argument("--res", type=int, default=1920); ap.add_argument("--samples", type=int, default=12)
ap.add_argument("--frame", type=int, default=None)
a = ap.parse_args(argv)
src = bpy.data.scenes["SLICE"]
sc = bpy.data.scenes.new("STILL")
for c in src.collection.children:
    if c.name != "C_PROXIES":
        sc.collection.children.link(c)
bpy.context.window.scene = sc
sc.frame_start, sc.frame_end = src.frame_start, src.frame_end
sc.frame_set(a.frame if a.frame else src.frame_start)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples
sc.cycles.use_denoising = False; sc.cycles.max_bounces = 4
sc.render.resolution_x = a.res; sc.render.resolution_y = 2 * round(a.res * 9 / 32); sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_depth = "8"
sc.view_settings.view_transform = src.view_settings.view_transform
cam = bpy.data.objects["CAM_001"]
VIEWS = {"front": ((0.0, -0.78, 1.30), 85.0), "three_quarter": ((-0.62, -0.60, 1.31), 85.0),   # from the −X side: the cheek strand is there
         "side": ((-0.90, -0.03, 1.30), 85.0), "shot": (None, None)}
loc, lens = VIEWS[a.view]
if loc is not None:                      # character file: put the camera on a fixed inspection view
    cam.animation_data_clear(); cam.parent = None
    cam.location = Vector(loc); cam.data.lens = lens
    target = Vector((0.0, -0.05, 1.285))
    cam.rotation_mode = "XYZ"; cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    if not bpy.data.objects.get("STILL_KEY"):
        ld = bpy.data.lights.new("STILL_KEY", "AREA"); ld.size = 1.0; ld.energy = 140.0
        o = bpy.data.objects.new("STILL_KEY", ld); sc.collection.objects.link(o)
        o.location = (0.9, -1.0, 1.9); o.rotation_euler = (Vector((0, -0.05, 1.30)) - o.location).to_track_quat("-Z", "Y").to_euler()
    w = bpy.data.worlds.new("STILL_W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.51, 0.55, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sc.camera = cam
sc.render.filepath = f"{a.out.rstrip('/')}/{a.view}.png"
bpy.ops.render.render(write_still=True)
print(f"STILL_OK {a.view} {sc.render.resolution_x}x{sc.render.resolution_y}")
