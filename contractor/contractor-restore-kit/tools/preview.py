"""Small CPU preview of a scene's camera (contractor): blender -b scene.blend -P preview.py -- --out PNG --pct 25 --samples 16 [--frame N]"""
import bpy, sys, argparse
a = argparse.ArgumentParser(); a.add_argument("--out"); a.add_argument("--pct", type=int, default=25); a.add_argument("--samples", type=int, default=16); a.add_argument("--frame", type=int)
a = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
sc = bpy.context.scene
if a.frame is not None: sc.frame_set(a.frame)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples; sc.render.resolution_percentage = a.pct
sc.render.filepath = a.out + ".exr"; bpy.ops.render.render(write_still=True)
import glob; img = bpy.data.images.load(sorted(glob.glob(a.out + ".exr*"))[0]); tmp = bpy.data.scenes.new("PNG_OUT"); tmp.render.image_settings.file_format = "PNG"; tmp.render.image_settings.color_mode = "RGB"
for k in ("view_transform", "look", "exposure", "gamma"): setattr(tmp.view_settings, k, getattr(sc.view_settings, k))
tmp.display_settings.display_device = sc.display_settings.display_device; img.save_render(a.out, scene=tmp); print("PREVIEW_OK", a.out, sc.name, sc.camera.name if sc.camera else None)
