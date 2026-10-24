"""playblast.py — burst 2 preview renders (no viewport/GPU in this environment, so Cycles on CPU at
low settings instead of Workbench; agreed in Q24.6). Renders the shot camera over a frame range into
a PNG sequence, in a temporary scene that links the shot's collections (the shot file is not saved).

    blender -b SHOT_001_v01.blend -P playblast.py -- --out DIR --frames 1001-1040 [--res 640 --samples 10]"""
import argparse, sys
import bpy
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True); ap.add_argument("--frames", required=True)
ap.add_argument("--res", type=int, default=640); ap.add_argument("--samples", type=int, default=10)
a = ap.parse_args(argv)
f0, f1 = (int(x) for x in a.frames.split("-"))
src = bpy.data.scenes["SLICE"]
sc = bpy.data.scenes.new("PLAYBLAST")
for c in src.collection.children:
    if c.name not in ("C_PROXIES",):
        sc.collection.children.link(c)
bpy.context.window.scene = sc
sc.camera = bpy.data.objects["CAM_001"]
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples
sc.cycles.use_denoising = False; sc.cycles.max_bounces = 3
sc.render.resolution_x = a.res; sc.render.resolution_y = 2 * round(a.res * 9 / 32); sc.render.resolution_percentage = 100   # even height: libx264 needs it
sc.render.fps = 24
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_depth = "8"
sc.view_settings.view_transform = src.view_settings.view_transform
w = bpy.data.worlds.new("PB_WORLD"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.36, 0.40, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.4
sc.frame_start, sc.frame_end = f0, f1
sc.render.filepath = a.out.rstrip("/") + "/pb_"
bpy.ops.render.render(animation=True)
print(f"PLAYBLAST_OK {f0}-{f1} -> {a.out}")
